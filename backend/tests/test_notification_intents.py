from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.db.seed import seed_demo_data
from app.main import app
from app.delivery.local_adapters import (
    LocalIvrAdapter,
    LocalInAppAdapter,
    LocalSmsAdapter,
    LocalWhatsAppAdapter,
    resolve_local_adapter,
)
from app.models import (
    Booking,
    Farmer,
    NotificationIntentChannel,
    NotificationIntent,
    NotificationIntentType,
    ProcurementCentre,
    SchedulingDecision,
)
from app.repositories import notification_intents as intent_repository
from app.services.notification_intents import create_for_decision
from app.services.notification_delivery import NotificationDeliveryService
from app.services import notification_intents
from app.services.scheduling import assess_booking
from app.services.scheduling_decisions import record_decision
from tests._auth_helpers import (
    auth_headers,
    create_admin,
    create_farmer_user,
    create_staff_user,
)


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    database_url = f"sqlite:///{tmp_path / 'notification_intents.sqlite3'}"
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


def _decision(session: Session, booking: Booking, reason_code: str) -> SchedulingDecision:
    decision = SchedulingDecision(
        booking_id=booking.id,
        centre_id=booking.centre_id,
        slot_id=booking.slot_id,
        evaluated_at=datetime.combine(booking.slot.slot_date, booking.slot.start_time),
        scheduling_status="DELAYED",
        recommendation="WARN_FARMER",
        estimated_completion_time=datetime.combine(
            booking.slot.slot_date, booking.slot.start_time
        ),
        slot_end_time=datetime.combine(booking.slot.slot_date, booking.slot.end_time),
        estimated_wait_minutes=0,
        farmers_ahead=0,
        prediction_provenance="LEGACY_ESTIMATOR",
        reason_code=reason_code,
        explanation="test decision",
        decision_version="v1",
    )
    session.add(decision)
    session.commit()
    return decision


