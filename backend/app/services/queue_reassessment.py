from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import bookings as booking_repository
from app.services import scheduling as scheduling_service
from app.services import scheduling_decisions


@dataclass(frozen=True)
class ReassessmentResult:
    reassessed_booking_ids: tuple[int, ...]
    persistence_succeeded: bool

    @property
    def reassessed_count(self) -> int:
        return len(self.reassessed_booking_ids)


def reassess_after_completion(session: Session, centre_id: int) -> ReassessmentResult:
    """Persist fresh decisions for pending bookings after a completion commit.

    The caller must invoke this only after the queue completion workflow has
    returned successfully. Each decision is intentionally persisted through
    the existing append-only decision service.
    """
    # The completion workflow may commit more than once (queue state and
    # throughput). Refresh ORM state before prediction-backed assessment so
    # every telemetry timestamp comes from the same committed representation,
    # including SQLite's timezone-naive test representation.
    session.expire_all()
    bookings = booking_repository.list_pending_bookings_for_centre(session, centre_id)
    reassessed_booking_ids: list[int] = []

    for booking in bookings:
        assessment = scheduling_service.assess_booking(session, booking.id)
        scheduling_decisions.record_decision(session, assessment)
        reassessed_booking_ids.append(booking.id)

    return ReassessmentResult(
        reassessed_booking_ids=tuple(reassessed_booking_ids),
        persistence_succeeded=True,
    )
