from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.seed import seed_demo_data
from app.db.session import get_db
from app.main import app
from app.models import Booking, Farmer, ProcurementCentre, SchedulingDecision
from tests._auth_helpers import auth_headers, create_admin, create_farmer_user, create_staff_user


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    database_url = f"sqlite:///{tmp_path / 'scheduling_decisions.sqlite3'}"
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_demo_data(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        command.downgrade(config, "base")


@pytest.fixture
async def client(db_session: Session) -> AsyncClient:
    admin = create_admin(db_session, email="decision-admin@example.test")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
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


def _booking(session: Session, farmer_phone: str = "9000000001") -> Booking:
    farmer = session.scalar(select(Farmer).where(Farmer.phone == farmer_phone))
    assert farmer is not None
    booking = session.scalar(
        select(Booking).where(Booking.farmer_id == farmer.id).order_by(Booking.id)
    )
    assert booking is not None
    return booking


@pytest.mark.anyio
async def test_decision_persistence_is_append_only_and_snapshots_assessment(
    client: AsyncClient,
    db_session: Session,
) -> None:
    booking = _booking(db_session)

    first = await client.post(f"/api/scheduling/bookings/{booking.id}/decisions")
    second = await client.post(f"/api/scheduling/bookings/{booking.id}/decisions")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_body = first.json()
    second_body = second.json()
    assert first_body["id"] != second_body["id"]
    assert first_body["booking_id"] == booking.id
    assert first_body["centre_id"] == booking.centre_id
    assert first_body["slot_id"] == booking.slot_id
    assert first_body["decision_version"] == "v1"
    assert first_body["reason_code"] == "ON_TRACK_KEEP_SLOT"
    assert first_body["prediction_provenance"] == "LEGACY_ESTIMATOR"

    history = await client.get(f"/api/scheduling/bookings/{booking.id}/decisions")
    assert history.status_code == 200
    assert [row["id"] for row in history.json()] == [
        first_body["id"],
        second_body["id"],
    ]
    assert db_session.scalar(select(SchedulingDecision).where(SchedulingDecision.id == first_body["id"])) is not None
    assert len(
        list(
            db_session.scalars(
                select(SchedulingDecision).where(
                    SchedulingDecision.booking_id == booking.id
                )
            )
        )
    ) == 2


@pytest.mark.anyio
async def test_decision_history_preserves_prediction_fields_and_rbac(
    client: AsyncClient,
    db_session: Session,
) -> None:
    booking = _booking(db_session)
    centre = db_session.get(ProcurementCentre, booking.centre_id)
    assert centre is not None
    farmer = db_session.get(Farmer, booking.farmer_id)
    assert farmer is not None
    other_booking = _booking(db_session, "9000000003")
    staff = create_staff_user(db_session, centre, email="decision-staff@example.test")
    farmer_user = create_farmer_user(
        db_session, farmer, email="decision-farmer@example.test"
    )

    recorded = await client.post(f"/api/scheduling/bookings/{booking.id}/decisions")
    assert recorded.status_code == 201
    recorded_body = recorded.json()
    assert recorded_body["prediction_status"] is not None
    assert recorded_body["prediction_provenance"]

    staff_client = client
    staff_client.headers.update(auth_headers(staff))
    assert (
        await staff_client.get(f"/api/scheduling/bookings/{booking.id}/decisions")
    ).status_code == 200
    assert (
        await staff_client.get(f"/api/scheduling/bookings/{other_booking.id}/decisions")
    ).status_code == 403

    farmer_client = client
    farmer_client.headers.update(auth_headers(farmer_user))
    assert (
        await farmer_client.get(f"/api/scheduling/bookings/{booking.id}/decisions")
    ).status_code == 200
    assert (
        await farmer_client.get(f"/api/scheduling/bookings/{other_booking.id}/decisions")
    ).status_code == 403
