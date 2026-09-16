"""Populate development operational telemetry through the real booking workflow.

This utility is for a local development database only. The generated rows are
REAL_OBSERVED because they pass through booking, queue, serving, and completion
services, but they represent development workflow observations rather than
real-world farmer behavior.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import make_url, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.seed import seed_demo_data
from app.models import (
    Booking,
    Farmer,
    ProcurementCentre,
    ProcurementSlot,
    ProcurementTelemetry,
)
from app.services.bookings import create_booking
from app.services.queue import call_next_farmer, check_in_booking, complete_service, start_serving
from app.schemas.procurement import BookingCreate

DEVELOPMENT_MARKER = "DEV-OPERATIONAL"
DEFAULT_COUNT = 20
COMPLETION_MINUTES = (3, 7, 12, 18, 25)


def _require_development_environment() -> None:
    database = make_url(settings.database_url)
    if settings.app_env != "development":
        raise RuntimeError(
            "Operational telemetry population requires APP_ENV=development."
        )
    if database.host not in {"localhost", "127.0.0.1"}:
        raise RuntimeError(
            "Operational telemetry population requires database host localhost or 127.0.0.1."
        )
    if database.database != "adaptive_procurement":
        raise RuntimeError(
            "Operational telemetry population requires database adaptive_procurement."
        )


def _development_crop_type(index: int) -> str:
    return f"{DEVELOPMENT_MARKER}-{index:03d}"


def _existing_generated_booking(
    session: Session,
    *,
    crop_type: str,
    centre_id: int,
    farmer_id: int,
    slot_id: int,
    quantity_kg: Decimal,
) -> Booking | None:
    return session.scalar(
        select(Booking).where(
            Booking.crop_type == crop_type,
            Booking.centre_id == centre_id,
            Booking.farmer_id == farmer_id,
            Booking.slot_id == slot_id,
            Booking.quantity_kg == quantity_kg,
        )
    )


def _usable_slots(session: Session) -> list[ProcurementSlot]:
    return list(
        session.scalars(
            select(ProcurementSlot)
            .where(ProcurementSlot.capacity > 0)
            .order_by(ProcurementSlot.slot_date, ProcurementSlot.start_time, ProcurementSlot.centre_id)
        )
    )


def _ensure_requirements(
    session: Session,
    count: int,
) -> tuple[list[ProcurementCentre], list[Farmer], list[ProcurementSlot]]:
    seed_demo_data(session)
    centres = list(
        session.scalars(
            select(ProcurementCentre)
            .where(ProcurementCentre.active.is_(True))
            .order_by(ProcurementCentre.id)
        )
    )
    farmers = list(session.scalars(select(Farmer).order_by(Farmer.id)))
    slots = _usable_slots(session)
    dates = {slot.slot_date for slot in slots}
    centre_ids = {slot.centre_id for slot in slots}
    if len(centres) < 2 or len(farmers) == 0 or len(dates) < 2 or len(centre_ids) < 2:
        raise RuntimeError(
            "Development seed must provide at least two centres, two dates, and one farmer."
        )
    if len(slots) * 20 < count:
        raise RuntimeError("Not enough seeded slot capacity for the requested population.")
    return centres, farmers, slots


def populate_operational_telemetry(
    session: Session,
    *,
    count: int = DEFAULT_COUNT,
) -> int:
    """Create completed development observations through application services.

    Returns the number of newly completed bookings. Existing bookings carrying
    the deterministic development marker are reused, making reruns idempotent.
    """
    _require_development_environment()
    if count <= 0:
        raise ValueError("count must be positive")

    _, farmers, slots = _ensure_requirements(session, count)
    generated: list[tuple[Booking, ProcurementSlot, int]] = []
    for index in range(count):
        slot = slots[index % len(slots)]
        farmer = farmers[index % len(farmers)]
        quantity = Decimal(500 + (index % 5) * 125)
        crop_type = _development_crop_type(index)
        existing = _existing_generated_booking(
            session,
            crop_type=crop_type,
            centre_id=slot.centre_id,
            farmer_id=farmer.id,
            slot_id=slot.id,
            quantity_kg=quantity,
        )
        if existing is None:
            existing = create_booking(
                session,
                BookingCreate(
                    farmer_id=farmer.id,
                    centre_id=slot.centre_id,
                    slot_id=slot.id,
                    crop_type=crop_type,
                    quantity_kg=quantity,
                ),
            )
        telemetry = session.scalar(
            select(ProcurementTelemetry).where(
                ProcurementTelemetry.booking_id == existing.id
            )
        )
        if telemetry is None or telemetry.completion_status != "COMPLETED":
            generated.append((existing, slot, index))

    grouped: dict[tuple[date, int], list[tuple[Booking, ProcurementSlot, int, datetime]]] = {}
    for booking, slot, index in generated:
        arrival = datetime.combine(
            slot.slot_date,
            slot.start_time,
            tzinfo=timezone.utc,
        ) + timedelta(minutes=5 + index % 4)
        grouped.setdefault((slot.slot_date, slot.centre_id), []).append(
            (booking, slot, index, arrival)
        )

    for entries in grouped.values():
        clock_value = [entries[0][3]]
        original_utcnow = clock.utcnow
        clock.utcnow = lambda: clock_value[0]
        try:
            for booking, _, _, arrival in entries:
                clock_value[0] = arrival
                check_in_booking(session, booking.id, booking.centre_id)
            for booking, _, index, arrival in entries:
                clock_value[0] = arrival
                while True:
                    called = call_next_farmer(session, booking.centre_id)
                    if called.booking_id == booking.id:
                        break
                    # A seeded development queue may contain older waiting
                    # bookings. Complete them through the same workflow so
                    # they do not block the generated booking.
                    start_serving(session, called.id)
                    complete_service(session, called.id)
                start_serving(session, called.id)
                clock_value[0] = arrival + timedelta(
                    minutes=COMPLETION_MINUTES[index % len(COMPLETION_MINUTES)]
                )
                complete_service(session, called.id)
        finally:
            clock.utcnow = original_utcnow

    return len(generated)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    args = parser.parse_args()
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        created = populate_operational_telemetry(session, count=args.count)
    print(f"Completed {created} development operational bookings.")


if __name__ == "__main__":
    main()
