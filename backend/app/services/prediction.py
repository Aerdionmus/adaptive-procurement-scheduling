from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from app.models import ProcurementTelemetry
from app.repositories import procurement_telemetry as telemetry_repository
from app.repositories import throughput as throughput_repository
from app.schemas.prediction import (
    ServiceTimePrediction,
    ServiceTimePredictionResponse,
    ThroughputPrediction,
)

STAGES = ("registration", "unloading", "quality", "weighment", "documentation")
HISTORY_LIMIT = 500
MINIMUM_SAMPLES = 3


@dataclass(frozen=True)
class _Sample:
    value: float
    at: datetime


def _duration_minutes(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    return round(seconds / 60, 6) if seconds >= 0 else None


def _valid_completed(row: ProcurementTelemetry) -> bool:
    return (
        row.completion_status.upper() == "COMPLETED"
        and not row.no_show
        and not row.cancellation
        and row.arrival_time is not None
        and row.completion_time is not None
    )


def _stage_duration(row: ProcurementTelemetry, stage: str) -> float | None:
    return _duration_minutes(
        getattr(row, f"{stage}_start"),
        getattr(row, f"{stage}_end"),
    )


def _active_service_duration(row: ProcurementTelemetry) -> float | None:
    durations = [_stage_duration(row, stage) for stage in STAGES]
    if any(duration is None for duration in durations):
        return None
    return round(sum(duration for duration in durations if duration is not None), 6)


def _elapsed_duration(row: ProcurementTelemetry) -> float | None:
    return _duration_minutes(row.arrival_time, row.completion_time)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def _confidence(sample_count: int) -> tuple[str, str]:
    if sample_count < MINIMUM_SAMPLES:
        return "INSUFFICIENT_DATA", "LOW"
    if sample_count < 10:
        return "READY", "LOW"
    if sample_count < 30:
        return "READY", "MEDIUM"
    return "READY", "HIGH"


def _metadata(samples: list[_Sample]) -> tuple[datetime | None, datetime | None]:
    if not samples:
        return None, None
    return samples[0].at, samples[-1].at


def _sample_prediction(
    *,
    centre_id: int,
    target: str,
    samples: list[_Sample],
    fallback_level: str,
    method: str = "RECENT_MEDIAN",
    source: str = "OPERATIONAL_TELEMETRY",
) -> ServiceTimePrediction:
    status, confidence = _confidence(len(samples))
    lookback_start, lookback_end = _metadata(samples)
    values = [sample.value for sample in samples]
    if not samples:
        predicted = p50 = p90 = None
    else:
        predicted = _percentile(values, 0.5)
        p50 = predicted
        p90 = _percentile(values, 0.9)
    return ServiceTimePrediction(
        centre_id=centre_id,
        target=target,
        predicted_minutes=predicted,
        p50_minutes=p50,
        p90_minutes=p90,
        status=status,
        confidence=confidence,
        sample_count=len(samples),
        method=method,
        fallback_level=fallback_level,
        lookback_start=lookback_start,
        lookback_end=lookback_end,
        source=source,
        reference_context_used=[],
    )


def _historical_rows(
    session: Session,
    centre_id: int | None,
) -> list[ProcurementTelemetry]:
    return [
        row
        for row in telemetry_repository.list_historical_telemetry(
            session,
            centre_id=centre_id,
            limit=HISTORY_LIMIT,
        )
        if _valid_completed(row)
    ]


def _samples(
    rows: list[ProcurementTelemetry],
    value_getter: Callable[[ProcurementTelemetry], float | None],
) -> list[_Sample]:
    result: list[_Sample] = []
    for row in rows:
        value = value_getter(row)
        if value is not None and row.arrival_time is not None:
            result.append(_Sample(value, row.arrival_time))
    return result


def _existing_throughput_samples(
    session: Session,
    centre_id: int,
) -> list[_Sample]:
    snapshot = throughput_repository.get_latest_snapshot(session, centre_id)
    if snapshot is None:
        return []
    value = float(Decimal(snapshot.avg_minutes_per_farmer))
    return [_Sample(value, snapshot.snapshot_at)]


def predict_service_times(
    session: Session,
    centre_id: int,
) -> ServiceTimePredictionResponse:
    centre_rows = _historical_rows(session, centre_id)
    global_rows = _historical_rows(session, None)
    centre_overall = _samples(centre_rows, _active_service_duration)
    predictions: list[ServiceTimePrediction] = []

    for stage in STAGES:
        centre_stage = _samples(
            centre_rows,
            lambda row, stage=stage: _stage_duration(row, stage),
        )
        global_stage = _samples(
            global_rows,
            lambda row, stage=stage: _stage_duration(row, stage),
        )
        samples = centre_stage
        fallback_level = "CENTRE_STAGE"
        if len(samples) < MINIMUM_SAMPLES:
            samples = centre_overall
            fallback_level = "CENTRE_OVERALL"
        if len(samples) < MINIMUM_SAMPLES:
            samples = global_stage
            fallback_level = "GLOBAL_STAGE"
        if len(samples) < MINIMUM_SAMPLES:
            samples = _existing_throughput_samples(session, centre_id)
            fallback_level = "EXISTING_THROUGHPUT"
            method = "EXISTING_THROUGHPUT_FALLBACK"
            source = "THROUGHPUT_SNAPSHOT"
        else:
            method = "RECENT_MEDIAN"
            source = "OPERATIONAL_TELEMETRY"
        predictions.append(
            _sample_prediction(
                centre_id=centre_id,
                target=stage,
                samples=samples,
                fallback_level=fallback_level,
                method=method,
                source=source,
            )
        )

    active_samples = centre_overall
    active_fallback = "CENTRE_OVERALL"
    if len(active_samples) < MINIMUM_SAMPLES:
        active_samples = _samples(global_rows, _active_service_duration)
        active_fallback = "GLOBAL_STAGE"
    if len(active_samples) < MINIMUM_SAMPLES:
        active_samples = _existing_throughput_samples(session, centre_id)
        active_fallback = "EXISTING_THROUGHPUT"
        active_method = "EXISTING_THROUGHPUT_FALLBACK"
        active_source = "THROUGHPUT_SNAPSHOT"
    else:
        active_method = "RECENT_MEDIAN"
        active_source = "OPERATIONAL_TELEMETRY"
    predictions.append(
        _sample_prediction(
            centre_id=centre_id,
            target="total_active_service",
            samples=active_samples,
            fallback_level=active_fallback,
            method=active_method,
            source=active_source,
        )
    )

    elapsed_samples = _samples(centre_rows, _elapsed_duration)
    if len(elapsed_samples) < MINIMUM_SAMPLES:
        elapsed_samples = _samples(global_rows, _elapsed_duration)
        elapsed_fallback = "GLOBAL_STAGE"
    else:
        elapsed_fallback = "CENTRE_OVERALL"
    if len(elapsed_samples) < MINIMUM_SAMPLES:
        elapsed_samples = _existing_throughput_samples(session, centre_id)
        elapsed_fallback = "EXISTING_THROUGHPUT"
        elapsed_method = "EXISTING_THROUGHPUT_FALLBACK"
        elapsed_source = "THROUGHPUT_SNAPSHOT"
    else:
        elapsed_method = "RECENT_MEDIAN"
        elapsed_source = "OPERATIONAL_TELEMETRY"
    predictions.append(
        _sample_prediction(
            centre_id=centre_id,
            target="arrival_to_completion",
            samples=elapsed_samples,
            fallback_level=elapsed_fallback,
            method=elapsed_method,
            source=elapsed_source,
        )
    )
    return ServiceTimePredictionResponse(centre_id=centre_id, predictions=predictions)


def predict_throughput(session: Session, centre_id: int) -> ThroughputPrediction:
    centre_rows = _historical_rows(session, centre_id)
    samples = _samples(centre_rows, _active_service_duration)
    fallback_level = "CENTRE_OVERALL"
    if len(samples) < MINIMUM_SAMPLES:
        samples = _existing_throughput_samples(session, centre_id)
        fallback_level = "EXISTING_THROUGHPUT"
        method = "EXISTING_THROUGHPUT_FALLBACK"
        source = "THROUGHPUT_SNAPSHOT"
    else:
        method = "RECENT_MEDIAN"
        source = "OPERATIONAL_TELEMETRY"
    status, confidence = _confidence(len(samples))
    lookback_start, lookback_end = _metadata(samples)
    if not samples:
        p50 = p90 = pace = lots_per_hour = None
    else:
        p50 = _percentile([sample.value for sample in samples], 0.5)
        p90 = _percentile([sample.value for sample in samples], 0.9)
        pace = p50
        lots_per_hour = round(60 / pace, 4) if pace > 0 else None
    return ThroughputPrediction(
        centre_id=centre_id,
        predicted_minutes_per_lot=pace,
        predicted_lots_per_hour=lots_per_hour,
        p50_minutes_per_lot=p50,
        p90_minutes_per_lot=p90,
        status=status,
        confidence=confidence,
        sample_count=len(samples),
        method=method,
        fallback_level=fallback_level,
        lookback_start=lookback_start,
        lookback_end=lookback_end,
        source=source,
        reference_context_used=[],
    )
