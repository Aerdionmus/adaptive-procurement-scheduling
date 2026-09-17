from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


PredictionStatus = Literal["READY", "INSUFFICIENT_DATA"]
PredictionConfidence = Literal["LOW", "MEDIUM", "HIGH"]
PredictionTarget = Literal[
    "registration",
    "unloading",
    "quality",
    "weighment",
    "documentation",
    "total_active_service",
    "arrival_to_completion",
]


class ServiceTimePrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    centre_id: int
    target: PredictionTarget
    predicted_minutes: float | None
    p50_minutes: float | None
    p90_minutes: float | None
    status: PredictionStatus
    confidence: PredictionConfidence
    sample_count: int
    method: Literal["RECENT_MEDIAN", "EXISTING_THROUGHPUT_FALLBACK"]
    fallback_level: Literal[
        "CENTRE_STAGE",
        "CENTRE_OVERALL",
        "GLOBAL_STAGE",
        "EXISTING_THROUGHPUT",
        "NONE",
    ]
    lookback_start: datetime | None
    lookback_end: datetime | None
    source: Literal["OPERATIONAL_TELEMETRY", "THROUGHPUT_SNAPSHOT"]
    reference_context_used: list[str]


class ThroughputPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    centre_id: int
    predicted_minutes_per_lot: float | None
    predicted_lots_per_hour: float | None
    p50_minutes_per_lot: float | None
    p90_minutes_per_lot: float | None
    status: PredictionStatus
    confidence: PredictionConfidence
    sample_count: int
    method: Literal["RECENT_MEDIAN", "EXISTING_THROUGHPUT_FALLBACK"]
    fallback_level: Literal["CENTRE_OVERALL", "EXISTING_THROUGHPUT", "NONE"]
    lookback_start: datetime | None
    lookback_end: datetime | None
    source: Literal["OPERATIONAL_TELEMETRY", "THROUGHPUT_SNAPSHOT"]
    reference_context_used: list[str]


class ServiceTimePredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    centre_id: int
    predictions: list[ServiceTimePrediction]
