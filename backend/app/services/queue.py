from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import BookingStatus, QueueEntry, QueueStatus
from app.repositories import bookings as booking_repository
from app.repositories import procurement as procurement_repository
from app.repositories import queue as queue_repository
from app.services import throughput as throughput_service


@dataclass
class QueueError(Exception):
    detail: str
    status_code: int


def check_in_booking(session: Session, booking_id: int, centre_id: int) -> QueueEntry:
    try:
        centre = procurement_repository.get_centre_for_update(session, centre_id)
        if centre is None:
            raise QueueError("Procurement centre not found", 404)
        if not centre.active:
            raise QueueError("Procurement centre is inactive", 409)

        booking = booking_repository.get_booking_for_update(session, booking_id)
        if booking is None:
            raise QueueError("Booking not found", 404)
        if booking.centre_id != centre.id:
            raise QueueError("Booking does not belong to the selected centre", 422)
        if queue_repository.get_queue_entry_for_booking(session, booking.id) is not None:
            raise QueueError("Booking already has a queue entry", 409)
        if booking.status != BookingStatus.BOOKED:
            raise QueueError("Booking is not eligible for check-in", 409)

        queue_entry = queue_repository.create_queue_entry(
            session,
            QueueEntry(
                centre_id=centre.id,
                booking_id=booking.id,
                token_number=queue_repository.next_token_number(session, centre.id),
                queue_status=QueueStatus.WAITING,
                checked_in_at=datetime.now(timezone.utc),
            ),
        )
        booking.status = BookingStatus.IN_QUEUE
        session.commit()
        session.refresh(queue_entry)
        return queue_entry
    except Exception:
        session.rollback()
        raise


def list_live_queue(session: Session, centre_id: int) -> list[QueueEntry]:
    centre = procurement_repository.get_centre(session, centre_id)
    if centre is None:
        raise QueueError("Procurement centre not found", 404)
    if not centre.active:
        raise QueueError("Procurement centre is inactive", 409)
    return queue_repository.list_live_queue(session, centre_id)


def call_next_farmer(session: Session, centre_id: int) -> QueueEntry:
    try:
        centre = procurement_repository.get_centre_for_update(session, centre_id)
        if centre is None:
            raise QueueError("Procurement centre not found", 404)
        if not centre.active:
            raise QueueError("Procurement centre is inactive", 409)

        queue_entry = queue_repository.get_next_waiting_for_update(session, centre.id)
        if queue_entry is None:
            raise QueueError("No waiting farmers in this queue", 409)

        queue_entry.queue_status = QueueStatus.CALLED
        queue_entry.called_at = datetime.now(timezone.utc)
        queue_entry.booking.status = BookingStatus.IN_QUEUE
        session.commit()
        session.refresh(queue_entry)
        return queue_entry
    except Exception:
        session.rollback()
        raise


def start_serving(session: Session, queue_entry_id: int) -> QueueEntry:
    return _transition_queue_entry(
        session,
        queue_entry_id,
        allowed_statuses=(QueueStatus.CALLED,),
        target_status=QueueStatus.SERVING,
        booking_status=BookingStatus.PROCESSING,
        set_served_at=True,
    )


def complete_service(session: Session, queue_entry_id: int) -> QueueEntry:
    queue_entry = _transition_queue_entry(
        session,
        queue_entry_id,
        allowed_statuses=(QueueStatus.SERVING,),
        target_status=QueueStatus.DONE,
        booking_status=BookingStatus.COMPLETED,
    )
    # Every completion is a fresh throughput data point, so keep the
    # centre's snapshot current as part of the same workflow instead of
    # requiring a separate background job for this prototype. This is a
    # best-effort refresh: recalculate_throughput() itself decides whether
    # there's enough history yet, and simply leaves the existing snapshot
    # (or the ETA service's fallback default) in place if not.
    throughput_service.recalculate_throughput(session, queue_entry.centre_id)
    return queue_entry


def mark_no_show(session: Session, queue_entry_id: int) -> QueueEntry:
    return _transition_queue_entry(
        session,
        queue_entry_id,
        allowed_statuses=(QueueStatus.WAITING, QueueStatus.CALLED),
        target_status=QueueStatus.NO_SHOW,
        booking_status=BookingStatus.MISSED,
    )


def _transition_queue_entry(
    session: Session,
    queue_entry_id: int,
    *,
    allowed_statuses: tuple[QueueStatus, ...],
    target_status: QueueStatus,
    booking_status: BookingStatus,
    set_served_at: bool = False,
) -> QueueEntry:
    try:
        queue_entry = queue_repository.get_queue_entry_for_update(session, queue_entry_id)
        if queue_entry is None:
            raise QueueError("Queue entry not found", 404)
        if queue_entry.queue_status not in allowed_statuses:
            raise QueueError(
                f"Cannot transition queue entry from {queue_entry.queue_status.value} to {target_status.value}",
                409,
            )

        queue_entry.queue_status = target_status
        queue_entry.booking.status = booking_status
        if set_served_at:
            queue_entry.served_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(queue_entry)
        return queue_entry
    except Exception:
        session.rollback()
        raise
