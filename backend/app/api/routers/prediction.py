from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import ensure_centre_scope, require_centre_staff_or_admin
from app.db.session import get_db
from app.models import User
from app.schemas.prediction import ServiceTimePredictionResponse, ThroughputPrediction
from app.services import prediction as prediction_service

router = APIRouter()


@router.get(
    "/centres/{centre_id}/service-times",
    response_model=ServiceTimePredictionResponse,
)
async def get_service_time_predictions(
    centre_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> ServiceTimePredictionResponse:
    ensure_centre_scope(current_user, centre_id)
    return prediction_service.predict_service_times(session, centre_id)


@router.get(
    "/centres/{centre_id}/throughput",
    response_model=ThroughputPrediction,
)
async def get_throughput_prediction(
    centre_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> ThroughputPrediction:
    ensure_centre_scope(current_user, centre_id)
    return prediction_service.predict_throughput(session, centre_id)
