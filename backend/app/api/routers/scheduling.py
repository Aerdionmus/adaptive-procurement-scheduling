from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.scheduling import SchedulingAssessmentResponse
from app.services import scheduling as scheduling_service

router = APIRouter()


def _raise_scheduling_error(error: scheduling_service.SchedulingError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.get("/bookings/{booking_id}", response_model=SchedulingAssessmentResponse)
async def get_booking_assessment(
    booking_id: int,
    session: Session = Depends(get_db),
) -> SchedulingAssessmentResponse:
    try:
        return scheduling_service.assess_booking(session, booking_id)
    except scheduling_service.SchedulingError as error:
        _raise_scheduling_error(error)


@router.get("/centres/{centre_id}", response_model=list[SchedulingAssessmentResponse])
async def get_centre_assessments(
    centre_id: int,
    session: Session = Depends(get_db),
) -> list[SchedulingAssessmentResponse]:
    try:
        return scheduling_service.assess_centre(session, centre_id)
    except scheduling_service.SchedulingError as error:
        _raise_scheduling_error(error)
