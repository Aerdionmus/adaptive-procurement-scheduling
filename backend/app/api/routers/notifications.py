from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import ensure_booking_access, get_current_user
from app.api.deps import ensure_centre_scope, require_centre_staff_or_admin
from app.db.session import get_db
from app.models import NotificationIntentStatus, User
from app.repositories import bookings as booking_repository
from app.repositories import notification_intents
from app.schemas.notification_intent import (
    NotificationDeliveryResponse,
    NotificationIntentResponse,
)
from app.services.notification_delivery import NotificationDeliveryService

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


@router.post(
    "/intents/{intent_id}/deliver",
    response_model=NotificationDeliveryResponse,
)
async def deliver_notification_intent(
    intent_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> NotificationDeliveryResponse:
    intent = notification_intents.get_by_id(session, intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="Notification intent not found")
    ensure_centre_scope(current_user, intent.centre_id)
    outcome = NotificationDeliveryService().deliver(session, intent_id)
    return NotificationDeliveryResponse(
        intent_id=outcome.intent.id,
        notification_type=outcome.intent.notification_type.value,
        channel=outcome.intent.channel.value,
        status=NotificationIntentStatus(outcome.intent.status).value,
        success=outcome.result.success,
        reference_id=outcome.result.reference_id,
        failure_reason=outcome.result.failure_reason,
        already_processed=outcome.already_processed,
    )
