from app.models import (
    NotificationIntent,
    NotificationIntentChannel,
    NotificationIntentType,
)
from app.repositories import notification_intents as intent_repository
from app.repositories import bookings as booking_repository
from app.models import SchedulingDecision


_NOTIFICATION_TYPES = {
    "AT_RISK_PREDICTED_COMPLETION": NotificationIntentType.FARMER_SLOT_AT_RISK,
    "DELAYED_NEW_SLOT_AVAILABLE": NotificationIntentType.FARMER_NEW_SLOT_PROPOSED,
    "DELAYED_ALTERNATE_CENTRE_AVAILABLE": (
        NotificationIntentType.FARMER_ALTERNATE_CENTRE_PROPOSED
    ),
}


def create_for_decision(
    session,
    decision: SchedulingDecision,
) -> NotificationIntent | None:
    notification_type = _NOTIFICATION_TYPES.get(decision.reason_code)
    if notification_type is None:
        return None

    channel = NotificationIntentChannel.IN_APP
    existing = intent_repository.get_by_deduplication_key(
        session,
        decision_id=decision.id,
        notification_type=notification_type.value,
        channel=channel.value,
    )
    if existing is not None:
        return existing

    booking = booking_repository.get_booking(session, decision.booking_id)
    if booking is None:
        raise ValueError("Scheduling decision booking is required")
    payload = {
        "decision_id": decision.id,
        "booking_id": decision.booking_id,
        "centre_id": decision.centre_id,
        "farmer_id": booking.farmer_id,
        "notification_type": notification_type.value,
        "reason_code": decision.reason_code,
        "recommendation": decision.recommendation,
        "explanation": decision.explanation,
        "recommended_slot_id": decision.recommended_slot_id,
        "recommended_centre_id": decision.recommended_centre_id,
    }
    return intent_repository.create_intent(
        session,
        NotificationIntent(
            decision_id=decision.id,
            booking_id=decision.booking_id,
            centre_id=decision.centre_id,
            farmer_id=payload["farmer_id"],
            notification_type=notification_type,
            channel=channel,
            payload=payload,
        ),
    )
