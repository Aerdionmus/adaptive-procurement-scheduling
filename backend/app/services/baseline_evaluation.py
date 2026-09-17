from __future__ import annotations

from datetime import datetime
from math import sqrt
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.models import ProcurementTelemetry
from app.repositories import procurement_telemetry as telemetry_repository
from app.services.prediction import (
    HISTORY_LIMIT,
    MINIMUM_SAMPLES,
    _Sample,
    is_prediction_eligible,
    recent_median,
    select_fallback_samples,
    throughput_fallback_samples,
)

MINIMUM_OBSERVATIONS = MINIMUM_SAMPLES
PROVENANCE = "REAL_OBSERVED"
TARGET = "arrival_to_completion_minutes"


def _elapsed(row: ProcurementTelemetry) -> float | None:
    if row.arrival_time is None or row.completion_time is None:
        return None
    seconds = (row.completion_time - row.arrival_time).total_seconds()
    return round(seconds / 60, 6) if seconds >= 0 else None


def _valid(row: ProcurementTelemetry) -> bool:
    return (
        row.completion_status.upper() == "COMPLETED"
        and is_prediction_eligible(row)
        and not row.no_show
        and not row.cancellation
        and row.arrival_time is not None
        and row.completion_time is not None
        and _elapsed(row) is not None
    )


def _observations(
    session: Session,
    centre_id: int | None,
) -> list[dict[str, Any]]:
    rows = telemetry_repository.list_historical_telemetry(
        session,
        centre_id=centre_id,
        limit=HISTORY_LIMIT,
    )
    result = []
    for row in rows:
        if not _valid(row):
            continue
        assert row.arrival_time is not None
        result.append(
            {
                "provenance": PROVENANCE,
                "telemetry_id": row.id,
                "booking_id": row.booking_id,
                "centre_id": row.centre_id,
                "arrival_time": row.arrival_time,
                "arrival_hour": row.arrival_time.hour,
                "day_of_week": row.arrival_time.weekday(),
                "queue_size_at_arrival": row.queue_size_at_arrival,
                "completion_time": row.completion_time,
                "arrival_to_completion_minutes": _elapsed(row),
            }
        )
    return sorted(result, key=lambda item: (item["arrival_time"], item["telemetry_id"]))


def _split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    train_end = int(len(rows) * 0.70)
    validation_end = train_end + int(len(rows) * 0.15)
    return rows[:train_end], rows[train_end:validation_end], rows[validation_end:]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _metrics(errors: list[float]) -> dict[str, Any]:
    if not errors:
        return {
            "mae": None,
            "median_absolute_error": None,
            "rmse": None,
            "p90_absolute_error": None,
            "sample_count": 0,
        }
    return {
        "mae": round(sum(errors) / len(errors), 6),
        "median_absolute_error": round(median(errors), 6),
        "rmse": round(sqrt(sum(error * error for error in errors) / len(errors)), 6),
        "p90_absolute_error": round(_percentile(errors, 0.9), 6),
        "sample_count": len(errors),
    }


def _period(rows: list[dict[str, Any]]) -> tuple[datetime | None, datetime | None]:
    if not rows:
        return None, None
    return rows[0]["arrival_time"], rows[-1]["arrival_time"]


def _elapsed_samples(rows: list[dict[str, Any]]) -> list[_Sample]:
    return [
        _Sample(row["arrival_to_completion_minutes"], row["arrival_time"])
        for row in rows
    ]


def _available_before(
    rows: list[dict[str, Any]],
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in rows
        if (candidate["arrival_time"], candidate["telemetry_id"])
        < (row["arrival_time"], row["telemetry_id"])
    ]


def _throughput_fallback(
    session: Session,
    centre_id: int,
    before: datetime,
) -> list[_Sample]:
    return throughput_fallback_samples(
        session,
        centre_id,
        as_of=before,
        strict_before=True,
    )


def evaluate_completion_time(
    session: Session,
    *,
    centre_id: int | None = None,
) -> dict[str, Any]:
    rows = _observations(session, centre_id)
    global_rows = _observations(session, None)
    train, validation, test = _split(rows)
    if len(rows) < MINIMUM_OBSERVATIONS:
        return {
            "provenance": PROVENANCE,
            "status": "INSUFFICIENT_DATA",
            "target": TARGET,
            "method": "RECENT_MEDIAN",
            "valid_observation_count": len(rows),
            "train_count": len(train),
            "validation_count": len(validation),
            "test_count": len(test),
            "train_start": _period(train)[0],
            "train_end": _period(train)[1],
            "validation_start": _period(validation)[0],
            "validation_end": _period(validation)[1],
            "test_start": _period(test)[0],
            "test_end": _period(test)[1],
            "metrics": None,
            "metrics_by_centre": {},
            "observations": rows,
        }

    history = train[:]
    errors = []
    test_errors_by_centre: dict[str, list[float]] = {}
    for row in validation:
        centre_samples = _elapsed_samples(
            [item for item in history if item["centre_id"] == row["centre_id"]]
            [-HISTORY_LIMIT:]
        )
        global_samples = _elapsed_samples(
            _available_before(global_rows, row)[-HISTORY_LIMIT:]
        )
        samples, _ = select_fallback_samples(
            centre_samples,
            global_samples,
            _throughput_fallback(session, row["centre_id"], row["arrival_time"]),
        )
        if not samples:
            continue
        prediction = float(recent_median([sample.value for sample in samples]))
        errors.append(abs(prediction - row["arrival_to_completion_minutes"]))
        history.append(row)
    test_history = history[:]
    errors = []
    for row in test:
        centre_samples = _elapsed_samples(
            [item for item in test_history if item["centre_id"] == row["centre_id"]]
            [-HISTORY_LIMIT:]
        )
        global_samples = _elapsed_samples(
            _available_before(global_rows, row)[-HISTORY_LIMIT:]
        )
        samples, _ = select_fallback_samples(
            centre_samples,
            global_samples,
            _throughput_fallback(session, row["centre_id"], row["arrival_time"]),
        )
        if not samples:
            continue
        prediction = float(recent_median([sample.value for sample in samples]))
        error = abs(prediction - row["arrival_to_completion_minutes"])
        errors.append(error)
        # RECENT_MEDIAN is online in production: completed observations become
        # available to the next prediction, but never to the current one.
        test_history.append(row)
        key = str(row["centre_id"])
        test_errors_by_centre.setdefault(key, []).append(error)

    return {
        "provenance": PROVENANCE,
        "status": "READY" if test else "INSUFFICIENT_DATA",
        "target": TARGET,
        "method": "RECENT_MEDIAN",
        "valid_observation_count": len(rows),
        "train_count": len(train),
        "validation_count": len(validation),
        "test_count": len(test),
        "train_start": _period(train)[0],
        "train_end": _period(train)[1],
        "validation_start": _period(validation)[0],
        "validation_end": _period(validation)[1],
        "test_start": _period(test)[0],
        "test_end": _period(test)[1],
        "metrics": _metrics(errors) if test else None,
        "metrics_by_centre": {
            key: _metrics(values)
            for key, values in sorted(test_errors_by_centre.items())
            if len(values) >= MINIMUM_OBSERVATIONS
        },
        "observations": rows,
    }
