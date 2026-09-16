from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from app.schemas.prediction import ServiceTimePrediction


def adapt_completion_window(
    legacy_window: dict[str, Any],
    *,
    at: datetime,
    prediction: ServiceTimePrediction | None = None,
    prediction_stale: bool = False,
) -> dict[str, Any]:
    """Apply an eligible Phase 2C calibration to a Phase 1 window.

    This function only changes the estimate. It never classifies completion
    or selects a recommendation. Invalid, stale, insufficient, and LOW
    confidence predictions preserve the legacy Phase 1 estimate byte-for-byte
    apart from explicit provenance metadata.
    """
    window = deepcopy(legacy_window)
    if prediction is None or prediction_stale or not _eligible(prediction):
        window["provenance"] = "LEGACY_ESTIMATOR"
        return window

    p50 = float(prediction.p50_minutes)
    p90 = float(prediction.p90_minutes)
    if p90 < p50:
        window["provenance"] = "LEGACY_ESTIMATOR"
        return window

    workload_delay = float(legacy_window.get("workload_delay_minutes", 0))
    baseline_service = float(legacy_window.get("baseline_service_minutes", 0))
    central_minutes = round(workload_delay + p50, 2)
    predictive_latest = round(workload_delay + p90, 2)
    latest_minutes = max(
        float(legacy_window["latest_minutes"]),
        predictive_latest,
    )
    uncertainty = round(latest_minutes - central_minutes, 2)
    window.update(
        {
            "earliest_minutes": central_minutes,
            "latest_minutes": latest_minutes,
            "lower_timestamp": _iso(at + timedelta(minutes=central_minutes)),
            "upper_timestamp": _iso(at + timedelta(minutes=latest_minutes)),
            "p50_timestamp": _iso(at + timedelta(minutes=central_minutes)),
            "p90_timestamp": _iso(at + timedelta(minutes=latest_minutes)),
            "uncertainty_minutes": uncertainty,
            "baseline_service_minutes": round(baseline_service, 2),
            "workload_delay_minutes": round(workload_delay, 2),
            "prediction_adjusted_service_minutes": round(p50, 2),
            "confidence": prediction.confidence.lower(),
            "provenance": "PREDICTIVE_CALIBRATION",
            "prediction_target": prediction.target,
            "prediction_sample_count": prediction.sample_count,
            "prediction_method": prediction.method,
        }
    )
    return window


def _eligible(prediction: ServiceTimePrediction) -> bool:
    return (
        prediction.status == "READY"
        and prediction.confidence in {"MEDIUM", "HIGH"}
        and prediction.p50_minutes is not None
        and prediction.p90_minutes is not None
        and prediction.p50_minutes >= 0
        and prediction.p90_minutes >= 0
    )


def _iso(value: datetime) -> str:
    return value.isoformat()
