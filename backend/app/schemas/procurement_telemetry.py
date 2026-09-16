from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


STAGES = ("registration", "unloading", "quality", "weighment", "documentation")


class ProcurementTelemetryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lot_id: str = Field(min_length=1, max_length=100)
    booking_id: int | None = Field(default=None, gt=0)
    centre_id: int = Field(gt=0)
    scheduled_slot: str | None = Field(default=None, max_length=100)
    arrival_time: datetime | None = None
    queue_size_at_arrival: int | None = Field(default=None, ge=0)
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    unloading_start: datetime | None = None
    unloading_end: datetime | None = None
    quality_start: datetime | None = None
    quality_end: datetime | None = None
    weighment_start: datetime | None = None
    weighment_end: datetime | None = None
    documentation_start: datetime | None = None
    documentation_end: datetime | None = None
    completion_time: datetime | None = None
    resource_state: dict[str, Any] | None = None
    no_show: bool = False
    cancellation: bool = False
    completion_status: str = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_event_consistency(self) -> "ProcurementTelemetryCreate":
        previous: datetime | None = self.arrival_time
        for stage in STAGES:
            start = getattr(self, f"{stage}_start")
            end = getattr(self, f"{stage}_end")
            if end is not None and start is None:
                raise ValueError(f"{stage}_end requires {stage}_start")
            if start is not None and end is not None and end < start:
                raise ValueError(f"{stage}_end must not precede {stage}_start")
            if start is not None and previous is not None and start < previous:
                raise ValueError(f"{stage}_start must not precede the prior event")
            if end is not None:
                previous = end
            elif start is not None:
                previous = start
        if self.completion_time is not None and previous is not None and self.completion_time < previous:
            raise ValueError("completion_time must not precede the final stage event")
        if self.no_show and any(getattr(self, f"{stage}_start") is not None for stage in STAGES):
            raise ValueError("no-show telemetry cannot contain stage timestamps")
        if self.cancellation and self.completion_time is not None:
            raise ValueError("cancelled telemetry cannot contain completion_time")
        return self


class ProcurementTelemetryResponse(ProcurementTelemetryCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    registration_duration_minutes: float | None = None
    unloading_duration_minutes: float | None = None
    quality_duration_minutes: float | None = None
    weighment_duration_minutes: float | None = None
    documentation_duration_minutes: float | None = None
    total_cycle_minutes: float | None = None
