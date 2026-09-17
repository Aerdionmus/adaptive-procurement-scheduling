from app.models import SchedulingDecision
from app.repositories import scheduling_decisions as decision_repository
from app.services.scheduling import (
    SchedulingAssessment,
    SchedulingRecommendation,
    SchedulingStatus,
)


def _reason_code(assessment: SchedulingAssessment) -> str:
    if assessment.scheduling_status == SchedulingStatus.ON_TRACK:
        return "ON_TRACK_KEEP_SLOT"
    if assessment.scheduling_status == SchedulingStatus.AT_RISK:
        return "AT_RISK_PREDICTED_COMPLETION"
    if assessment.recommendation == SchedulingRecommendation.PROPOSE_NEW_SLOT:
        return "DELAYED_NEW_SLOT_AVAILABLE"
    if assessment.recommendation == SchedulingRecommendation.RECOMMEND_ALTERNATE_CENTRE:
        return "DELAYED_ALTERNATE_CENTRE_AVAILABLE"
    return "DELAYED_NO_ALTERNATIVE"


def record_decision(session, assessment: SchedulingAssessment) -> SchedulingDecision:
    return decision_repository.create_decision(
        session,
        SchedulingDecision(
            booking_id=assessment.booking_id,
            centre_id=assessment.centre_id,
            slot_id=assessment.slot_id,
            evaluated_at=assessment.calculated_at,
            scheduling_status=assessment.scheduling_status.value,
            recommendation=assessment.recommendation.value,
            estimated_completion_time=assessment.estimated_completion_time,
            slot_end_time=assessment.slot_end_time,
            estimated_wait_minutes=assessment.estimated_wait_minutes,
            farmers_ahead=assessment.farmers_ahead,
            prediction_status=assessment.prediction_status,
            prediction_provenance=assessment.prediction_provenance,
            recommended_slot_id=assessment.recommended_slot_id,
            recommended_centre_id=assessment.recommended_centre_id,
            reason_code=_reason_code(assessment),
            explanation=assessment.explanation,
            decision_version="v1",
        ),
    )
