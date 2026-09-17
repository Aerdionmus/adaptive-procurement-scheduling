from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SchedulingDecision


def create_decision(session: Session, decision: SchedulingDecision) -> SchedulingDecision:
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def list_decisions(session: Session, booking_id: int) -> list[SchedulingDecision]:
    return list(
        session.scalars(
            select(SchedulingDecision)
            .where(SchedulingDecision.booking_id == booking_id)
            .order_by(SchedulingDecision.evaluated_at.asc(), SchedulingDecision.id.asc())
        )
    )
