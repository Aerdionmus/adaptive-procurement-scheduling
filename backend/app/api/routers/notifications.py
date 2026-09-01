from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def notifications_placeholder() -> dict[str, str]:
    return {"status": "notifications module foundation ready"}
