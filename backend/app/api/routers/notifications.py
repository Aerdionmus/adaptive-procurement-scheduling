from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import ensure_booking_access, get_current_user
from app.db.session import get_db
from app.models import User
from app.repositories import bookings as booking_repository
from app.repositories import notification_intents
from app.schemas.notification_intent import NotificationIntentResponse

router = APIRouter()


@router.get("/")
async def notifications_placeholder() -> dict[str, str]:
    return {"status": "notifications module foundation ready"}


@router.get(
    "/bookings/{booking_id}/intents",
    response_model=list[NotificationIntentResponse],
)
async def get_booking_notification_intents(
    booking_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NotificationIntentResponse]:
    booking = booking_repository.get_booking(session, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    ensure_booking_access(
        current_user, farmer_id=booking.farmer_id, centre_id=booking.centre_id
    )
    return notification_intents.list_for_booking(session, booking_id)
