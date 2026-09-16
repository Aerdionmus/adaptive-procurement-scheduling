from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import ProcurementCentre, ProcurementTelemetry, ThroughputSnapshot
from app.repositories import procurement_telemetry as telemetry_repository
from app.schemas.procurement_telemetry import ProcurementTelemetryCreate
from app.services import prediction
from tests._auth_helpers import auth_headers, create_staff_user


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    sqlite_url = f"sqlite:///{tmp_path / 'prediction.sqlite3'}"
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(sqlite_url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    first = ProcurementCentre(
        name="Prediction Centre",
        code="PRED-01",
        district="Prediction",
        daily_capacity=100,
    )
    second = ProcurementCentre(
        name="Other Prediction Centre",
        code="PRED-02",
        district="Prediction",
        daily_capacity=100,
    )
    session.add_all([first, second])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        command.downgrade(config, "base")


def _telemetry(
    centre_id: int,
    at: datetime,
    *,
    duration_offset: int = 0,
    no_show: bool = False,
    cancellation: bool = False,
    completion_status: str = "COMPLETED",
    provenance: str = "TEST",
) -> ProcurementTelemetryCreate:
    stage_durations = (2, 4, 6, 3, 5)
    cursor = at
    values: dict[str, object] = {
        "lot_id": f"LOT-{at.timestamp()}",
        "centre_id": centre_id,
        "arrival_time": at,
        "queue_size_at_arrival": 2,
        "no_show": no_show,
        "cancellation": cancellation,
        "completion_status": completion_status,
        "provenance": provenance,
    }
    for stage, duration in zip(prediction.STAGES, stage_durations):
        start = cursor
        end = start + timedelta(minutes=duration + duration_offset)
        values[f"{stage}_start"] = start
        values[f"{stage}_end"] = end
        cursor = end
    values["completion_time"] = cursor + timedelta(minutes=10)
    if no_show:
        for stage in prediction.STAGES:
            values[f"{stage}_start"] = None
            values[f"{stage}_end"] = None
        values["completion_time"] = None
    if cancellation:
        values["completion_time"] = None
    return ProcurementTelemetryCreate(**values)


def _add(
    session: Session,
    data: ProcurementTelemetryCreate,
) -> ProcurementTelemetry:
    row = telemetry_repository.create_telemetry(session, data)
    session.commit()
    session.refresh(row)
    return row


def test_valid_labels_exclude_invalid_and_keep_active_separate(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "PRED-01")
    )
    base = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
    for index in range(3):
        _add(db_session, _telemetry(centre_id, base + timedelta(days=index), provenance="REAL_OBSERVED"))
    _add(db_session, _telemetry(centre_id, base + timedelta(days=3), no_show=True))
    _add(db_session, _telemetry(centre_id, base + timedelta(days=4), cancellation=True))
    _add(
        db_session,
        _telemetry(
            centre_id,
            base + timedelta(days=5),
            completion_status="PROCESSING",
        ),
    )
    result = prediction.predict_service_times(db_session, centre_id)
    active = next(item for item in result.predictions if item.target == "total_active_service")
    elapsed = next(item for item in result.predictions if item.target == "arrival_to_completion")
    assert active.sample_count == 3
    assert elapsed.sample_count == 3
    assert active.predicted_minutes == 20.0
    assert elapsed.predicted_minutes == 30.0
    assert active.predicted_minutes != elapsed.predicted_minutes


def test_stage_median_p50_p90_and_chronological_handling(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "PRED-01")
    )
    base = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
    for index, offset in [(2, 20), (0, 0), (1, 10)]:
        _add(
            db_session,
            _telemetry(
                centre_id,
                base + timedelta(days=index),
                duration_offset=offset,
                provenance="REAL_OBSERVED",
            ),
        )
    result = prediction.predict_service_times(db_session, centre_id)
    quality = next(item for item in result.predictions if item.target == "quality")
    assert quality.status == "READY"
    assert quality.sample_count == 3
    assert quality.p50_minutes == 16.0
    assert quality.p90_minutes == 24.0
    assert quality.lookback_start < quality.lookback_end


def test_fallback_hierarchy_and_insufficient_data(db_session: Session):
    first, second = db_session.scalars(select(ProcurementCentre).order_by(ProcurementCentre.id)).all()
    base = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
    empty = prediction.predict_service_times(db_session, 999999)
    assert all(item.status == "INSUFFICIENT_DATA" for item in empty.predictions)
    for index in range(3):
        _add(db_session, _telemetry(second.id, base + timedelta(days=index), provenance="REAL_OBSERVED"))
    result = prediction.predict_service_times(db_session, first.id)
    registration = next(item for item in result.predictions if item.target == "registration")
    assert registration.fallback_level == "GLOBAL_STAGE"
    assert registration.status == "READY"



def test_existing_throughput_fallback_and_determinism(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "PRED-01")
    )
    db_session.add(
        ThroughputSnapshot(
            centre_id=centre_id,
            avg_minutes_per_farmer=30,
            snapshot_at=datetime(2026, 9, 1, 4, tzinfo=timezone.utc),
        )
    )
    db_session.commit()
    first = prediction.predict_service_times(db_session, centre_id)
    second = prediction.predict_service_times(db_session, centre_id)
    assert first == second
    assert all(item.fallback_level == "EXISTING_THROUGHPUT" for item in first.predictions)
    throughput = prediction.predict_throughput(db_session, centre_id)
    assert throughput.predicted_minutes_per_lot == 30.0
    assert throughput.reference_context_used == []


def test_non_operational_provenance_is_excluded_from_prediction(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "PRED-01")
    )
    base = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
    for index, provenance in enumerate(("TEST", "SIMULATED", "LEGACY")):
        _add(
            db_session,
            _telemetry(
                centre_id,
                base + timedelta(days=index),
                provenance=provenance,
            ),
        )
    result = prediction.predict_service_times(db_session, centre_id)
    assert all(item.status == "INSUFFICIENT_DATA" for item in result.predictions)


@pytest.mark.anyio
async def test_prediction_endpoints_are_centre_scoped(db_session: Session):
    first, second = db_session.scalars(select(ProcurementCentre).order_by(ProcurementCentre.id)).all()
    staff = create_staff_user(db_session, first, email="prediction-staff@example.test")

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
            assert (await client.get(f"/api/predictions/centres/{first.id}/throughput")).status_code == 200
            assert (await client.get(f"/api/predictions/centres/{second.id}/throughput")).status_code == 403
            assert (await client.get(f"/api/predictions/centres/{second.id}/service-times")).status_code == 403
    finally:
        app.dependency_overrides.clear()
