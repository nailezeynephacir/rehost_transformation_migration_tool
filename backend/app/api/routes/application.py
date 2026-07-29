from fastapi import APIRouter, File, UploadFile, status

from app.schemas.runs import RunCreatedResponse
from app.services import application_service

router = APIRouter(tags=["application"])


@router.post("/apply", response_model=RunCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def apply(
    new_original: UploadFile = File(...),
    transformations: UploadFile = File(...),
):
    run_id = await application_service.start_application(new_original, transformations)
    return RunCreatedResponse(run_id=run_id)