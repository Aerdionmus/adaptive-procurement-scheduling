from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import ensure_centre_scope, require_admin, require_centre_staff_or_admin
from app.db.session import get_db
from app.models import User
from app.schemas.baseline_evaluation import BaselineEvaluationResponse
from app.services import baseline_evaluation

router = APIRouter()


@router.get("/all/completion-time", response_model=BaselineEvaluationResponse)
async def get_all_completion_time_evaluation(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> BaselineEvaluationResponse:
    return baseline_evaluation.evaluate_completion_time(session)


@router.get("/centres/{centre_id}/completion-time", response_model=BaselineEvaluationResponse)
async def get_centre_completion_time_evaluation(
    centre_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_centre_staff_or_admin),
) -> BaselineEvaluationResponse:
    ensure_centre_scope(current_user, centre_id)
    return baseline_evaluation.evaluate_completion_time(session, centre_id=centre_id)
