"""Isolated, deterministic event-driven procurement simulation.

The simulation deliberately has no database dependency.  It consumes a
validated synthetic scenario, advances a priority queue of events, and keeps
the physical (true) state separate from the last telemetry snapshot visible
to the scheduling policy.  This makes the model useful for staff what-if
analysis without allowing a simulation to mutate production bookings.
"""
from __future__ import annotations

import heapq
import random
import uuid
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from typing import Any

from app.schemas.simulation import SimulationEvent, SimulationRunRequest
from app.services.scheduling import (
    SchedulingRecommendation,
    classify_completion,
    recommend_for_status,
)

STAGES = ("registration", "unloading/sampling", "quality", "weighment", "documentation")
STAGE_RESOURCES = {
    "registration": "registration",
    "unloading/sampling": "unloading/sampling",
    "quality": "quality",
    "weighment": "weighment",
    "documentation": "documentation",
}
RESOURCE_GROUPS = ("registration", "unloading/sampling", "quality", "weighment", "documentation")
_RUNS: dict[str, dict[str, Any]] = {}
_MAX_STORED_RUNS = 100


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _minutes(value: timedelta) -> float:
    return round(value.total_seconds() / 60, 2)


@dataclass
class Work:
    work_id: str
    arrived_at: datetime
    quantity_kg: Decimal
    arrival_status: str
    durations: dict[str, int]
    stage_index: int = 0
    stage_started_at: datetime | None = None
    completed_at: datetime | None = None
    remaining_minutes: float | None = None

    @property
    def stage(self) -> str:
        return STAGES[self.stage_index]


@dataclass
class Resource:
    resource_id: str
    resource_type: str
    available: bool = True
    work_id: str | None = None
    busy_until: datetime | None = None
    remaining_minutes: float = 0
    assignment_token: int = 0


@dataclass(frozen=True)
class _ObservedSlotContext:
    """Minimal slot adapter used by the shared production policy."""

    id: int
    centre_id: int


@dataclass
class SimulationState:
    at: datetime
    queue: list[Work] = field(default_factory=list)
    resources: dict[str, Resource] = field(default_factory=dict)
    centre_open: bool = True
    completed: list[Work] = field(default_factory=list)


