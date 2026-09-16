from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProcurementTelemetry
from app.schemas.procurement_telemetry import ProcurementTelemetryCreate


def create_telemetry(session: Session, data: ProcurementTelemetryCreate) -> ProcurementTelemetry:
    telemetry = ProcurementTelemetry(**data.model_dump())
    session.add(telemetry)
    session.flush()
    return telemetry


def get_telemetry(session: Session, telemetry_id: int) -> ProcurementTelemetry | None:
    return session.get(ProcurementTelemetry, telemetry_id)


def get_telemetry_for_booking(
    session: Session,
    booking_id: int,
) -> ProcurementTelemetry | None:
    return session.scalar(
        select(ProcurementTelemetry)
        .where(ProcurementTelemetry.booking_id == booking_id)
        .order_by(ProcurementTelemetry.id.desc())
        .limit(1)
    )


def list_telemetry(session: Session, centre_id: int) -> list[ProcurementTelemetry]:
    return list(
        session.scalars(
            select(ProcurementTelemetry)
            .where(ProcurementTelemetry.centre_id == centre_id)
            .order_by(ProcurementTelemetry.arrival_time.asc(), ProcurementTelemetry.id.asc())
        )
    )


def list_historical_telemetry(
        session: Session,
        *,
        centre_id: int | None = None,
        limit: int = 500,
        before: datetime | None = None,
        after: datetime | None = None,
) -> list[ProcurementTelemetry]:
    """Return a bounded, chronological telemetry history.

        Prediction code applies label validity rules after this query. Keeping
        the query bounded prevents an unbounded table scan as telemetry grows,
        while the stable ``id`` tie-breaker makes repeated predictions ordered
        deterministically.
    """
    if limit < 1:
        raise ValueError("limit must be positive")

    query = select(ProcurementTelemetry)
    if centre_id is not None:
        query = query.where(ProcurementTelemetry.centre_id == centre_id)
    if after is not None:
        query = query.where(ProcurementTelemetry.arrival_time >= after)
    if before is not None:
        query = query.where(ProcurementTelemetry.arrival_time < before)
    query = query.order_by(
        ProcurementTelemetry.arrival_time.desc(),
        ProcurementTelemetry.id.desc(),
    ).limit(limit)
    # Select the newest bounded window, but expose it in chronological order
    # so downstream quantiles and provenance are stable and easy to inspect.
    return list(reversed(list(session.scalars(query))))
