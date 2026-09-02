from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import bookings as booking_repository
from app.schemas.procurement import BookingCreate, BookingResponse
from app.services.bookings import BookingError, create_booking as create_booking_service


router = APIRouter()


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking_data: BookingCreate,
    session: Session = Depends(get_db),
) -> BookingResponse:
    try:
        return create_booking_service(session, booking_data)
    except BookingError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: int,
    session: Session = Depends(get_db),
) -> BookingResponse:
    booking = booking_repository.get_booking(session, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking
