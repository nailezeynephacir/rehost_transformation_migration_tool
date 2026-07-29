from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.schemas.runs import ArtifactListResponse
from app.services import run_service

router = APIRouter(tags=["artifacts"])


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(run_id: str):
    return ArtifactListResponse(artifacts=run_service.list_artifacts(run_id))


# :path allows slashes in this segment, needed for artifact names like
# "generated_rehost/main.c". The actual safety check (allowlist +
# resolved-path containment) lives entirely in run_service.get_artifact_path -
# this route never touches the filesystem itself.
@router.get("/runs/{run_id}/artifacts/{artifact_name:path}")
async def get_artifact(run_id: str, artifact_name: str):
    artifact_path = run_service.get_artifact_path(run_id, artifact_name)
    return FileResponse(
        path=artifact_path,
        filename=artifact_path.name,
    )