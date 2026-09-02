from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.api_router import api_router
from app.core.config import settings


def create_application() -> FastAPI:
    application = FastAPI(title=settings.api_title, version=settings.api_version)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix=settings.api_prefix)

    @application.get("/")
    async def root() -> dict[str, str]:
        return {"message": "Adaptive Procurement Scheduling API is running -v2"}

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return application


app = create_application()
