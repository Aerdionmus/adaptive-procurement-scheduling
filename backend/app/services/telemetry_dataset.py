from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import ProcurementTelemetry
from app.repositories import procurement_telemetry as telemetry_repository
from app.schemas.procurement_telemetry import STAGES


@dataclass(frozen=True)
class DatasetSplit:
    train: list[dict[str, Any]]
    validation: list[dict[str, Any]]
    test: list[dict[str, Any]]


def _duration(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    return round(seconds / 60, 2) if seconds >= 0 else None


def _timestamp_key(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _valid_completed(row: ProcurementTelemetry) -> bool:
    return (
        row.completion_status.upper() == "COMPLETED"
        and not row.no_show
        and not row.cancellation
        and row.arrival_time is not None
        and row.completion_time is not None
    )


def _row(row: ProcurementTelemetry, stage: str) -> dict[str, Any] | None:
    duration = _duration(
        getattr(row, f"{stage}_start"),
        getattr(row, f"{stage}_end"),
    )
    durations = [
        _duration(getattr(row, f"{name}_start"), getattr(row, f"{name}_end"))
        for name in STAGES
    ]
    elapsed = _duration(row.arrival_time, row.completion_time)
    if elapsed is None or row.arrival_time is None:
        return None
    return {
        "provenance": "REAL_OBSERVED",
        "telemetry_id": row.id,
        "centre_id": row.centre_id,
        "booking_id": row.booking_id,
        "lot_id": row.lot_id,
        "arrival_time": row.arrival_time,
        "arrival_hour": row.arrival_time.hour,
        "day_of_week": row.arrival_time.weekday(),
        "queue_size_at_arrival": row.queue_size_at_arrival,
        "resource_state": row.resource_state,
        "stage": stage,
        "stage_duration_minutes": duration,
        "total_active_service_minutes": (
            round(sum(value for value in durations if value is not None), 2)
            if all(value is not None for value in durations)
            else None
        ),
        "arrival_to_completion_minutes": elapsed,
    }


def prepare_dataset(
    session: Session,
    *,
    centre_id: int | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    rows = telemetry_repository.list_historical_telemetry(
        session,
        centre_id=centre_id,
        limit=limit,
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        if not _valid_completed(row):
            continue
        for stage in STAGES:
            prepared = _row(row, stage)
            if prepared is not None:
                if prepared["stage_duration_minutes"] is not None:
                    result.append(prepared)
        result.append(
            {
                "provenance": "REAL_OBSERVED",
                "telemetry_id": row.id,
                "centre_id": row.centre_id,
                "booking_id": row.booking_id,
                "lot_id": row.lot_id,
                "arrival_time": row.arrival_time,
                "arrival_hour": row.arrival_time.hour,
                "day_of_week": row.arrival_time.weekday(),
                "queue_size_at_arrival": row.queue_size_at_arrival,
                "resource_state": row.resource_state,
                "stage": "arrival_to_completion",
                "stage_duration_minutes": None,
                "total_active_service_minutes": None,
                "arrival_to_completion_minutes": _duration(
                    row.arrival_time, row.completion_time
                ),
            }
        )
    return result


def split_chronologically(rows: list[dict[str, Any]]) -> DatasetSplit:
    ordered = sorted(rows, key=lambda row: (row["arrival_time"], row["telemetry_id"], row["stage"]))
    total = len(ordered)
    train_end = int(total * 0.70)
    validation_end = train_end + int(total * 0.15)
    return DatasetSplit(
        train=ordered[:train_end],
        validation=ordered[train_end:validation_end],
        test=ordered[validation_end:],
    )


def quality_report(session: Session, *, centre_id: int | None = None) -> dict[str, Any]:
    rows = telemetry_repository.list_historical_telemetry(
        session,
        centre_id=centre_id,
        limit=500,
    )
    completed = [row for row in rows if _valid_completed(row)]
    stage_counts = {
        stage: sum(
            _duration(getattr(row, f"{stage}_start"), getattr(row, f"{stage}_end")) is not None
            for row in completed
        )
        for stage in STAGES
    }
    timestamps = [
        _timestamp_key(row.arrival_time)
        for row in rows
        if row.arrival_time is not None
    ]
    complete_stage_rows = sum(
        all(
            _duration(getattr(row, f"{stage}_start"), getattr(row, f"{stage}_end")) is not None
            for stage in STAGES
        )
        for row in completed
    )
    by_centre: dict[str, int] = {}
    by_day: dict[str, int] = {}
    for row in rows:
        by_centre[str(row.centre_id)] = by_centre.get(str(row.centre_id), 0) + 1
        if row.arrival_time is not None:
            key = row.arrival_time.date().isoformat()
            by_day[key] = by_day.get(key, 0) + 1
    valid_count = len(completed)
    return {
        "provenance": "REAL_OBSERVED",
        "total_records": len(rows),
        "valid_completed_records": valid_count,
        "incomplete_records": sum(not _valid_completed(row) and not row.cancellation and not row.no_show for row in rows),
        "cancelled_records": sum(row.cancellation for row in rows),
        "no_show_records": sum(row.no_show for row in rows),
        "valid_labels_per_stage": stage_counts,
        "centres_represented": sorted({row.centre_id for row in rows}),
        "earliest_telemetry_timestamp": min(timestamps) if timestamps else None,
        "latest_telemetry_timestamp": max(timestamps) if timestamps else None,
        "records_by_centre": by_centre,
        "records_by_day": by_day,
        "complete_stage_timestamp_pct": round(100 * complete_stage_rows / valid_count, 2) if valid_count else 0.0,
    }


def readiness_report(session: Session, *, centre_id: int | None = None) -> dict[str, Any]:
    report = quality_report(session, centre_id=centre_id)
    count = report["valid_completed_records"]
    level = "INSUFFICIENT_DATA" if count < 3 else "LOW" if count < 10 else "MEDIUM" if count < 30 else "HIGH"
    return {
        "provenance": "REAL_OBSERVED",
        "status": level,
        "valid_completed_records": count,
        "stage_counts": report["valid_labels_per_stage"],
        "centre_counts": report["records_by_centre"],
    }
