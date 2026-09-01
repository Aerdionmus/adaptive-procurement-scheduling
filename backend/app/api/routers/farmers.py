from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_farmers_placeholder() -> dict[str, str]:
    return {"status": "farmers module foundation ready"}
