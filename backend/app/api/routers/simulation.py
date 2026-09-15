from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import ensure_centre_scope, require_centre_staff_or_admin
from app.models import User
from app.schemas.simulation import (
    SimulationMetricsResponse,
    SimulationRunRequest,
    SimulationRunResponse,
    SimulationTraceResponse,
)
from app.services import simulation

router = APIRouter()


@router.post("/runs", response_model=SimulationRunResponse)
async def create_simulation(
    request: SimulationRunRequest,
    current_user: User = Depends(require_centre_staff_or_admin),
) -> SimulationRunResponse:
    ensure_centre_scope(current_user, request.centre_id)
    run_id, result = simulation.create_run(request)
    return SimulationRunResponse(run_id=run_id, **result)


@router.get("/runs/{run_id}", response_model=SimulationRunResponse)
async def read_simulation(
    run_id: str,
    current_user: User = Depends(require_centre_staff_or_admin),
) -> SimulationRunResponse:
    result = simulation.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    ensure_centre_scope(current_user, result["centre_id"])
    return SimulationRunResponse(run_id=run_id, **result)


def _scoped_run(run_id: str, current_user: User) -> dict:
    result = simulation.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    ensure_centre_scope(current_user, result["centre_id"])
    return result


@router.get("/runs/{run_id}/metrics", response_model=SimulationMetricsResponse)
async def read_simulation_metrics(
    run_id: str,
    current_user: User = Depends(require_centre_staff_or_admin),
) -> SimulationMetricsResponse:
    result = _scoped_run(run_id, current_user)
    return SimulationMetricsResponse(
        run_id=run_id,
        centre_id=result["centre_id"],
        scenario=result["scenario"],
        adaptive_metrics=result["adaptive_metrics"],
        baseline_metrics=result["baseline_metrics"],
        comparison=result["comparison"],
    )


@router.get("/runs/{run_id}/trace", response_model=SimulationTraceResponse)
async def read_simulation_trace(
    run_id: str,
    current_user: User = Depends(require_centre_staff_or_admin),
) -> SimulationTraceResponse:
    result = _scoped_run(run_id, current_user)
    return SimulationTraceResponse(
        run_id=run_id,
        centre_id=result["centre_id"],
        scenario=result["scenario"],
        trace=result["trace"],
    )
