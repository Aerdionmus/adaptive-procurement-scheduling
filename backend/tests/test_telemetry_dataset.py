from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import (
    Booking,
    BookingStatus,
    Farmer,
    ProcurementCentre,
    ProcurementSlot,
    ProcurementTelemetry,
)
from app.repositories import procurement_telemetry
from app.schemas.procurement_telemetry import ProcurementTelemetryCreate
from app.services import queue as queue_service
from app.services import telemetry as telemetry_service
from app.services import telemetry_dataset
from tests._auth_helpers import auth_headers, create_staff_user


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    sqlite_url = f"sqlite:///{tmp_path / 'telemetry_dataset.sqlite3'}"
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(sqlite_url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    first = ProcurementCentre(name="Dataset Centre", code="DATA-01", district="Test", daily_capacity=50)
    second = ProcurementCentre(name="Other Centre", code="DATA-02", district="Test", daily_capacity=50)
    session.add_all([first, second])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        command.downgrade(config, "base")


def _full_payload(centre_id: int, booking_id: int | None, at: datetime) -> ProcurementTelemetryCreate:
    cursor = at
    values: dict[str, object] = {
        "lot_id": str(booking_id or "manual-lot"),
        "booking_id": booking_id,
        "centre_id": centre_id,
        "arrival_time": at,
        "queue_size_at_arrival": 4,
        "completion_status": "COMPLETED",
        "provenance": "TEST",
        "resource_state": {"quality-1": "available"},
    }
    for stage, minutes in (
        ("registration", 2),
        ("unloading", 4),
        ("quality", 6),
        ("weighment", 3),
        ("documentation", 5),
    ):
        values[f"{stage}_start"] = cursor
        cursor += timedelta(minutes=minutes)
        values[f"{stage}_end"] = cursor
    values["completion_time"] = cursor
    return ProcurementTelemetryCreate(**values)


def _add_full(session: Session, centre_id: int, booking_id: int | None, day: int) -> None:
    row = procurement_telemetry.create_telemetry(
        session,
        _full_payload(
            centre_id,
            booking_id,
            datetime(2026, 9, day, 4, tzinfo=timezone.utc),
        ),
    )
    session.commit()
    session.refresh(row)


def test_real_queue_workflow_creates_linked_telemetry_and_queue_snapshot(db_session: Session):
    centre = db_session.scalar(select(ProcurementCentre).where(ProcurementCentre.code == "DATA-01"))
    farmer = Farmer(name="Workflow Farmer", phone="9111111111", village="Test")
    slot = ProcurementSlot(
        centre_id=centre.id,
        slot_date=date.today(),
        start_time=time(0, 0),
        end_time=time(23, 59),
        capacity=10,
    )
    booking = Booking(
        farmer=farmer,
        centre=centre,
        slot=slot,
        crop_type="Paddy",
        quantity_kg=100,
        status=BookingStatus.BOOKED,
    )
    db_session.add(booking)
    db_session.commit()
    entry = queue_service.check_in_booking(db_session, booking.id, centre.id)
    telemetry = db_session.scalar(
        select(ProcurementTelemetry).where(ProcurementTelemetry.booking_id == booking.id)
    )
    assert entry.booking_id == booking.id
    assert telemetry is not None
    assert telemetry.lot_id == str(booking.id)
    assert telemetry.provenance == "REAL_OBSERVED"
    assert telemetry.queue_size_at_arrival == 0
    queue_service.call_next_farmer(db_session, centre.id)
    queue_service.start_serving(db_session, entry.id)
    queue_service.complete_service(db_session, entry.id)
    db_session.refresh(telemetry)
    assert telemetry.completion_status == "COMPLETED"
    assert telemetry.completion_time is not None
    repeated = telemetry_service.record_check_in(
        db_session,
        booking,
        arrival_time=telemetry.arrival_time,
        queue_size_at_arrival=telemetry.queue_size_at_arrival,
    )
    assert repeated.id == telemetry.id
    rows = telemetry_dataset.prepare_dataset(db_session, centre_id=centre.id)
    assert len(rows) == 1
    assert rows[0]["stage"] == "arrival_to_completion"
    assert rows[0]["stage_duration_minutes"] is None
    assert rows[0]["total_active_service_minutes"] is None
    assert rows[0]["arrival_to_completion_minutes"] is not None


def test_booking_id_uniqueness_rejects_duplicate_but_allows_legacy_null(
    db_session: Session,
):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "DATA-01")
    )
    first = _full_payload(centre_id, 101, datetime(2026, 9, 8, 4, tzinfo=timezone.utc))
    procurement_telemetry.create_telemetry(db_session, first)
    db_session.commit()
    duplicate = _full_payload(centre_id, 101, datetime(2026, 9, 9, 4, tzinfo=timezone.utc))
    with pytest.raises(IntegrityError):
        procurement_telemetry.create_telemetry(db_session, duplicate)
        db_session.commit()
    db_session.rollback()
    legacy_one = _full_payload(centre_id, None, datetime(2026, 9, 10, 4, tzinfo=timezone.utc))
    legacy_two = _full_payload(centre_id, None, datetime(2026, 9, 11, 4, tzinfo=timezone.utc))
    procurement_telemetry.create_telemetry(db_session, legacy_one)
    procurement_telemetry.create_telemetry(db_session, legacy_two)
    db_session.commit()


