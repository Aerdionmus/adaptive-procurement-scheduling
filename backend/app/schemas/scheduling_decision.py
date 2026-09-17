from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SchedulingDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    centre_id: int
    slot_id: int
    evaluated_at: datetime
    scheduling_status: str
    recommendation: str
    estimated_completion_time: datetime
    slot_end_time: datetime
    estimated_wait_minutes: Decimal
    farmers_ahead: int
    prediction_status: str | None
    prediction_provenance: str
    recommended_slot_id: int | None
    recommended_centre_id: int | None
    reason_code: str
    explanation: str
    decision_version: str
