from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
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


def get_by_id(session: Session, intent_id: int) -> NotificationIntent | None:
    return session.get(NotificationIntent, intent_id)


DEFAULT_PROCESSING_STALE_AFTER = timedelta(minutes=5)


def claim_pending(
    session: Session,
    intent_id: int,
    *,
    stale_after: timedelta = DEFAULT_PROCESSING_STALE_AFTER,
) -> NotificationIntent | None:
    stale_before = datetime.now(timezone.utc) - stale_after
    result = session.execute(
        update(NotificationIntent)
        .where(
            NotificationIntent.id == intent_id,
            (NotificationIntent.status == "PENDING")
            | (
                (NotificationIntent.status == "PROCESSING")
                & (NotificationIntent.processing_started_at < stale_before)
            ),
        )
        .values(
            status="PROCESSING",
            processing_started_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    if result.rowcount == 0:
        return None
    return get_by_id(session, intent_id)


def mark_delivered(
    session: Session, intent_id: int, provider_reference: str | None
) -> NotificationIntent:
    intent = get_by_id(session, intent_id)
    if intent is None:
        raise ValueError("Notification intent not found")
    intent.status = "DELIVERED"
    intent.delivered_at = datetime.now(timezone.utc)
    intent.provider_reference = provider_reference
    intent.failure_reason = None
    session.commit()
    session.refresh(intent)
    return intent


def mark_failed(session: Session, intent_id: int, failure_reason: str) -> NotificationIntent:
    intent = get_by_id(session, intent_id)
    if intent is None:
        raise ValueError("Notification intent not found")
    intent.status = "FAILED"
    intent.failure_reason = failure_reason
    session.commit()
    session.refresh(intent)
    return intent
