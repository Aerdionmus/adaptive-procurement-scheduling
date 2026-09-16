from fastapi import APIRouter

from app.api.routers import (
    admin,
    auth,
    bookings,
    centres,
    farmers,
    notifications,
    procurement_telemetry,
    prediction,
    telemetry_dataset,
    queue,
    reference,
    scheduling,
    simulation,
    slots,
    system,
)

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(farmers.router, prefix="/farmers", tags=["farmers"])
api_router.include_router(centres.router, prefix="/centres", tags=["centres"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
api_router.include_router(slots.router, prefix="/slots", tags=["slots"])
api_router.include_router(queue.router, prefix="/queue", tags=["queue"])
api_router.include_router(
    scheduling.router,
    prefix="/scheduling",
    tags=["scheduling"],
)
api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["notifications"],
)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(reference.router, prefix="/reference", tags=["reference"])
api_router.include_router(
    procurement_telemetry.router,
    prefix="/procurement-telemetry",
    tags=["procurement-telemetry"],
)
api_router.include_router(prediction.router, prefix="/predictions", tags=["predictions"])
api_router.include_router(
    telemetry_dataset.router,
    prefix="/telemetry-dataset",
    tags=["telemetry-dataset"],
)
api_router.include_router(simulation.router, prefix="/simulation", tags=["simulation"])
