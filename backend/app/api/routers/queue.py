from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.eta import QueueETAResponse
from app.schemas.queue import QueueCheckInCreate, QueueEntryResponse
from app.services import eta as eta_service
from app.services import queue as queue_service

router = APIRouter()


def _raise_queue_error(error: queue_service.QueueError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.post("/check-in", response_model=QueueEntryResponse, status_code=status.HTTP_201_CREATED)
async def check_in_booking(
    check_in_data: QueueCheckInCreate,
    session: Session = Depends(get_db),
) -> QueueEntryResponse:
    try:
        return queue_service.check_in_booking(
            session,
            check_in_data.booking_id,
            check_in_data.centre_id,
        )
    except queue_service.QueueError as error:
        _raise_queue_error(error)


@router.get("/centres/{centre_id}", response_model=list[QueueEntryResponse])
async def get_live_queue(
    centre_id: int,
    session: Session = Depends(get_db),
) -> list[QueueEntryResponse]:
    try:
        return queue_service.list_live_queue(session, centre_id)
    except queue_service.QueueError as error:
        _raise_queue_error(error)


@router.post("/centres/{centre_id}/call-next", response_model=QueueEntryResponse)
async def call_next_farmer(
    centre_id: int,
    session: Session = Depends(get_db),
) -> QueueEntryResponse:
    try:
        return queue_service.call_next_farmer(session, centre_id)
    except queue_service.QueueError as error:
        _raise_queue_error(error)


@router.post("/{queue_entry_id}/start-serving", response_model=QueueEntryResponse)
async def start_serving(
    queue_entry_id: int,
    session: Session = Depends(get_db),
) -> QueueEntryResponse:
    try:
        return queue_service.start_serving(session, queue_entry_id)
    except queue_service.QueueError as error:
        _raise_queue_error(error)


@router.post("/{queue_entry_id}/complete", response_model=QueueEntryResponse)
async def complete_service(
    queue_entry_id: int,
    session: Session = Depends(get_db),
) -> QueueEntryResponse:
    try:
        return queue_service.complete_service(session, queue_entry_id)
    except queue_service.QueueError as error:
        _raise_queue_error(error)


@router.post("/{queue_entry_id}/no-show", response_model=QueueEntryResponse)
async def mark_no_show(
    queue_entry_id: int,
    session: Session = Depends(get_db),
) -> QueueEntryResponse:
    try:
        return queue_service.mark_no_show(session, queue_entry_id)
    except queue_service.QueueError as error:
        _raise_queue_error(error)


@router.get("/{queue_entry_id}/eta", response_model=QueueETAResponse)
async def get_queue_eta(
    queue_entry_id: int,
    session: Session = Depends(get_db),
) -> QueueETAResponse:
    try:
        return eta_service.calculate_eta(session, queue_entry_id)
    except queue_service.QueueError as error:
        _raise_queue_error(error)
