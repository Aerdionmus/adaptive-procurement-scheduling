from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import ProcurementCentre, ProcurementSlot


def list_active_centres(session: Session) -> list[ProcurementCentre]:
    return list(
        session.scalars(
            select(ProcurementCentre)
            .where(ProcurementCentre.active.is_(True))
            .order_by(ProcurementCentre.id)
        )
    )


def get_centre(session: Session, centre_id: int) -> ProcurementCentre | None:
    return session.get(ProcurementCentre, centre_id)


def get_centre_for_update(session: Session, centre_id: int) -> ProcurementCentre | None:
    return session.scalar(
        select(ProcurementCentre)
        .where(ProcurementCentre.id == centre_id)
        .with_for_update()
    )


def list_usable_slots(session: Session, centre_id: int) -> list[ProcurementSlot]:
    return list(
        session.scalars(
            select(ProcurementSlot)
            .where(
                ProcurementSlot.centre_id == centre_id,
                ProcurementSlot.capacity > 0,
            )
            .order_by(ProcurementSlot.slot_date, ProcurementSlot.start_time)
        )
    )


def get_slot(session: Session, slot_id: int) -> ProcurementSlot | None:
    return session.get(ProcurementSlot, slot_id)


def reserve_slot_capacity(session: Session, slot_id: int) -> bool:
    """Atomically reserve one remaining booking position in a slot."""
    result = session.execute(
        update(ProcurementSlot)
        .where(
            ProcurementSlot.id == slot_id,
            ProcurementSlot.capacity > 0,
        )
        .values(capacity=ProcurementSlot.capacity - 1)
    )
    return result.rowcount == 1
