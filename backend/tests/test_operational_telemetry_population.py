from __future__ import annotations

from pathlib import Path
from datetime import timedelta

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models import Booking, ProcurementTelemetry
from app.scripts.populate_operational_telemetry import (
    DEVELOPMENT_MARKER,
    _require_development_environment,
    populate_operational_telemetry,
)


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    sqlite_url = f"sqlite:///{tmp_path / 'operational_telemetry.sqlite3'}"
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    command.upgrade(config, "head")
    engine = create_engine(sqlite_url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql://localhost/adaptive_procurement",
    )
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        command.downgrade(config, "base")


def test_population_uses_workflow_and_is_idempotent(db_session: Session) -> None:
    created = populate_operational_telemetry(db_session, count=6)
    assert created == 6

    bookings = list(
        db_session.scalars(
            select(Booking).where(Booking.crop_type.like(f"{DEVELOPMENT_MARKER}-%"))
        )
    )
    assert len(bookings) == 6
    assert len({booking.centre_id for booking in bookings}) >= 2
    telemetry = list(
        db_session.scalars(
            select(ProcurementTelemetry).where(
                ProcurementTelemetry.booking_id.in_(booking.id for booking in bookings)
            )
        )
    )
    assert len(telemetry) == 6
    assert all(row.provenance == "REAL_OBSERVED" for row in telemetry)
    assert all(row.completion_status == "COMPLETED" for row in telemetry)
    assert all(row.arrival_time is not None for row in telemetry)
    assert all(row.completion_time is not None for row in telemetry)
    durations = {
        (row.completion_time - row.arrival_time).total_seconds()
        for row in telemetry
    }
    assert len(durations) > 1
    assert len({row.queue_size_at_arrival for row in telemetry}) > 1
    assert all(
        getattr(row, f"{stage}_{boundary}") is None
        for row in telemetry
        for stage in (
            "registration",
            "unloading",
            "quality",
            "weighment",
            "documentation",
        )
        for boundary in ("start", "end")
    )

    assert populate_operational_telemetry(db_session, count=6) == 0
    assert db_session.scalar(
        select(ProcurementTelemetry.booking_id).where(
            ProcurementTelemetry.booking_id.in_(booking.id for booking in bookings)
        )
    ) is not None
    assert len(
        list(
            db_session.scalars(
                select(ProcurementTelemetry).where(
                    ProcurementTelemetry.booking_id.in_(
                        booking.id for booking in bookings
                    )
                )
            )
        )
    ) == 6


def test_population_source_does_not_create_telemetry_directly() -> None:
    source = Path(__file__).resolve().parents[1] / "app/scripts/populate_operational_telemetry.py"
    text = source.read_text()
    assert "create_telemetry(" not in text


@pytest.mark.parametrize(
    ("app_env", "database_url", "message"),
    [
        ("production", "postgresql://localhost/adaptive_procurement", "APP_ENV"),
        ("development", "postgresql://db.internal/adaptive_procurement", "host"),
        ("development", "postgresql://localhost/other_database", "database"),
    ],
)
def test_population_requires_exact_development_database(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    database_url: str,
    message: str,
) -> None:
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "database_url", database_url)
    with pytest.raises(RuntimeError, match=message):
        _require_development_environment()


def test_population_accepts_exact_development_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql://localhost/adaptive_procurement",
    )
    _require_development_environment()


def test_generated_identity_does_not_match_normal_booking(
    db_session: Session,
) -> None:
    populate_operational_telemetry(db_session, count=1)
    generated = db_session.scalar(
        select(Booking).where(Booking.crop_type == f"{DEVELOPMENT_MARKER}-000")
    )
    assert generated is not None
    normal = Booking(
        farmer_id=generated.farmer_id,
        centre_id=generated.centre_id,
        slot_id=generated.slot_id,
        crop_type="Paddy",
        quantity_kg=generated.quantity_kg,
    )
    assert normal.crop_type != generated.crop_type
