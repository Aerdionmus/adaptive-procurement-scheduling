from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def scheduling_placeholder() -> dict[str, str]:
    return {"status": "scheduling module foundation ready"}