class SimulationEngine:
    """Small discrete-event engine with stable ordering for reproducibility."""

    def __init__(self, request: SimulationRunRequest):
        self.request = request
        self.centre_key = f"centre-{request.centre_id}"
        self.start = request.start_time or (
            datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
            if request.scenario == "adaptive_stress"
            else datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        if self.start.tzinfo is None:
            self.start = self.start.replace(tzinfo=timezone.utc)
        self.horizon_end = self.start + timedelta(minutes=request.horizon_minutes)
        self.rng = random.Random(request.seed)
        self.state = SimulationState(self.start, resources=self._make_resources())
        self.trace: list[dict[str, Any]] = []
        self.stages: list[dict[str, Any]] = []
        self._work: dict[str, Work] = {}
        self._events: list[tuple[datetime, int, int, str, Any]] = []
        self._external_events: list[SimulationEvent] = []
        self._event_sequence = 0
        self._last_arrival: datetime | None = None
        self._arrival_statuses: list[str] = []
        self._last_external_action: str | None = None
        self._history: list[tuple[datetime, dict[str, Any]]] = []
        self._observed: dict[str, Any] = {}
        self._last_observation_at = self.start
        self._resource_busy_minutes: dict[str, float] = {
            resource_id: 0.0 for resource_id in self.state.resources
        }
        # Older callers omitted the field; for those, one polling interval is
        # the conservative telemetry delay.  An explicit zero means the
        # caller is asking for an immediate observation.
        self._effective_observation_delay = (
            request.observation_delay_minutes
            if "observation_delay_minutes" in request.model_fields_set
            else request.observation_interval_minutes
        )
        self._schedule_external_events()
        self._schedule("observation", self.start, None, priority=3)
        for minute in range(
            request.observation_interval_minutes,
            request.horizon_minutes + 1,
            request.observation_interval_minutes,
        ):
            self._schedule("observation", self.start + timedelta(minutes=minute), None, priority=3)

    def _make_resources(self) -> dict[str, Resource]:
        counts = {
            "registration": self.request.registration_resource_count or self.request.resource_count,
            "unloading/sampling": self.request.unloading_resource_count or self.request.resource_count,
            "quality": self.request.quality_resource_count,
            "weighment": self.request.weighment_resource_count,
            "documentation": self.request.documentation_resource_count or self.request.resource_count,
        }
        resources: dict[str, Resource] = {}
        for kind in RESOURCE_GROUPS:
            for number in range(counts[kind]):
                resource_id = f"{kind.replace('/', '-')}-{number + 1}"
                resources[resource_id] = Resource(resource_id, kind)
        return resources

    def _schedule(self, kind: str, at: datetime, payload: Any, *, priority: int) -> None:
        self._event_sequence += 1
        heapq.heappush(self._events, (at, priority, self._event_sequence, kind, payload))

    def _schedule_external_events(self) -> None:
        source = self.request.events
        if source is None:
            if self.request.scenario == "adaptive_stress":
                # A fixed, documented timeline used for demos and regression
                # tests. Times are minutes from the real UTC start timestamp.
                source = [
                    SimulationEvent(event_type="centre_open", at_minute=0),
                    SimulationEvent(event_type="arrival", at_minute=20, quantity_kg=Decimal("50"), service_minutes=60, scheduled_minute=20),
                    SimulationEvent(event_type="arrival", at_minute=30, quantity_kg=Decimal("50"), service_minutes=60, scheduled_minute=30),
                    SimulationEvent(event_type="arrival", at_minute=40, quantity_kg=Decimal("50"), service_minutes=60, scheduled_minute=40),
                    SimulationEvent(event_type="arrival", at_minute=50, quantity_kg=Decimal("50"), service_minutes=60, scheduled_minute=50),
                    SimulationEvent(event_type="arrival", at_minute=60, quantity_kg=Decimal("50"), service_minutes=60, scheduled_minute=60),
                    SimulationEvent(event_type="outage", at_minute=75, resource_type="quality", resource_id="quality-1"),
                    SimulationEvent(event_type="no_show", at_minute=120, quantity_kg=Decimal("15"), scheduled_minute=120),
                    SimulationEvent(event_type="outage", at_minute=105, resource_type="weighment", resource_id="weighment-1"),
                    SimulationEvent(event_type="arrival", at_minute=135, quantity_kg=Decimal("30"), service_minutes=22, scheduled_minute=135),
                    SimulationEvent(event_type="recovery", at_minute=180, resource_type="quality", resource_id="quality-1"),
                    SimulationEvent(event_type="recovery", at_minute=180, resource_type="weighment", resource_id="weighment-1"),
                    SimulationEvent(event_type="arrival", at_minute=240, quantity_kg=Decimal("20"), service_minutes=16, scheduled_minute=180),
                    SimulationEvent(event_type="observation", at_minute=140),
                ]
            else:
                count = max(1, self.request.horizon_minutes // 30)
                source = [
                    SimulationEvent(
                        event_type="arrival",
                        at_minute=min(i * 30, self.request.horizon_minutes),
                        quantity_kg=Decimal(str(self.rng.randint(5, 30))),
                        service_minutes=self.rng.randint(8, 20),
                    )
                    for i in range(count)
                ]
                if self.request.horizon_minutes >= 90:
                    outage_at = self.request.horizon_minutes // 3
                    source += [
                        SimulationEvent(
                            event_type="outage",
                            at_minute=outage_at,
                            resource_type="quality",
                            resource_id="quality-1",
                        ),
                        SimulationEvent(
                            event_type="recovery",
                            at_minute=outage_at + 20,
                            resource_type="quality",
                            resource_id="quality-1",
                        ),
                    ]
        # Materialise omitted service times once, before the event loop, so
        # adaptive and baseline runs compare the exact same work.
        self._external_events = [
            (
                event.model_copy(
                    update={"service_minutes": self.rng.randint(8, 20)}
                )
                if event.event_type in ("arrival", "no_show") and event.service_minutes is None
                else event
            )
            for event in source
        ]
        priorities = {"centre_open": 1, "outage": 1, "recovery": 2, "arrival": 3, "no_show": 3, "observation": 4}
        for event in self._external_events:
            self._schedule(
                "external",
                self.start + timedelta(minutes=event.at_minute),
                event,
                priority=priorities.get(event.event_type, 3),
            )

    @property
    def events(self) -> list[dict[str, Any]]:
        """Return the canonical external stream for replay/debug tooling."""
        priorities = {"outage": 1, "recovery": 2, "arrival": 3, "no_show": 3}
        return [
            {
                "sequence": sequence,
                "event": event,
                "at": self.start + timedelta(minutes=event.at_minute),
                "priority": priorities.get(event.event_type, 3),
            }
            for sequence, event in enumerate(self._external_events)
        ]

    def _duration_breakdown(self, event: SimulationEvent) -> dict[str, int]:
        total = event.service_minutes or self.rng.randint(8, 20)
        quantity_factor = max(0, int(event.quantity_kg // 10))
        raw = {
            "registration": max(1, total // 6),
            "unloading/sampling": max(1, total // 3 + quantity_factor),
            "quality": max(1, total // 5 + (quantity_factor if event.quantity_kg >= 20 else 0)),
            "weighment": max(1, total // 8),
        }
        raw["documentation"] = max(1, total - sum(raw.values()))
        return raw

    def _arrival_status(self, event: SimulationEvent, at: datetime) -> str:
        if event.arrival_status:
            return event.arrival_status
        if event.event_type == "no_show":
            return "no-show"
        if self._last_arrival and (at - self._last_arrival).total_seconds() <= 5 * 60:
            return "clustered"
        self._last_arrival = at
        if event.scheduled_minute is not None:
            delta = event.at_minute - event.scheduled_minute
            return "early" if delta < 0 else "late" if delta > 0 else "on-time"
        return "on-time"

    def _snapshot(self, at: datetime) -> dict[str, Any]:
        active = [resource for resource in self.state.resources.values() if resource.work_id]
        pending = self.state.queue
        stage_queues = {
            stage: [
                {
                    "work_id": work.work_id,
                    "quantity_kg": str(work.quantity_kg),
                    "remaining_minutes": round(
                        work.remaining_minutes or work.durations[work.stage], 2
                    ),
                }
                for work in pending
                if work.stage == stage
            ]
            for stage in STAGES
        }
        return {
            "at": _iso(at),
            "queue_work": len(pending),
            "queue_quantity_kg": str(sum((work.quantity_kg for work in pending), Decimal(0))),
            "active_resources": {
                resource.resource_id: {
                    "resource_type": resource.resource_type,
                    "work_id": resource.work_id,
                    "available": resource.available,
                    "available_at": _iso(resource.busy_until),
                    "remaining_minutes": round(
                        _minutes(resource.busy_until - at)
                        if resource.busy_until and resource.busy_until > at
                        else resource.remaining_minutes,
                        2,
                    ),
                }
                for resource in self.state.resources.values()
            },
            "stage_queues": stage_queues,
            "active_resource_count": len(active),
            "active_server_count": len(active),
            "available_resource_count": sum(
                resource.available and resource.work_id is None
                for resource in self.state.resources.values()
            ),
            "resource_status": {
                key: {
                    "resource_type": resource.resource_type,
                    "work_id": resource.work_id,
                    "available": resource.available,
                    "available_at": _iso(resource.busy_until),
                }
                for key, resource in self.state.resources.items()
            },
            "centre_status": {self.centre_key: "OPEN" if self.state.centre_open else "OUTAGE"},
            "completed_work": len(self.state.completed),
            "completed_quantity_kg": str(
                sum((work.quantity_kg for work in self.state.completed), Decimal(0))
            ),
        }

    def _capture_history(self, at: datetime) -> None:
        snapshot = self._snapshot(at)
        if self._history and self._history[-1][0] == at:
            self._history[-1] = (at, snapshot)
        else:
            self._history.append((at, snapshot))

    def _observe(self, at: datetime) -> None:
        target = at - timedelta(minutes=self._effective_observation_delay)
        candidates = [snapshot for timestamp, snapshot in self._history if timestamp <= target]
        snapshot = deepcopy(candidates[-1] if candidates else self._history[0][1])
        captured_at = datetime.fromisoformat(snapshot["at"])
        age = max(0, _minutes(at - captured_at))
        snapshot.update(
            {
                "observed_at": _iso(at),
                "captured_at": _iso(captured_at),
                "data_age_minutes": age,
                "is_stale": age > self.request.stale_after_minutes,
                "observation_delay_minutes": self._effective_observation_delay,
            }
        )
        self._observed = snapshot
        self._last_observation_at = at

    def _pause_resource(self, resource: Resource, at: datetime) -> None:
        if resource.work_id and resource.busy_until and resource.busy_until > at:
            work = self._work[resource.work_id]
            work.remaining_minutes = max(0.01, _minutes(resource.busy_until - at))
            self.state.queue.append(work)
            resource.work_id = None
            resource.busy_until = None
            resource.assignment_token += 1

    def _resource_is_available(self, resource: Resource) -> bool:
        return resource.available and self.state.centre_open and resource.work_id is None

    def _assign(self, at: datetime) -> None:
        if not self.state.centre_open:
            return
        changed = True
        while changed:
            changed = False
            for work in list(self.state.queue):
                kind = STAGE_RESOURCES[work.stage]
                resource = next(
                    (
                        candidate
                        for candidate in self.state.resources.values()
                        if candidate.resource_type == kind and self._resource_is_available(candidate)
                    ),
                    None,
                )
                if resource is None:
                    continue
                self.state.queue.remove(work)
                duration = work.remaining_minutes or work.durations[work.stage]
                work.remaining_minutes = None
                work.stage_started_at = at
                resource.work_id = work.work_id
                resource.busy_until = at + timedelta(minutes=duration)
                self._resource_busy_minutes[resource.resource_id] += float(duration)
                resource.assignment_token += 1
                token = resource.assignment_token
                self._schedule(
                    "complete",
                    resource.busy_until,
                    (resource.resource_id, token),
                    priority=0,
                )
                self.trace.append(
                    {
                        "at": _iso(at),
                        "action": "assign",
                        "work_id": work.work_id,
                        "stage": work.stage,
                        "resource_id": resource.resource_id,
                        "duration_minutes": round(duration, 2),
                        "quantity_kg": str(work.quantity_kg),
                    }
                )
                changed = True

    def _complete(self, at: datetime, payload: tuple[str, int]) -> None:
        resource_id, token = payload
        resource = self.state.resources.get(resource_id)
        if (
            resource is None
            or resource.assignment_token != token
            or resource.work_id is None
            or resource.busy_until is None
            or resource.busy_until > at
            or not resource.available
            or not self.state.centre_open
        ):
            return
        work = self._work[resource.work_id]
        resource.work_id = None
        resource.busy_until = None
        resource.remaining_minutes = 0
        work.stage_index += 1
        self.trace.append(
            {
                "at": _iso(at),
                "action": "stage_complete",
                "work_id": work.work_id,
                "stage": STAGES[work.stage_index - 1],
                "resource_id": resource.resource_id,
            }
        )
        if work.stage_index == len(STAGES):
            work.completed_at = at
            self.state.completed.append(work)
            self.trace.append(
                {
                    "at": _iso(at),
                    "action": "complete",
                    "work_id": work.work_id,
                    "quantity_kg": str(work.quantity_kg),
                }
            )
        else:
            self.state.queue.append(work)

    def _handle_external(self, event: SimulationEvent, at: datetime) -> None:
        if event.event_type == "observation":
            self._observe(at)
            return
        if event.event_type == "centre_open":
            self.state.centre_open = True
            self.trace.append({"at": _iso(at), "action": "centre_open"})
            return
        self._last_external_action = event.event_type
        if event.event_type in ("arrival", "no_show"):
            status = self._arrival_status(event, at)
            self._arrival_statuses.append(status)
            self.trace.append(
                {
                    "at": _iso(at),
                    "action": "arrival_status",
                    "status": status,
                    "quantity_kg": str(event.quantity_kg),
                }
            )
            if status != "no-show":
                work_id = f"work-{len(self._work) + 1}"
                work = Work(
                    work_id,
                    at,
                    event.quantity_kg,
                    status,
                    self._duration_breakdown(event),
                )
                self._work[work_id] = work
                self.state.queue.append(work)
            return

        if event.resource_type == "centre":
            self.state.centre_open = event.event_type == "recovery"
            if not self.state.centre_open:
                for resource in self.state.resources.values():
                    self._pause_resource(resource, at)
        else:
            resource_id = event.resource_id
            if resource_id == "resource-1" and event.resource_type not in ("resource", "centre"):
                resource_id = f"{event.resource_type.replace('/', '-')}-1"
            targets = (
                [
                    resource
                    for resource in self.state.resources.values()
                    if resource.resource_id.endswith(resource_id.rsplit("-", 1)[-1])
                ]
                if event.resource_type == "resource"
                else [self.state.resources[resource_id]]
                if resource_id in self.state.resources
                else []
            )
            for resource in targets:
                resource.available = event.event_type == "recovery"
                if not resource.available:
                    self._pause_resource(resource, at)
        self.trace.append(
            {
                "at": _iso(at),
                "action": event.event_type,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
            }
        )

    def _estimate(self, at: datetime) -> dict[str, Any]:
        observed = self._observed
        workload: dict[str, float] = {kind: 0 for kind in RESOURCE_GROUPS}
        for stage, queued_work in observed.get("stage_queues", {}).items():
            workload[STAGE_RESOURCES[stage]] += sum(
                float(item["remaining_minutes"]) for item in queued_work
            )
        for resource in observed.get("active_resources", {}).values():
            if resource["work_id"]:
                workload[resource["resource_type"]] += float(
                    resource.get("remaining_minutes", 0)
                )
        stage_bounds = {
            stage: round(
                workload[STAGE_RESOURCES[stage]]
                / max(
                    1,
                    sum(
                        resource["available"]
                        for resource in observed.get("active_resources", {}).values()
                        if resource["resource_type"] == STAGE_RESOURCES[stage]
                    ),
                ),
                2,
            )
            for stage in STAGES
        }
        earliest = max(stage_bounds.values(), default=0)
        age = observed.get("data_age_minutes", 0)
        outage_penalty = 20 if observed.get("centre_status", {}).get(self.centre_key) != "OPEN" else sum(
            10
            for resource in observed.get("active_resources", {}).values()
            if not resource["available"]
        )
        uncertainty = round(5 + age * 0.5 + outage_penalty + (earliest * 0.15), 2)
        lower = at + timedelta(minutes=earliest)
        upper = at + timedelta(minutes=earliest + uncertainty)
        return {
            "earliest_minutes": round(earliest, 2),
            "latest_minutes": round(earliest + uncertainty, 2),
            "lower_timestamp": _iso(lower),
            "upper_timestamp": _iso(upper),
            "p50_timestamp": _iso(at + timedelta(minutes=earliest + uncertainty * 0.25)),
            "p90_timestamp": _iso(at + timedelta(minutes=earliest + uncertainty * 0.75)),
            "uncertainty_minutes": uncertainty,
            "data_age_minutes": age,
            "observation_delay_minutes": self._effective_observation_delay,
            "is_stale": bool(self._observed.get("is_stale")),
            "confidence": "low" if uncertainty >= 20 or self._observed.get("is_stale") else "medium",
            "claim": "completion window; not an exact ETA",
            "basis": "stage workload, resource availability, outages, and observation age",
            "stage_bounds_minutes": stage_bounds,
        }

    def _decision_trace(self, at: datetime) -> None:
        if not self._observed:
            self._observe(at)
        estimate = self._estimate(at)
        slot_end = self.horizon_end
        estimated_completion = datetime.fromisoformat(estimate["upper_timestamp"])
        assessment = classify_completion(estimated_completion, slot_end).value
        recommendation, recommended_slot_id, recommended_centre_id = recommend_for_status(
            classify_completion(estimated_completion, slot_end),
            same_centre_slot=(
                _ObservedSlotContext(0, self.request.centre_id)
                if self._observed.get("centre_status", {}).get(self.centre_key) == "OPEN"
                and not any(
                    not resource["available"]
                    and resource["resource_type"] == "weighment"
                    for resource in self._observed.get("active_resources", {}).values()
                )
                else None
            ),
            alternate_centre_slot=(
                _ObservedSlotContext(0, self.request.centre_id + 1)
                if self._observed.get("centre_status", {}).get(self.centre_key) != "OPEN"
                else None
            ),
        )
        common = {
            "at": _iso(at),
            "observation_timestamp": self._observed.get("observed_at"),
            "observation_captured_at": self._observed.get("captured_at"),
            "observed_queue": self._observed.get("queue_work", 0),
            "observed_queue_quantity_kg": self._observed.get("queue_quantity_kg", "0"),
            "active_server_count": self._observed.get("active_server_count", 0),
            "active_servers": self._observed.get("active_server_count", 0),
            "service_time_minutes": estimate["earliest_minutes"],
            "estimated_completion": estimate["upper_timestamp"],
            "completion_window": estimate,
            "slot_end": _iso(slot_end),
            "assessment": assessment,
            "recommendation": recommendation.value,
            "recommended_slot_id": recommended_slot_id,
            "recommended_centre_id": recommended_centre_id,
            "data_age_minutes": self._observed.get("data_age_minutes", 0),
            "observation_delay_minutes": self._effective_observation_delay,
            "policy": "canonical-adaptive-v1",
            "policy_thresholds_minutes": {
                "at_risk": 10,
                "delayed": 45,
            },
            "observed_at": self._observed.get("observed_at"),
            "observed_stage_queues": deepcopy(self._observed.get("stage_queues", {})),
            "observed_resource_states": deepcopy(self._observed.get("active_resources", {})),
            "bottleneck_stage": max(
                estimate["stage_bounds_minutes"],
                key=estimate["stage_bounds_minutes"].get,
                default=None,
            ),
            "confidence": estimate["confidence"],
            "stage_workload_minutes": estimate["stage_bounds_minutes"],
        }
        reasons = {
            "OBSERVE": "Use the latest timestamped telemetry snapshot",
            "ESTIMATE": "Project stage workload through available resources",
            "ASSESS": "Apply the production completion policy to the interval estimate",
            "ADAPT": "Recommend only an operationally supported slot action",
        }
        for action, reason in reasons.items():
            self.trace.append(dict(common, action=action, reason=reason))
        phase = (
            "OUTAGE"
            if self._observed.get("centre_status", {}).get(self.centre_key) != "OPEN"
            else "QUALITY_DELAY"
            if any(
                not resource["available"] and resource["resource_type"] == "quality"
                for resource in self._observed.get("active_resources", {}).values()
            )
            else "OUTAGE"
            if any(
                not resource["available"]
                for resource in self._observed.get("active_resources", {}).values()
            )
            else "RECOVERY"
            if self._last_external_action == "recovery"
            else "SURGE"
            if self._observed.get("queue_work", 0)
            > len(self._observed.get("active_resources", {}))
            else "NORMAL"
        )
        if self._observed.get("is_stale"):
            phase = "STALE"
        if not self.stages or self.stages[-1]["phase"] != phase:
            self.stages.append(
                {
                    "phase": phase,
                    "at": _iso(at),
                    "reason": "derived from the observed queue and resource event stream",
                }
            )

    def run(self) -> dict[str, Any]:
        self._capture_history(self.start)
        while self._events:
            at, _priority, _sequence, kind, payload = heapq.heappop(self._events)
            # Observation events are limited to the horizon.  Internal stage
            # completion events may drain admitted work after the horizon.
            if at > self.horizon_end and kind in ("external", "observation"):
                continue
            self.state.at = at
            if kind == "complete":
                self._complete(at, payload)
            elif kind == "external":
                self._handle_external(payload, at)
            elif kind == "observation":
                self._observe(at)
            self._capture_history(at)
            if kind in ("external", "observation"):
                self._decision_trace(at)
            self._assign(at)
            self._capture_history(at)
        self.state.at = max(self.state.at, self.horizon_end)
        if not self._observed:
            self._observe(self.state.at)
        adaptive = self._metrics()
        baseline = self._baseline_metrics()
        comparable = {
            key: round(float(adaptive[key]) - float(baseline[key]), 2)
            for key in adaptive
            if key in baseline and isinstance(adaptive[key], (int, float))
            and isinstance(baseline[key], (int, float))
        }
        return {
            "seed": self.request.seed,
            "centre_id": self.request.centre_id,
            "scenario": self.request.scenario,
            "start_time": _iso(self.start),
            "canonical_sequence": self._canonical_sequence(),
            "trace": self.trace,
            "true_state": self._true_state(),
            "observed_state": self._observed,
            "completion_window": self._estimate(self.state.at),
            "stages": self.stages,
            "canonical_stages": list(STAGES),
            "canonical_stage_sequence": "→".join(STAGES),
            "adaptive_metrics": adaptive,
            "baseline_metrics": baseline,
            "comparison": {
                "metrics": comparable,
                "completion_delta_minutes": round(
                    baseline["completion_minutes"] - adaptive["completion_minutes"], 2
                ),
                "completed_delta": adaptive["completed"] - baseline["completed"],
                "admitted_delta": adaptive["admitted"] - baseline["admitted"],
                "remaining_queue_delta": adaptive["remaining_queue"] - baseline["remaining_queue"],
                "mean_cycle_delta_minutes": round(
                    adaptive["mean_cycle_minutes"] - baseline["mean_cycle_minutes"], 2
                ),
                "throughput_delta_kg": round(
                    float(adaptive["throughput_kg_per_hour"] - baseline["throughput_kg_per_hour"]), 2
                ),
                "adaptive_policy": "multi-stage, capacity-aware, outage-aware",
                "baseline_policy": baseline["policy"],
            },
        }

    def _canonical_sequence(self) -> list[dict[str, Any]]:
        # The external events are already deterministically ordered by the
        # heap sequence, but expose a compact, serialisable replay contract.
        priorities = {"outage": 1, "recovery": 2, "arrival": 3, "no_show": 3}
        ordered = sorted(
            enumerate(self._external_events),
            key=lambda pair: (
                pair[1].at_minute,
                priorities.get(pair[1].event_type, 3),
                pair[0],
            ),
        )
        return [
            {
                "sequence": sequence,
                "event_type": event.event_type,
                "at": _iso(self.start + timedelta(minutes=event.at_minute)),
                "at_minute": event.at_minute,
                "centre_id": event.centre_id,
                "resource_id": event.resource_id,
                "resource_type": event.resource_type,
                "quantity_kg": str(event.quantity_kg),
                "service_minutes": event.service_minutes or 0,
            }
            for sequence, (_original_index, event) in enumerate(ordered)
        ]

    def _true_state(self) -> dict[str, Any]:
        return {
            **self._snapshot(self.state.at),
            "at": _iso(self.state.at),
            "completed": [
                {
                    "work_id": work.work_id,
                    "completed_at": _iso(work.completed_at),
                    "quantity_kg": str(work.quantity_kg),
                    "arrival_status": work.arrival_status,
                }
                for work in self.state.completed
            ],
            "pending_work": [
                {
                    "work_id": work.work_id,
                    "stage": work.stage,
                    "arrival_status": work.arrival_status,
                    "quantity_kg": str(work.quantity_kg),
                }
                for work in self.state.queue
            ],
        }

    def _metrics(self) -> dict[str, Any]:
        completed = [work for work in self.state.completed if work.completed_at]
        completion = max((work.completed_at for work in completed), default=self.start)
        admitted = [work for work in self._work.values()]
        waits = sorted(
            (work.stage_started_at - work.arrived_at).total_seconds() / 60
            for work in completed
            if work.stage_started_at
        )
        decisions = [item for item in self.trace if item.get("action") == "ADAPT"]
        within_slot = [work for work in completed if work.completed_at <= self.horizon_end]
        busy_minutes = sum(self._resource_busy_minutes.values())
        return {
            "policy": "multi-stage, capacity-aware, outage-aware",
            "completed": len(completed),
            "admitted": len(admitted),
            "completed_quantity_kg": str(sum((work.quantity_kg for work in completed), Decimal(0))),
            "remaining_queue": len(self.state.queue)
            + sum(resource.work_id is not None for resource in self.state.resources.values()),
            "completion_minutes": round((completion - self.start).total_seconds() / 60, 2),
            "throughput_kg_per_hour": round(
                float(sum((work.quantity_kg for work in completed), Decimal(0)))
                / max(1, (completion - self.start).total_seconds() / 3600),
                2,
            ),
            "mean_wait_minutes": round(
                sum((work.stage_started_at - work.arrived_at).total_seconds() / 60
                    for work in completed if work.stage_started_at)
                / len(completed), 2,
            ) if completed else 0,
            "median_wait_minutes": round(float(median(waits)), 2) if waits else 0,
            "p90_wait_minutes": round(waits[min(len(waits) - 1, int(len(waits) * 0.9))], 2) if waits else 0,
            "total_arrivals": len(self._arrival_statuses),
            "delayed_lots": len(admitted) - len(within_slot),
            "completion_within_slot_pct": round(100 * len(within_slot) / max(1, len(admitted)), 2),
            "warnings": sum(item.get("recommendation") == SchedulingRecommendation.WARN_FARMER.value for item in decisions),
            "reschedules": sum(item.get("recommendation") == SchedulingRecommendation.PROPOSE_NEW_SLOT.value for item in decisions),
            "alternate_centre_recommendations": sum(
                item.get("recommendation") == SchedulingRecommendation.RECOMMEND_ALTERNATE_CENTRE.value
                for item in decisions
            ),
            "time_integrated_resource_utilisation_minutes": round(busy_minutes, 2),
            "peak_queue": max(
                [item["observed_queue"] for item in self.trace if "observed_queue" in item] or [0]
            ),
            "no_shows": self._arrival_statuses.count("no-show"),
            "mean_cycle_minutes": round(
                sum((work.completed_at - work.arrived_at).total_seconds() / 60 for work in completed)
                / len(completed),
                2,
            )
            if completed
            else 0,
            "arrival_statuses": {
                status: self._arrival_statuses.count(status)
                for status in ("early", "on-time", "late", "no-show", "clustered")
            },
            "stage_completions": {
                stage: sum(work.stage_index > index for work in admitted)
                for index, stage in enumerate(STAGES)
            },
            "resource_utilisation": {
                resource_id: round(self._resource_busy_minutes[resource_id], 2)
                for resource_id, resource in self.state.resources.items()
            },
        }

    def _baseline_metrics(self) -> dict[str, Any]:
        # A deliberately simple serial FIFO policy gives staff a stable,
        # honest counterfactual while using exactly the same generated work.
        arrivals = sorted(
            (
                event
                for event in self._external_events
                if event.event_type == "arrival"
            ),
            key=lambda item: item.at_minute,
        )
        cursor = self.start
        records: list[tuple[datetime, datetime, datetime, Decimal]] = []
        for event in arrivals:
            arrived = self.start + timedelta(minutes=event.at_minute)
            started = max(cursor, arrived)
            completed_at = started + timedelta(minutes=sum(self._duration_breakdown(event).values()))
            records.append((arrived, started, completed_at, event.quantity_kg))
            cursor = completed_at
        completed_records = [record for record in records if record[2] <= self.horizon_end]
        quantity = sum((record[3] for record in records), Decimal(0))
        completed_quantity = sum((record[3] for record in completed_records), Decimal(0))
        waits = [(record[1] - record[0]).total_seconds() / 60 for record in records]
        cycles = [(record[2] - record[0]).total_seconds() / 60 for record in records]
        completion_minutes = (cursor - self.start).total_seconds() / 60
        outstanding_counts = [
            sum(arrived <= at < completed_at for arrived, _started, completed_at, _quantity in records)
            for at in [record[0] for record in records] + [record[2] for record in records]
        ]
        arrival_statuses = Counter(self._arrival_statuses)
        return {
            "policy": "static FIFO, one resource",
            "completed": len(records),
            "admitted": len(records),
            "completed_quantity_kg": str(quantity),
            "remaining_queue": sum(record[2] > self.horizon_end for record in records),
            "completion_minutes": round(completion_minutes, 2),
            "throughput_kg_per_hour": round(
                float(quantity) / max(1, completion_minutes / 60), 2
            ),
            "mean_cycle_minutes": round(sum(cycles) / max(1, len(cycles)), 2),
            "mean_wait_minutes": round(sum(waits) / max(1, len(waits)), 2),
            "median_wait_minutes": round(float(median(waits)), 2) if waits else 0,
            "p90_wait_minutes": round(sorted(waits)[min(len(waits) - 1, int(len(waits) * 0.9))], 2) if waits else 0,
            "total_arrivals": len(self._arrival_statuses),
            "delayed_lots": len(records) - len(completed_records),
            "completion_within_slot_pct": round(100 * len(completed_records) / max(1, len(records)), 2),
            "warnings": 0,
            "reschedules": 0,
            "alternate_centre_recommendations": 0,
            "time_integrated_resource_utilisation_minutes": round(completion_minutes, 2),
            "peak_queue": max(outstanding_counts, default=0),
            "no_shows": sum(event.event_type == "no_show" for event in self._external_events),
            "arrival_statuses": {
                status: arrival_statuses.get(status, 0)
                for status in ("early", "on-time", "late", "no-show", "clustered")
            },
            "stage_completions": {stage: len(records) for stage in STAGES},
            "resource_utilisation": {"baseline-1": round(completion_minutes, 2)},
        }


def run_simulation(request: SimulationRunRequest) -> dict[str, Any]:
    return SimulationEngine(request).run()


def create_run(request: SimulationRunRequest) -> tuple[str, dict[str, Any]]:
    run_id = str(uuid.uuid4())
    result = run_simulation(request)
    while len(_RUNS) >= _MAX_STORED_RUNS:
        _RUNS.pop(next(iter(_RUNS)))
    _RUNS[run_id] = deepcopy(result)
    return run_id, result


def get_run(run_id: str) -> dict[str, Any] | None:
    result = _RUNS.get(run_id)
    return deepcopy(result) if result is not None else None
