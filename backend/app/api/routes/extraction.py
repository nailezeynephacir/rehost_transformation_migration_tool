from typing import List

from fastapi import APIRouter, File, Form, UploadFile, status

from app.schemas.runs import RunCreatedResponse
from app.services import extraction_service

router = APIRouter(tags=["extraction"])


@router.post("/extract", response_model=RunCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def extract(
    original: UploadFile = File(...),
    rehost: UploadFile = File(...),
    target_macros: List[str] = Form(...),
):
    run_id = await extraction_service.start_extraction(original, rehost, target_macros)
    return RunCreatedResponse(run_id=run_id)