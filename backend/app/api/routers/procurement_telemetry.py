from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import ensure_centre_scope, require_centre_staff_or_admin
from app.db.session import get_db
from app.models import ProcurementTelemetry, User
from app.repositories import procurement_telemetry as telemetry_repository
from app.schemas.procurement_telemetry import (
    ProcurementTelemetryCreate,
    ProcurementTelemetryResponse,
)

router = APIRouter()


def _duration(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    return round(seconds / 60, 2) if seconds >= 0 else None


def _response(row: ProcurementTelemetry) -> ProcurementTelemetryResponse:
    values = {
        column.name: getattr(row, column.name)
        for column in ProcurementTelemetry.__table__.columns
        if column.name != "id"
    }
    values["id"] = row.id
    for stage in ("registration", "unloading", "quality", "weighment", "documentation"):
        values[f"{stage}_duration_minutes"] = _duration(
            getattr(row, f"{stage}_start"), getattr(row, f"{stage}_end")
        )
    values["total_cycle_minutes"] = _duration(row.arrival_time, row.completion_time)
    return ProcurementTelemetryResponse.model_validate(values)


@router.post("/", response_model=ProcurementTelemetryResponse, status_code=status.HTTP_201_CREATED)
async def create_procurement_telemetry(
    data: ProcurementTelemetryCreate,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> ProcurementTelemetryResponse:
    ensure_centre_scope(current_user, data.centre_id)
    return _response(telemetry_repository.create_telemetry(session, data))


@router.get("/centres/{centre_id}", response_model=list[ProcurementTelemetryResponse])
async def list_procurement_telemetry(
    centre_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> list[ProcurementTelemetryResponse]:
    ensure_centre_scope(current_user, centre_id)
    return [_response(row) for row in telemetry_repository.list_telemetry(session, centre_id)]


@router.get("/{telemetry_id}", response_model=ProcurementTelemetryResponse)
async def get_procurement_telemetry(
    telemetry_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> ProcurementTelemetryResponse:
    row = telemetry_repository.get_telemetry(session, telemetry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Procurement telemetry not found")
    ensure_centre_scope(current_user, row.centre_id)
    return _response(row)
