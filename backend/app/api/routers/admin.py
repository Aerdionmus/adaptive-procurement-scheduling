from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def admin_placeholder() -> dict[str, str]:
    return {"status": "admin module foundation ready"}
