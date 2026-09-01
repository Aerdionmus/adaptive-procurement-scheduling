from fastapi import APIRouter

router = APIRouter()


@router.get("/test")
def api_test() -> dict[str, str]:
    return {"message": "React successfully connected to FastAPI!"}
