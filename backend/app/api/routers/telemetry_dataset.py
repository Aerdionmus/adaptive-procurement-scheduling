from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import ensure_centre_scope, require_admin, require_centre_staff_or_admin
from app.db.session import get_db
from app.models import User
from app.schemas.telemetry_dataset import (
    TelemetryDatasetResponse,
    TelemetryQualityResponse,
    TelemetryReadinessResponse,
)
from app.services import telemetry_dataset

router = APIRouter()


@router.get("/all/quality", response_model=TelemetryQualityResponse)
async def get_all_telemetry_quality(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TelemetryQualityResponse:
    return telemetry_dataset.quality_report(session)


@router.get("/all/readiness", response_model=TelemetryReadinessResponse)
async def get_all_telemetry_readiness(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TelemetryReadinessResponse:
    return telemetry_dataset.readiness_report(session)


@router.get("/all/dataset", response_model=TelemetryDatasetResponse)
async def get_all_telemetry_dataset(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TelemetryDatasetResponse:
    return {
        "provenance": "REAL_OBSERVED",
        "rows": telemetry_dataset.prepare_dataset(session),
    }


@router.get(
    "/centres/{centre_id}/quality",
    response_model=TelemetryQualityResponse,
)
async def get_telemetry_quality(
    centre_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> TelemetryQualityResponse:
    ensure_centre_scope(current_user, centre_id)
    return telemetry_dataset.quality_report(session, centre_id=centre_id)


@router.get(
    "/centres/{centre_id}/readiness",
    response_model=TelemetryReadinessResponse,
)
async def get_telemetry_readiness(
    centre_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> TelemetryReadinessResponse:
    ensure_centre_scope(current_user, centre_id)
    return telemetry_dataset.readiness_report(session, centre_id=centre_id)


@router.get(
    "/centres/{centre_id}/dataset",
    response_model=TelemetryDatasetResponse,
)
async def get_telemetry_dataset(
    centre_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> TelemetryDatasetResponse:
    ensure_centre_scope(current_user, centre_id)
    return {
        "provenance": "REAL_OBSERVED",
        "rows": telemetry_dataset.prepare_dataset(session, centre_id=centre_id),
    }
