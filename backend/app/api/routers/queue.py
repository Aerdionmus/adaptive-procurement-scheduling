from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def queue_placeholder() -> dict[str, str]:
    return {"status": "queue module foundation ready"}
