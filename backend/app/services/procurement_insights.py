"""Explainable, centre-level procurement decision support.

This service observes the operational scheduling engine and adds reference
context for presentation. It never feeds reference data back into queue,
ETA, throughput, or scheduling calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core import clock
from app.models import QueueStatus
from app.repositories import bookings as booking_repository
from app.repositories import procurement as procurement_repository
from app.repositories import queue as queue_repository
from app.repositories import throughput as throughput_repository
from app.services import procurement_context
from app.services import scheduling
from app.services.eta import calculate_eta


class ProcurementInsightError(Exception):
    def __init__(self, detail: str, status_code: int) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass(frozen=True)
class OperationalMetrics:
    queue_depth: int
    active_booking_count: int
    current_serving_token: int | None
    average_service_minutes: Decimal | None
    estimated_wait_minutes: Decimal | None


@dataclass(frozen=True)
class AttentionItem:
    code: str
    title: str
    detail: str
    evidence: list[str]


@dataclass(frozen=True)
class ProcurementInsight:
    centre_id: int
    centre_name: str
    centre_code: str
    district: str
    operational_status: scheduling.SchedulingStatus
    metrics: OperationalMetrics
    reasons: list[str]
    attention_items: list[AttentionItem]
    booking_assessments: list[scheduling.SchedulingAssessment]
    reference_context: procurement_context.CentreAgriculturalContext
    calculated_at: datetime


def get_centre_procurement_insight(
    session: Session,
    centre_id: int,
    *,
    dataset_type: str | None = None,
    metric_name: str | None = None,
    season_or_period: str | None = None,
) -> ProcurementInsight:
    """Build a deterministic operational snapshot and explanation."""
    centre = procurement_repository.get_centre(session, centre_id)
    if centre is None:
        raise ProcurementInsightError("Procurement centre not found", 404)
    if not centre.active:
        raise ProcurementInsightError("Procurement centre is inactive", 409)

    live_queue = queue_repository.list_live_queue(session, centre_id)
    pending_bookings = booking_repository.list_pending_bookings_for_centre(
        session, centre_id
    )
    assessments = scheduling.assess_centre(session, centre_id)
    reference_context = procurement_context.get_centre_agricultural_context(
        session,
        centre_id,
        dataset_type=dataset_type,
        metric_name=metric_name,
        season_or_period=season_or_period,
    )

    latest_snapshot = throughput_repository.get_latest_snapshot(session, centre_id)
    wait_estimates = [
        calculate_eta(session, entry.id).estimated_wait_minutes for entry in live_queue
    ]
    current_serving = next(
        (entry.token_number for entry in live_queue if entry.queue_status == QueueStatus.SERVING),
        None,
    )

    status = _centre_status(assessments)
    reasons = _build_reasons(
        status,
        assessments,
        queue_depth=len(live_queue),
        average_service_minutes=(
            Decimal(latest_snapshot.avg_minutes_per_farmer)
            if latest_snapshot is not None
            else None
        ),
    )
    attention_items = _build_attention_items(
        status,
        assessments,
        queue_depth=len(live_queue),
        current_serving_token=current_serving,
    )

    return ProcurementInsight(
        centre_id=centre.id,
        centre_name=centre.name,
        centre_code=centre.code,
        district=centre.district,
        operational_status=status,
        metrics=OperationalMetrics(
            queue_depth=len(live_queue),
            active_booking_count=len(pending_bookings),
            current_serving_token=current_serving,
            average_service_minutes=(
                Decimal(latest_snapshot.avg_minutes_per_farmer)
                if latest_snapshot is not None
                else None
            ),
            estimated_wait_minutes=max(wait_estimates) if wait_estimates else None,
        ),
        reasons=reasons,
        attention_items=attention_items,
        booking_assessments=assessments,
        reference_context=reference_context,
        calculated_at=clock.utcnow(),
    )


def _centre_status(
    assessments: list[scheduling.SchedulingAssessment],
) -> scheduling.SchedulingStatus:
    statuses = {assessment.scheduling_status for assessment in assessments}
    for status in (
        scheduling.SchedulingStatus.DELAYED,
        scheduling.SchedulingStatus.AT_RISK,
        scheduling.SchedulingStatus.ON_TRACK,
    ):
        if status in statuses:
            return status
    return scheduling.SchedulingStatus.ON_TRACK


def _build_reasons(
    status: scheduling.SchedulingStatus,
    assessments: list[scheduling.SchedulingAssessment],
    *,
    queue_depth: int,
    average_service_minutes: Decimal | None,
) -> list[str]:
    reasons = [
        f"{sum(a.scheduling_status == status for a in assessments)} pending booking(s) "
        f"have the centre's highest observed scheduling status: {status.value}."
    ]
    if queue_depth:
        reasons.append(f"The live queue contains {queue_depth} farmer(s).")
    else:
        reasons.append("There are no farmers in the live queue.")
    if average_service_minutes is not None:
        reasons.append(
            f"The latest recorded throughput pace is {average_service_minutes} "
            "minutes per farmer."
        )
    else:
        reasons.append("No throughput snapshot is available yet.")
    return reasons


def _build_attention_items(
    status: scheduling.SchedulingStatus,
    assessments: list[scheduling.SchedulingAssessment],
    *,
    queue_depth: int,
    current_serving_token: int | None,
) -> list[AttentionItem]:
    items: list[AttentionItem] = []
    delayed = sum(
        assessment.scheduling_status == scheduling.SchedulingStatus.DELAYED
        for assessment in assessments
    )
    at_risk = sum(
        assessment.scheduling_status == scheduling.SchedulingStatus.AT_RISK
        for assessment in assessments
    )
    if delayed:
        items.append(
            AttentionItem(
                code="DELAYED_BOOKINGS",
                title="Delayed bookings need attention",
                detail=f"{delayed} pending booking(s) are DELAYED.",
                evidence=["Existing scheduling assessment status is DELAYED."],
            )
        )
    if at_risk:
        items.append(
            AttentionItem(
                code="AT_RISK_BOOKINGS",
                title="Bookings are at risk",
                detail=f"{at_risk} pending booking(s) are AT_RISK.",
                evidence=["Existing scheduling assessment status is AT_RISK."],
            )
        )
    if queue_depth:
        serving = (
            f"Token {current_serving_token} is currently serving."
            if current_serving_token is not None
            else "No token is currently marked as serving."
        )
        items.append(
            AttentionItem(
                code="LIVE_QUEUE",
                title="Live queue requires monitoring",
                detail=f"{queue_depth} farmer(s) are in the live queue. {serving}",
                evidence=["Queue entries are in WAITING, CALLED, or SERVING state."],
            )
        )
    if not assessments:
        items.append(
            AttentionItem(
                code="NO_PENDING_BOOKINGS",
                title="No pending bookings",
                detail="No non-terminal bookings are currently recorded.",
                evidence=["Operational booking statuses contain no pending bookings."],
            )
        )
    return items
