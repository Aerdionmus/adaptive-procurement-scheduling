from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TelemetryDatasetRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance: str
    telemetry_id: int
    centre_id: int
    booking_id: int | None
    lot_id: str
    arrival_time: datetime
    arrival_hour: int
    day_of_week: int
    queue_size_at_arrival: int | None
    resource_state: dict[str, Any] | None
    stage: str
    stage_duration_minutes: float | None
    total_active_service_minutes: float | None
    arrival_to_completion_minutes: float


class TelemetryDatasetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance: str
    rows: list[TelemetryDatasetRow]


class TelemetryReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance: str
    status: str
    valid_completed_records: int
    stage_counts: dict[str, int]
    centre_counts: dict[str, int]


class TelemetryQualityResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    provenance: str
    total_records: int
    valid_completed_records: int
    incomplete_records: int
    cancelled_records: int
    no_show_records: int
    valid_labels_per_stage: dict[str, int]
    centres_represented: list[int]
    earliest_telemetry_timestamp: datetime | None
    latest_telemetry_timestamp: datetime | None
    records_by_centre: dict[str, int]
    records_by_day: dict[str, int]
    complete_stage_timestamp_pct: float