def test_dataset_quality_exclusions_and_deterministic_split(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "DATA-01")
    )
    for day in range(1, 5):
        _add_full(db_session, centre_id, day, day)
    incomplete = _full_payload(centre_id, None, datetime(2026, 9, 5, 4, tzinfo=timezone.utc))
    incomplete.quality_end = None
    incomplete.quality_start = None
    procurement_telemetry.create_telemetry(db_session, incomplete)
    no_show_data = _full_payload(
        centre_id, None, datetime(2026, 9, 6, 4, tzinfo=timezone.utc)
    ).model_dump(
        exclude={"registration_start", "registration_end", "unloading_start", "unloading_end",
                 "quality_start", "quality_end", "weighment_start", "weighment_end",
                 "documentation_start", "documentation_end", "completion_time"}
    )
    no_show_data.update(no_show=True, completion_status="NO_SHOW")
    no_show = ProcurementTelemetry(**no_show_data)
    cancelled_data = _full_payload(
        centre_id, None, datetime(2026, 9, 7, 4, tzinfo=timezone.utc)
    ).model_dump(exclude={"completion_time"})
    cancelled_data.update(cancellation=True, completion_status="CANCELLED")
    cancelled = ProcurementTelemetry(**cancelled_data)
    db_session.add_all([no_show, cancelled])
    db_session.commit()
    report = telemetry_dataset.quality_report(db_session, centre_id=centre_id)
    assert report["total_records"] == 7
    assert report["valid_completed_records"] == 5
    assert report["valid_labels_per_stage"]["quality"] == 4
    assert report["cancelled_records"] == 1
    assert report["no_show_records"] == 1
    rows = telemetry_dataset.prepare_dataset(db_session, centre_id=centre_id)
    assert len(rows) == 29
    assert all(row["provenance"] == "REAL_OBSERVED" for row in rows)
    split = telemetry_dataset.split_chronologically(rows)
    assert len(split.train) == 20
    assert len(split.validation) == 4
    assert len(split.test) == 5
    assert split.train == telemetry_dataset.split_chronologically(rows).train


@pytest.mark.anyio
async def test_dataset_and_readiness_are_centre_scoped(db_session: Session):
    first, second = db_session.scalars(select(ProcurementCentre).order_by(ProcurementCentre.id)).all()
    staff = create_staff_user(db_session, first, email="dataset-staff@example.test")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers=auth_headers(staff),
        ) as client:
            assert (await client.get(f"/api/telemetry-dataset/centres/{first.id}/readiness")).status_code == 200
            assert (await client.get(f"/api/telemetry-dataset/centres/{second.id}/readiness")).status_code == 403
            assert (await client.get(f"/api/telemetry-dataset/centres/{second.id}/dataset")).status_code == 403
    finally:
        app.dependency_overrides.clear()
