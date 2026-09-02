from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_slots_placeholder() -> dict[str, str]:
    return {"status": "slots module foundation ready"}
