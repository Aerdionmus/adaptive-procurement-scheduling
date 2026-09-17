from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import NotificationIntent


def get_by_deduplication_key(
    session: Session,
    *,
    decision_id: int,
    notification_type: str,
    channel: str,
) -> NotificationIntent | None:
    return session.scalar(
        select(NotificationIntent).where(
            NotificationIntent.decision_id == decision_id,
            NotificationIntent.notification_type == notification_type,
            NotificationIntent.channel == channel,
        )
    )


def create_intent(session: Session, intent: NotificationIntent) -> NotificationIntent:
    session.add(intent)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_by_deduplication_key(
            session,
            decision_id=intent.decision_id,
            notification_type=intent.notification_type.value,
            channel=intent.channel.value,
        )
        if existing is None:
            raise
        return existing
    session.refresh(intent)
    return intent


def list_for_booking(session: Session, booking_id: int) -> list[NotificationIntent]:
    return list(
        session.scalars(
            select(NotificationIntent)
            .where(NotificationIntent.booking_id == booking_id)
            .order_by(NotificationIntent.created_at.asc(), NotificationIntent.id.asc())
        )
    )
