from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_centres_placeholder() -> dict[str, str]:
    return {"status": "centres module foundation ready"}
