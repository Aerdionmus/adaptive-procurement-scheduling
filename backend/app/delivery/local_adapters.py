from __future__ import annotations

from app.models import NotificationIntentChannel

from app.delivery.contracts import DeliveryAdapter, DeliveryRequest, DeliveryResult


class LocalDeterministicAdapter(DeliveryAdapter):
    def __init__(
        self, channel: NotificationIntentChannel, *, force_failure: bool = False
    ) -> None:
        self.channel = channel
        self.force_failure = force_failure

    def deliver(self, request: DeliveryRequest) -> DeliveryResult:
        if request.channel != self.channel:
            raise ValueError("Delivery request channel does not match adapter")
        if request.intent_id <= 0 or not request.payload:
            raise ValueError("Delivery request is invalid")
        if self.force_failure:
            return DeliveryResult(
                success=False,
                failure_reason="Forced local adapter failure",
            )
        return DeliveryResult(
            success=True,
            reference_id=f"local-{self.channel.value.lower()}-{request.intent_id}",
        )


class LocalInAppAdapter(LocalDeterministicAdapter):
    def __init__(self, *, force_failure: bool = False) -> None:
        super().__init__(NotificationIntentChannel.IN_APP, force_failure=force_failure)


class LocalSmsAdapter(LocalDeterministicAdapter):
    def __init__(self, *, force_failure: bool = False) -> None:
        super().__init__(NotificationIntentChannel.SMS, force_failure=force_failure)


class LocalWhatsAppAdapter(LocalDeterministicAdapter):
    def __init__(self, *, force_failure: bool = False) -> None:
        super().__init__(NotificationIntentChannel.WHATSAPP, force_failure=force_failure)


class LocalIvrAdapter(LocalDeterministicAdapter):
    def __init__(self, *, force_failure: bool = False) -> None:
        super().__init__(NotificationIntentChannel.IVR, force_failure=force_failure)


_ADAPTERS = {
    NotificationIntentChannel.IN_APP: LocalInAppAdapter,
    NotificationIntentChannel.SMS: LocalSmsAdapter,
    NotificationIntentChannel.WHATSAPP: LocalWhatsAppAdapter,
    NotificationIntentChannel.IVR: LocalIvrAdapter,
}


def resolve_local_adapter(
    channel: NotificationIntentChannel, *, force_failure: bool = False
) -> LocalDeterministicAdapter:
    adapter_type = _ADAPTERS.get(channel)
    if adapter_type is None:
        raise ValueError(f"Unsupported notification channel: {channel}")
    return adapter_type(force_failure=force_failure)
