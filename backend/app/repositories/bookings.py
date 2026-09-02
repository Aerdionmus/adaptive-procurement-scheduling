from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking


def create_booking(session: Session, booking: Booking) -> Booking:
    session.add(booking)
    session.flush()
    return booking


def get_booking(session: Session, booking_id: int) -> Booking | None:
    return session.get(Booking, booking_id)


def get_booking_for_update(session: Session, booking_id: int) -> Booking | None:
    return session.scalar(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    )
