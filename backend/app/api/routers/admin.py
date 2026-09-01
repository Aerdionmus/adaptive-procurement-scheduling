from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def admin_placeholder() -> dict[str, str]:
    return {"status": "admin module foundation ready"}
