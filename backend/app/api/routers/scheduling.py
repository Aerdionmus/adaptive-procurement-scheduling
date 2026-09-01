from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def scheduling_placeholder() -> dict[str, str]:
    return {"status": "scheduling module foundation ready"}
