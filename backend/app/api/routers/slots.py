from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_slots_placeholder() -> dict[str, str]:
    return {"status": "slots module foundation ready"}
