from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import ProcurementCentre, ProcurementTelemetry
from tests._auth_helpers import auth_headers, create_admin, create_staff_user


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    sqlite_url = f"sqlite:///{tmp_path / 'telemetry.sqlite3'}"
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(sqlite_url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    centre = ProcurementCentre(
        name="Telemetry Centre",
        code="TEL-01",
        district="Test",
        daily_capacity=100,
    )
    other = ProcurementCentre(
        name="Other Centre",
        code="TEL-02",
        district="Test",
        daily_capacity=100,
    )
    session.add_all([centre, other])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        command.downgrade(config, "base")


@pytest.fixture
async def client(db_session: Session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = create_admin(db_session, email="telemetry-admin@example.test")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=auth_headers(admin),
        ) as test_client:
            yield test_client, db_session
    finally:
        app.dependency_overrides.clear()


def payload(centre_id: int) -> dict:
    start = datetime(2026, 9, 16, 4, 0, tzinfo=timezone.utc)
    return {
        "lot_id": "LOT-001",
        "centre_id": centre_id,
        "scheduled_slot": "slot-09:00",
        "arrival_time": start.isoformat(),
        "queue_size_at_arrival": 3,
        "registration_start": start.isoformat(),
        "registration_end": (start + timedelta(minutes=2)).isoformat(),
        "unloading_start": (start + timedelta(minutes=2)).isoformat(),
        "unloading_end": (start + timedelta(minutes=8)).isoformat(),
        "quality_start": (start + timedelta(minutes=8)).isoformat(),
        "quality_end": (start + timedelta(minutes=12)).isoformat(),
        "weighment_start": (start + timedelta(minutes=12)).isoformat(),
        "weighment_end": (start + timedelta(minutes=14)).isoformat(),
        "documentation_start": (start + timedelta(minutes=14)).isoformat(),
        "documentation_end": (start + timedelta(minutes=16)).isoformat(),
        "completion_time": (start + timedelta(minutes=16)).isoformat(),
        "resource_state": {"quality-1": "available"},
        "completion_status": "COMPLETED",
    }


@pytest.mark.anyio
async def test_create_and_list_telemetry_returns_safe_derived_durations(client):
    test_client, session = client
    centre_id = session.scalar(select(ProcurementCentre.id).where(ProcurementCentre.code == "TEL-01"))
    response = await test_client.post("/api/procurement-telemetry/", json=payload(centre_id))
    assert response.status_code == 201
    body = response.json()
    assert body["registration_duration_minutes"] == 2.0
    assert body["total_cycle_minutes"] == 16.0
    listing = await test_client.get(f"/api/procurement-telemetry/centres/{centre_id}")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert session.scalar(select(ProcurementTelemetry)) is not None


@pytest.mark.anyio
async def test_invalid_stage_order_and_inconsistent_flags_are_rejected(client):
    test_client, session = client
    centre_id = session.scalar(select(ProcurementCentre.id).where(ProcurementCentre.code == "TEL-01"))
    invalid = payload(centre_id)
    invalid["quality_start"] = invalid["quality_end"]
    invalid["quality_end"] = invalid["unloading_end"]
    response = await test_client.post("/api/procurement-telemetry/", json=invalid)
    assert response.status_code == 422
    invalid = payload(centre_id)
    invalid["no_show"] = True
    response = await test_client.post("/api/procurement-telemetry/", json=invalid)
    assert response.status_code == 422


@pytest.mark.anyio
async def test_staff_cannot_write_or_read_another_centre_telemetry(db_session: Session):
    first, second = db_session.scalars(select(ProcurementCentre).order_by(ProcurementCentre.id)).all()
    staff = create_staff_user(
        db_session, first, email="telemetry-staff@example.test"
    )

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=auth_headers(staff),
        ) as test_client:
            response = await test_client.post("/api/procurement-telemetry/", json=payload(second.id))
            assert response.status_code == 403
            response = await test_client.get(f"/api/procurement-telemetry/centres/{second.id}")
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
