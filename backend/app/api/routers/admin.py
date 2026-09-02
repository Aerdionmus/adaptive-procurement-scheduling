from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import throughput as throughput_repository
from app.schemas.throughput import ThroughputSnapshotResponse
from app.services import throughput as throughput_service

router = APIRouter()


@router.get("/")
async def admin_placeholder() -> dict[str, str]:
    return {"status": "admin module foundation ready"}


@router.get(
    "/throughput/{centre_id}",
    response_model=ThroughputSnapshotResponse,
)
async def get_latest_throughput(
    centre_id: int,
    session: Session = Depends(get_db),
) -> ThroughputSnapshotResponse:
    snapshot = throughput_repository.get_latest_snapshot(session, centre_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="No throughput snapshot is available for this centre yet",
        )
    return snapshot


@router.post(
    "/throughput/{centre_id}/recalculate",
    response_model=ThroughputSnapshotResponse,
)
async def recalculate_throughput(
    centre_id: int,
    session: Session = Depends(get_db),
) -> ThroughputSnapshotResponse:
    try:
        return throughput_service.recalculate_throughput_for_centre(session, centre_id)
    except throughput_service.ThroughputError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
