from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import procurement as procurement_repository
from app.schemas.procurement import ProcurementCentreResponse, ProcurementSlotResponse
from app.schemas.procurement_context import CentreAgriculturalContextResponse
from app.services import procurement_context as procurement_context_service

router = APIRouter()


@router.get("/", response_model=list[ProcurementCentreResponse])
async def list_centres(
    session: Session = Depends(get_db),
) -> list[ProcurementCentreResponse]:
    return procurement_repository.list_active_centres(session)


@router.get("/{centre_id}/slots", response_model=list[ProcurementSlotResponse])
async def list_centre_slots(
    centre_id: int,
    session: Session = Depends(get_db),
) -> list[ProcurementSlotResponse]:
    centre = procurement_repository.get_centre(session, centre_id)
    if centre is None:
        raise HTTPException(status_code=404, detail="Procurement centre not found")
    if not centre.active:
        raise HTTPException(status_code=409, detail="Procurement centre is inactive")
    return procurement_repository.list_usable_slots(session, centre_id)


@router.get(
    "/{centre_id}/reference-context",
    response_model=CentreAgriculturalContextResponse,
)
async def get_centre_reference_context(
    centre_id: int,
    dataset_type: str | None = None,
    metric_name: str | None = None,
    season_or_period: str | None = None,
    session: Session = Depends(get_db),
) -> CentreAgriculturalContextResponse:
    """Read-only agricultural/statistical context for this centre's
    district (Milestone 2). Unauthenticated, matching the rest of this
    router (centre listing and slot listing are also public); it exposes
    nothing more sensitive than what GET /api/reference/ already serves to
    any authenticated user.

    Never affects, and is never affected by, booking/queue/scheduling for
    this centre - see app/services/procurement_context.py for why that
    separation is structural rather than just documented.
    """
    try:
        context = procurement_context_service.get_centre_agricultural_context(
            session,
            centre_id,
            dataset_type=dataset_type,
            metric_name=metric_name,
            season_or_period=season_or_period,
        )
    except procurement_context_service.ProcurementContextError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    return context
