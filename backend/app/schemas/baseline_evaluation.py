from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BaselineMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mae: float | None
    median_absolute_error: float | None
    rmse: float | None
    p90_absolute_error: float | None
    sample_count: int


class BaselineEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance: str
    status: str
    target: str
    method: str
    valid_observation_count: int
    train_count: int
    validation_count: int
    test_count: int
    train_start: datetime | None
    train_end: datetime | None
    validation_start: datetime | None
    validation_end: datetime | None
    test_start: datetime | None
    test_end: datetime | None
    metrics: BaselineMetrics | None
    metrics_by_centre: dict[str, BaselineMetrics]
    observations: list[dict[str, Any]]
