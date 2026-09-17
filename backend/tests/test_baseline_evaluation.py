from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import ProcurementCentre, ProcurementTelemetry, ThroughputSnapshot
from app.repositories import procurement_telemetry
from app.schemas.procurement_telemetry import ProcurementTelemetryCreate
from app.services import baseline_evaluation
from tests._auth_helpers import auth_headers, create_staff_user


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    sqlite_url = f"sqlite:///{tmp_path / 'baseline.sqlite3'}"
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(sqlite_url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    first = ProcurementCentre(name="Baseline Centre", code="BASE-01", district="Test", daily_capacity=50)
    second = ProcurementCentre(name="Other Centre", code="BASE-02", district="Test", daily_capacity=50)
    session.add_all([first, second])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        command.downgrade(config, "base")


def _add(
    session: Session,
    centre_id: int,
    day: int,
    elapsed_minutes: int,
    *,
    status: str = "COMPLETED",
    no_show: bool = False,
    cancellation: bool = False,
    provenance: str = "REAL_OBSERVED",
) -> None:
    arrival = datetime(2026, 9, day, 4, tzinfo=timezone.utc)
    data = ProcurementTelemetryCreate(
        lot_id=f"BASE-{centre_id}-{day}",
        centre_id=centre_id,
        arrival_time=arrival,
        completion_time=arrival + timedelta(minutes=elapsed_minutes) if status == "COMPLETED" else None,
        queue_size_at_arrival=day,
        provenance=provenance,
        no_show=no_show,
        cancellation=cancellation,
        completion_status=status,
    )
    procurement_telemetry.create_telemetry(session, data)
    session.commit()


def test_chronological_baseline_metrics_and_no_future_leakage(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "BASE-01")
    )
    for day, elapsed in enumerate(range(10, 110, 10), start=1):
        _add(db_session, centre_id, day, elapsed)
    result = baseline_evaluation.evaluate_completion_time(db_session, centre_id=centre_id)
    assert result["status"] == "READY"
    assert result["target"] == "arrival_to_completion_minutes"
    assert result["method"] == "RECENT_MEDIAN"
    assert result["valid_observation_count"] == 10
    assert result["train_count"] == 7
    assert result["validation_count"] == 1
    assert result["test_count"] == 2
    assert result["metrics"]["sample_count"] == 2
    assert result["metrics"]["mae"] == 47.5
    assert result["metrics"]["median_absolute_error"] == 47.5
    assert result["metrics"]["rmse"] == pytest.approx(47.565744, abs=1e-6)
    assert result["metrics"]["p90_absolute_error"] == 49.5
    assert result["metrics_by_centre"] == {}
    assert [row["arrival_time"] for row in result["observations"]] == sorted(
        row["arrival_time"] for row in result["observations"]
    )


def test_insufficient_and_invalid_operational_data(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "BASE-01")
    )
    _add(db_session, centre_id, 1, 20)
    _add(db_session, centre_id, 2, 20, no_show=True, status="NO_SHOW")
    _add(db_session, centre_id, 3, 20, cancellation=True, status="CANCELLED")
    _add(db_session, centre_id, 4, 20, status="PROCESSING")
    result = baseline_evaluation.evaluate_completion_time(db_session, centre_id=centre_id)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["valid_observation_count"] == 1
    assert result["metrics"] is None


def test_non_operational_provenance_is_excluded(db_session: Session):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "BASE-01")
    )
    for day, provenance in enumerate(
        ("REAL_OBSERVED", "TEST", "LEGACY", "SIMULATED"), start=1
    ):
        _add(db_session, centre_id, day, 20, provenance=provenance)
    result = baseline_evaluation.evaluate_completion_time(db_session, centre_id=centre_id)
    assert result["valid_observation_count"] == 1
    assert result["status"] == "INSUFFICIENT_DATA"


def test_recent_median_is_bounded_and_shared_with_prediction():
    from app.services import prediction

    values = list(range(prediction.HISTORY_LIMIT + 2))
    assert prediction.recent_median(values[-prediction.HISTORY_LIMIT:]) == 251.5


def test_global_fallback_keeps_centre_targets_isolated(db_session: Session):
    first, second = db_session.scalars(select(ProcurementCentre).order_by(ProcurementCentre.id)).all()
    _add(db_session, second.id, 1, 10)
    _add(db_session, second.id, 2, 20)
    _add(db_session, first.id, 3, 100)
    _add(db_session, first.id, 4, 110)
    _add(db_session, first.id, 5, 120)

    result = baseline_evaluation.evaluate_completion_time(
        db_session,
        centre_id=first.id,
    )

    assert result["status"] == "READY"
    assert result["metrics"]["sample_count"] == 1
    assert result["metrics"]["mae"] == 60.0
    assert {row["centre_id"] for row in result["observations"]} == {first.id}


def test_throughput_fallback_is_used_when_centre_and_global_are_insufficient(
    db_session: Session,
):
    centre_id = db_session.scalar(
        select(ProcurementCentre.id).where(ProcurementCentre.code == "BASE-01")
    )
    db_session.add(
        ThroughputSnapshot(
            centre_id=centre_id,
            avg_minutes_per_farmer=Decimal("30"),
            snapshot_at=datetime(2026, 9, 2, 4, tzinfo=timezone.utc),
        )
    )
    db_session.commit()
    _add(db_session, centre_id, 3, 50)
    _add(db_session, centre_id, 4, 60)
    _add(db_session, centre_id, 5, 70)

    result = baseline_evaluation.evaluate_completion_time(
        db_session,
        centre_id=centre_id,
    )

    assert result["status"] == "READY"
    assert result["metrics"]["sample_count"] == 1
    assert result["metrics"]["mae"] == 40.0


def test_shared_fallback_selector_matches_production_and_evaluation():
    from app.services.prediction import _Sample, select_fallback_samples

    centre = [_Sample(100.0, datetime(2026, 9, 1, tzinfo=timezone.utc))]
    global_samples = [
        _Sample(10.0, datetime(2026, 9, 1, tzinfo=timezone.utc)),
        _Sample(20.0, datetime(2026, 9, 2, tzinfo=timezone.utc)),
        _Sample(30.0, datetime(2026, 9, 3, tzinfo=timezone.utc)),
    ]
    throughput = [_Sample(40.0, datetime(2026, 9, 3, tzinfo=timezone.utc))]

    selected, level = select_fallback_samples(centre, global_samples, throughput)

    assert level == "GLOBAL_STAGE"
    assert [sample.value for sample in selected] == [10.0, 20.0, 30.0]


@pytest.mark.anyio
async def test_baseline_evaluation_is_centre_scoped(db_session: Session):
    first, second = db_session.scalars(select(ProcurementCentre).order_by(ProcurementCentre.id)).all()
    staff = create_staff_user(db_session, first, email="baseline-staff@example.test")

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
            assert (await client.get(f"/api/baseline-evaluation/centres/{first.id}/completion-time")).status_code == 200
            assert (await client.get(f"/api/baseline-evaluation/centres/{second.id}/completion-time")).status_code == 403
    finally:
        app.dependency_overrides.clear()