@pytest.fixture
async def client(db_session: Session) -> AsyncClient:
    admin = create_admin(db_session, email="intent-admin@example.test")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers=auth_headers(admin),
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("reason_code", "notification_type"),
    [
        (
            "AT_RISK_PREDICTED_COMPLETION",
            NotificationIntentType.FARMER_SLOT_AT_RISK,
        ),
        (
            "DELAYED_NEW_SLOT_AVAILABLE",
            NotificationIntentType.FARMER_NEW_SLOT_PROPOSED,
        ),
        (
            "DELAYED_ALTERNATE_CENTRE_AVAILABLE",
            NotificationIntentType.FARMER_ALTERNATE_CENTRE_PROPOSED,
        ),
    ],
)
def test_mapped_decision_creates_one_pending_intent(
    db_session: Session,
    reason_code: str,
    notification_type: NotificationIntentType,
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    decision = _decision(db_session, booking, reason_code)

    first = create_for_decision(db_session, decision)
    second = create_for_decision(db_session, decision)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.notification_type == notification_type
    assert first.status.value == "PENDING"
    assert first.booking_id == booking.id
    assert first.centre_id == booking.centre_id
    assert first.payload["decision_id"] == decision.id
    assert "phone" not in first.payload
    assert db_session.scalar(
        select(NotificationIntent).where(NotificationIntent.decision_id == decision.id)
    ) is not None


def test_on_track_and_no_alternative_create_no_intent(db_session: Session) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    on_track = _decision(db_session, booking, "ON_TRACK_KEEP_SLOT")
    no_alternative = _decision(db_session, booking, "DELAYED_NO_ALTERNATIVE")

    assert create_for_decision(db_session, on_track) is None
    assert create_for_decision(db_session, no_alternative) is None
    assert db_session.scalars(select(NotificationIntent)).all() == []


def test_distinct_decisions_for_one_booking_create_distinct_intents(
    db_session: Session,
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None

    first_decision = _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    first_intent = create_for_decision(db_session, first_decision)
    assert first_intent is not None
    assert create_for_decision(db_session, first_decision).id == first_intent.id

    second_decision = _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    second_intent = create_for_decision(db_session, second_decision)

    assert second_intent is not None
    assert second_intent.id != first_intent.id
    assert second_intent.decision_id == second_decision.id
    assert second_intent.booking_id == booking.id
    assert db_session.query(NotificationIntent).count() == 2


def test_decision_remains_persisted_when_intent_persistence_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    assessment = assess_booking(db_session, booking.id)

    def fail_intent_persistence(*args, **kwargs):
        raise RuntimeError("notification persistence failed")

    monkeypatch.setattr(
        notification_intents, "create_for_decision", fail_intent_persistence
    )

    with pytest.raises(RuntimeError, match="notification persistence failed"):
        record_decision(db_session, assessment)

    persisted = db_session.scalars(
        select(SchedulingDecision).where(SchedulingDecision.booking_id == booking.id)
    ).all()
    assert len(persisted) == 1
    assert db_session.scalars(
        select(NotificationIntent).where(NotificationIntent.booking_id == booking.id)
    ).all() == []


def test_all_channels_resolve_to_deterministic_local_adapters() -> None:
    assert isinstance(
        resolve_local_adapter(NotificationIntentChannel.IN_APP), LocalInAppAdapter
    )
    assert isinstance(
        resolve_local_adapter(NotificationIntentChannel.SMS), LocalSmsAdapter
    )
    assert isinstance(
        resolve_local_adapter(NotificationIntentChannel.WHATSAPP),
        LocalWhatsAppAdapter,
    )
    assert isinstance(
        resolve_local_adapter(NotificationIntentChannel.IVR), LocalIvrAdapter
    )


def test_delivery_is_deterministic_and_idempotent(db_session: Session) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    intent = create_for_decision(
        db_session, _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    )
    assert intent is not None

    service = NotificationDeliveryService()
    first = service.deliver(db_session, intent.id)
    second = service.deliver(db_session, intent.id)

    assert first.result.success is True
    assert first.intent.status.value == "DELIVERED"
    assert first.result.reference_id == f"local-in_app-{intent.id}"
    assert second.already_processed is True
    assert second.result.reference_id == first.result.reference_id


def test_forced_adapter_failure_persists_failed_without_retry(
    db_session: Session,
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    intent = create_for_decision(
        db_session, _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    )
    assert intent is not None

    service = NotificationDeliveryService(
        adapter_resolver=lambda channel: resolve_local_adapter(
            channel, force_failure=True
        )
    )
    outcome = service.deliver(db_session, intent.id)

    assert outcome.result.success is False
    assert outcome.intent.status.value == "FAILED"
    assert outcome.intent.failure_reason == "Forced local adapter failure"
    repeated = service.deliver(db_session, intent.id)
    assert repeated.already_processed is True
    assert repeated.result.success is False


def test_adapter_exception_transitions_processing_intent_to_failed(
    db_session: Session,
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    intent = create_for_decision(
        db_session, _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    )
    assert intent is not None

    class RaisingAdapter:
        def deliver(self, request):
            raise RuntimeError("local adapter crashed")

    service = NotificationDeliveryService(
        adapter_resolver=lambda channel: RaisingAdapter()
    )
    with pytest.raises(RuntimeError, match="local adapter crashed"):
        service.deliver(db_session, intent.id)

    db_session.expire_all()
    failed = intent_repository.get_by_id(db_session, intent.id)
    assert failed is not None
    assert str(failed.status) in {"FAILED", "NotificationIntentStatus.FAILED"}
    assert failed.failure_reason == "local adapter crashed"


def test_competing_sessions_only_one_claim_and_delivery(
    db_session: Session,
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    intent = create_for_decision(
        db_session, _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    )
    assert intent is not None
    barrier = Barrier(2)
    engine = db_session.get_bind()

    def compete() -> int | None:
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            barrier.wait()
            claimed = intent_repository.claim_pending(session, intent.id)
            return claimed.id if claimed is not None else None
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: compete(), (1, 2)))

    assert sorted(claims, key=lambda value: value is None) == [intent.id, None]
    winning_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        delivered = intent_repository.mark_delivered(
            winning_session, intent.id, f"local-in_app-{intent.id}"
        )
        assert delivered.status.value == "DELIVERED"
        assert delivered.provider_reference == f"local-in_app-{intent.id}"
    finally:
        winning_session.close()

    final = intent_repository.get_by_id(db_session, intent.id)
    assert final is not None
    db_session.expire_all()
    final = intent_repository.get_by_id(db_session, intent.id)
    assert final is not None
    assert final.status.value == "DELIVERED"
    assert final.provider_reference == f"local-in_app-{intent.id}"


def test_recent_processing_intent_cannot_be_reclaimed(db_session: Session) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    intent = create_for_decision(
        db_session, _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    )
    assert intent is not None
    intent.status = "PROCESSING"
    intent.processing_started_at = datetime.now(timezone.utc)
    db_session.commit()

    assert intent_repository.claim_pending(db_session, intent.id) is None


def test_stale_processing_intent_can_be_reclaimed_and_delivered(
    db_session: Session,
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    intent = create_for_decision(
        db_session, _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    )
    assert intent is not None
    intent.status = "PROCESSING"
    intent.processing_started_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    reclaimed = intent_repository.claim_pending(db_session, intent.id)
    assert reclaimed is not None
    assert str(reclaimed.status) in {"PROCESSING", "NotificationIntentStatus.PROCESSING"}

    outcome = NotificationDeliveryService().deliver(db_session, intent.id)
    assert outcome.already_processed is True

    intent.status = "PROCESSING"
    intent.processing_started_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    outcome = NotificationDeliveryService().deliver(db_session, intent.id)
    assert outcome.result.success is True
    assert outcome.intent.status.value == "DELIVERED"


@pytest.mark.anyio
async def test_booking_intents_endpoint_enforces_farmer_scope(
    client: AsyncClient, db_session: Session
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    decision = _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    create_for_decision(db_session, decision)

    response = await client.get(f"/api/notifications/bookings/{booking.id}/intents")
    assert response.status_code == 200
    assert response.json()[0]["decision_id"] == decision.id

    other_farmer = db_session.scalar(
        select(Farmer).where(Farmer.id != booking.farmer_id).order_by(Farmer.id)
    )
    assert other_farmer is not None
    other_user = create_farmer_user(
        db_session, other_farmer, email="intent-other-farmer@example.test"
    )
    client.headers.update(auth_headers(other_user))
    forbidden = await client.get(f"/api/notifications/bookings/{booking.id}/intents")
    assert forbidden.status_code == 403


@pytest.mark.anyio
async def test_booking_intents_endpoint_enforces_staff_centre_scope(
    client: AsyncClient, db_session: Session
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    other_centre = db_session.scalar(
        select(ProcurementCentre)
        .where(ProcurementCentre.id != booking.centre_id)
        .order_by(ProcurementCentre.id)
    )
    assert other_centre is not None
    other_booking = db_session.scalar(
        select(Booking)
        .where(Booking.centre_id == other_centre.id)
        .order_by(Booking.id)
    )
    assert other_booking is not None
    decision = _decision(db_session, other_booking, "AT_RISK_PREDICTED_COMPLETION")
    create_for_decision(db_session, decision)

    staff = create_staff_user(
        db_session,
        db_session.get(ProcurementCentre, booking.centre_id),
        email="intent-staff@example.test",
    )
    client.headers.update(auth_headers(staff))
    forbidden = await client.get(
        f"/api/notifications/bookings/{other_booking.id}/intents"
    )
    assert forbidden.status_code == 403


@pytest.mark.anyio
async def test_staff_delivery_endpoint_delivers_only_authorized_intent(
    client: AsyncClient, db_session: Session
) -> None:
    booking = db_session.scalar(select(Booking).order_by(Booking.id))
    assert booking is not None
    decision = _decision(db_session, booking, "AT_RISK_PREDICTED_COMPLETION")
    intent = create_for_decision(db_session, decision)
    assert intent is not None

    response = await client.post(f"/api/notifications/intents/{intent.id}/deliver")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DELIVERED"
    assert body["reference_id"] == f"local-in_app-{intent.id}"

    farmer = db_session.get(Farmer, booking.farmer_id)
    assert farmer is not None
    farmer_user = create_farmer_user(
        db_session, farmer, email="intent-delivery-farmer@example.test"
    )
    client.headers.update(auth_headers(farmer_user))
    forbidden = await client.post(
        f"/api/notifications/intents/{intent.id}/deliver"
    )
    assert forbidden.status_code == 403
