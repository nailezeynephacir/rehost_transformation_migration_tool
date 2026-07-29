from fastapi import APIRouter

from app.schemas.runs import RunResponse
from app.services import run_service

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    return run_service.get_run_response(run_id)