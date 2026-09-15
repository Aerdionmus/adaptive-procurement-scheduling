from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SimulationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    event_type: Literal["centre_open", "arrival", "no_show", "outage", "recovery", "observation"]
    at_minute: int = Field(ge=0)
    quantity_kg: Decimal = Field(default=Decimal("10"), gt=0)
    service_minutes: int | None = Field(default=None, gt=0)
    centre_id: str = "centre-1"
    resource_id: str = "resource-1"
    resource_type: Literal[
        "centre",
        "resource",
        "registration",
        "unloading/sampling",
        "quality",
        "weighment",
        "documentation",
    ] = "centre"
    scheduled_minute: int | None = Field(default=None, ge=0)
    arrival_status: Literal["early", "on-time", "late", "no-show", "clustered"] | None = None


class SimulationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    centre_id: int = Field(gt=0)
    scenario: Literal["generated", "adaptive_stress"] = "generated"
    seed: int = Field(default=1, ge=0, le=2_147_483_647)
    start_time: datetime | None = None
    horizon_minutes: int = Field(default=240, gt=0, le=10080)
    observation_interval_minutes: int = Field(default=15, gt=0)
    stale_after_minutes: int = Field(default=30, gt=0)
    observation_delay_minutes: int = Field(default=0, ge=0, le=10080)
    resource_count: int = Field(default=1, gt=0, le=20)
    registration_resource_count: int | None = Field(default=None, gt=0, le=20)
    unloading_resource_count: int | None = Field(default=None, gt=0, le=20)
    quality_resource_count: int = Field(default=1, gt=0, le=20)
    weighment_resource_count: int = Field(default=1, gt=0, le=20)
    documentation_resource_count: int | None = Field(default=None, gt=0, le=20)
    events: list[SimulationEvent] | None = Field(default=None, max_length=5000)


class SimulationRunResponse(BaseModel):
    run_id: str
    centre_id: int
    scenario: str = "generated"
    seed: int
    start_time: datetime
    canonical_sequence: list[dict]
    trace: list[dict]
    true_state: dict
    observed_state: dict
    completion_window: dict
    stages: list[dict]
    canonical_stages: list[str]
    canonical_stage_sequence: str
    adaptive_metrics: dict
    baseline_metrics: dict
    comparison: dict


class SimulationMetricsResponse(BaseModel):
    run_id: str
    centre_id: int
    scenario: str = "generated"
    adaptive_metrics: dict
    baseline_metrics: dict
    comparison: dict


class SimulationTraceResponse(BaseModel):
    run_id: str
    centre_id: int
    scenario: str = "generated"
    trace: list[dict]
