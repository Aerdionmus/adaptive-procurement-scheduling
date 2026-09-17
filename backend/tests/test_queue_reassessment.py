from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.seed import seed_demo_data
from app.db.session import get_db
from app.main import app
from app.models import (
    Booking,
    BookingStatus,
    ProcurementCentre,
    QueueEntry,
    SchedulingDecision,
)
from app.services import queue_reassessment
from tests._auth_helpers import auth_headers, create_admin


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    database_url = f"sqlite:///{tmp_path / 'queue_reassessment.sqlite3'}"
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_demo_data(session)
    session.execute(delete(QueueEntry))
    session.execute(delete(SchedulingDecision))
    session.execute(update(Booking).values(status=BookingStatus.BOOKED))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        command.downgrade(config, "base")


@pytest.fixture
async def client(db_session: Session) -> AsyncClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = create_admin(db_session, email="queue-reassessment-admin@example.test")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=auth_headers(admin),
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _centre(session: Session, code: str) -> ProcurementCentre:
    centre = session.scalar(
        select(ProcurementCentre).where(ProcurementCentre.code == code)
    )
    assert centre is not None
    return centre


def _bookings(session: Session, centre_id: int, count: int) -> list[Booking]:
    bookings = list(
        session.scalars(
            select(Booking)
            .where(
                Booking.centre_id == centre_id,
                Booking.status == BookingStatus.BOOKED,
            )
            .order_by(Booking.id)
        )
    )
    assert len(bookings) >= count
    return bookings[:count]


async def _complete(client: AsyncClient, booking: Booking) -> int:
    check_in = await client.post(
        "/api/queue/check-in",
        json={"booking_id": booking.id, "centre_id": booking.centre_id},
    )
    assert check_in.status_code == 201, check_in.text
    entry_id = check_in.json()["id"]
    call_next = await client.post(
        f"/api/queue/centres/{booking.centre_id}/call-next"
    )
    assert call_next.status_code == 200, call_next.text
    start = await client.post(f"/api/queue/{entry_id}/start-serving")
    assert start.status_code == 200, start.text
    complete = await client.post(f"/api/queue/{entry_id}/complete")
    assert complete.status_code == 200, complete.text
    return entry_id


@pytest.mark.anyio
async def test_completion_reassesses_remaining_bookings_only_and_is_centre_scoped(
    client: AsyncClient,
    db_session: Session,
) -> None:
    centre = _centre(db_session, "TNJ-CENTRAL-01")
    other_centre = _centre(db_session, "KUM-01")
    completed, remaining = _bookings(db_session, centre.id, 2)
    other_booking = _bookings(db_session, other_centre.id, 1)[0]

    await _complete(client, completed)

    decisions = list(
        db_session.scalars(
            select(SchedulingDecision)
            .order_by(SchedulingDecision.id)
        )
    )
    same_centre_pending_ids = [
        booking.id
        for booking in db_session.scalars(
            select(Booking)
            .where(
                Booking.centre_id == centre.id,
                Booking.status.in_(
                    (
                        BookingStatus.BOOKED,
                        BookingStatus.CHECKED_IN,
                        BookingStatus.IN_QUEUE,
                        BookingStatus.PROCESSING,
                    )
                ),
            )
            .order_by(Booking.id)
        )
    ]
    assert [decision.booking_id for decision in decisions] == same_centre_pending_ids
    assert remaining.id in same_centre_pending_ids
    assert all(decision.centre_id == centre.id for decision in decisions)
    assert all(decision.prediction_provenance for decision in decisions)
    assert all(decision.prediction_status is not None for decision in decisions)
    assert all(decision.booking_id != other_booking.id for decision in decisions)
    db_session.refresh(completed)
    assert completed.status == BookingStatus.COMPLETED


@pytest.mark.anyio
async def test_multiple_completions_append_new_reassessment_snapshots(
    client: AsyncClient,
    db_session: Session,
) -> None:
    centre = _centre(db_session, "TNJ-CENTRAL-01")
    first, second, third = _bookings(db_session, centre.id, 3)

    await _complete(client, first)
    first_count = db_session.scalar(
        select(SchedulingDecision.id).where(
            SchedulingDecision.booking_id == third.id
        )
    )
    assert first_count is not None

    await _complete(client, second)

    third_decisions = list(
        db_session.scalars(
            select(SchedulingDecision)
            .where(SchedulingDecision.booking_id == third.id)
            .order_by(SchedulingDecision.id)
        )
    )
    assert len(third_decisions) == 2
    assert third_decisions[0].id != third_decisions[1].id


@pytest.mark.anyio
async def test_failed_queue_transition_creates_no_reassessment_decisions(
    client: AsyncClient,
    db_session: Session,
) -> None:
    centre = _centre(db_session, "TNJ-CENTRAL-01")
    booking = _bookings(db_session, centre.id, 1)[0]
    response = await client.post("/api/queue/999999/complete")
    assert response.status_code == 404
    assert db_session.scalar(select(SchedulingDecision.id)) is None
    db_session.refresh(booking)
    assert booking.status == BookingStatus.BOOKED


@pytest.mark.anyio
async def test_reassessment_persistence_failure_is_surfaced_after_completion(
    client: AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    centre = _centre(db_session, "TNJ-CENTRAL-01")
    completed, remaining = _bookings(db_session, centre.id, 2)

    def fail_record(*args, **kwargs):
        raise RuntimeError("decision persistence failed")

    monkeypatch.setattr(queue_reassessment.scheduling_decisions, "record_decision", fail_record)

    with pytest.raises(RuntimeError, match="decision persistence failed"):
        await _complete(client, completed)

    db_session.refresh(completed)
    assert completed.status == BookingStatus.COMPLETED
    assert db_session.scalar(
        select(SchedulingDecision.id).where(
            SchedulingDecision.booking_id == remaining.id
        )
    ) is None
