from __future__ import annotations

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


def list_telemetry(session: Session, centre_id: int) -> list[ProcurementTelemetry]:
    return list(
        session.scalars(
            select(ProcurementTelemetry)
            .where(ProcurementTelemetry.centre_id == centre_id)
            .order_by(ProcurementTelemetry.arrival_time.asc(), ProcurementTelemetry.id.asc())
        )
    )
