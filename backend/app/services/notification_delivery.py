from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.delivery.contracts import DeliveryAdapter, DeliveryRequest, DeliveryResult
from app.delivery.local_adapters import resolve_local_adapter
from app.models import NotificationIntent, NotificationIntentStatus
from app.repositories import notification_intents


@dataclass(frozen=True)
class DeliveryOutcome:
    intent: NotificationIntent
    result: DeliveryResult
    already_processed: bool = False


AdapterResolver = Callable[[object], DeliveryAdapter]


class NotificationDeliveryService:
    def __init__(self, adapter_resolver: AdapterResolver = resolve_local_adapter) -> None:
        self.adapter_resolver = adapter_resolver

    def deliver(self, session: Session, intent_id: int) -> DeliveryOutcome:
        intent = notification_intents.get_by_id(session, intent_id)
        if intent is None:
            raise ValueError("Notification intent not found")
        status = NotificationIntentStatus(intent.status)
        if status in (
            NotificationIntentStatus.DELIVERED,
            NotificationIntentStatus.FAILED,
            NotificationIntentStatus.SENT,
        ):
            return DeliveryOutcome(
                intent=intent,
                result=DeliveryResult(
                    success=status == NotificationIntentStatus.DELIVERED,
                    reference_id=intent.provider_reference,
                    failure_reason=intent.failure_reason,
                ),
                already_processed=True,
            )

        claimed = notification_intents.claim_pending(session, intent_id)
        if claimed is None:
            current = notification_intents.get_by_id(session, intent_id)
            if current is None:
                raise ValueError("Notification intent not found")
            return DeliveryOutcome(
                intent=current,
                result=DeliveryResult(
                    success=NotificationIntentStatus(current.status)
                    == NotificationIntentStatus.DELIVERED,
                    reference_id=current.provider_reference,
                    failure_reason=current.failure_reason,
                ),
                already_processed=True,
            )

        request = DeliveryRequest(
            intent_id=claimed.id,
            channel=claimed.channel,
            notification_type=claimed.notification_type,
            payload=claimed.payload,
        )
        try:
            result = self.adapter_resolver(claimed.channel).deliver(request)
        except Exception as error:
            notification_intents.mark_failed(session, intent_id, str(error))
            raise
        if result.success:
            persisted = notification_intents.mark_delivered(
                session, intent_id, result.reference_id
            )
        else:
            persisted = notification_intents.mark_failed(
                session, intent_id, result.failure_reason or "Delivery failed"
            )
        return DeliveryOutcome(intent=persisted, result=result)


def deliver_notification_intent(session: Session, intent_id: int) -> DeliveryOutcome:
    return NotificationDeliveryService().deliver(session, intent_id)
