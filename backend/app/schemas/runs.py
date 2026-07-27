from typing import List, Literal, Optional, Union

from pydantic import BaseModel

# These three literals ARE the vocabulary decisions made:
# three statuses (not four), "run" not "job", async not blocking.
RunStatus = Literal["queued", "running", "completed", "failed"]
Operation = Literal["extract", "apply"]
ResultStatus = Literal["Applied", "Skipped", "Already Applied"]


class RunCreatedResponse(BaseModel):
    run_id: str
    status: Literal["queued"] = "queued"


class RunSummary(BaseModel):
    applied: int
    skipped: int
    already_applied: int


class TransformationResult(BaseModel):
    transformation_id: Optional[str] = None
    file: str
    scope: Optional[str] = None
    function_name: Optional[str] = None
    status: ResultStatus
    matched_macro: Optional[str] = None
    opening_line: Optional[int] = None
    reason: str
    original_snippet: Optional[str] = None
    rehost_snippet: Optional[str] = None
    # Only ever populated for operation="apply" - this is the field that
    # solves the "third diff pane" gap from the schema doc.
    generated_snippet: Optional[str] = None


class Artifact(BaseModel):
    name: str
    type: str


class RunPendingResponse(BaseModel):
    run_id: str
    operation: Operation
    status: Literal["queued", "running"]
    created_at: str
    started_at: Optional[str] = None
    target_macros: Optional[List[str]] = None


class RunFailedResponse(BaseModel):
    run_id: str
    operation: Operation
    status: Literal["failed"] = "failed"
    error: str


class RunCompletedResponse(BaseModel):
    run_id: str
    operation: Operation
    status: Literal["completed"] = "completed"
    completed_at: str
    target_macros: Optional[List[str]] = None
    summary: RunSummary
    results: List[TransformationResult]
    artifacts: List[Artifact]


# GET /runs/{run_id} returns one of three different shapes depending on
# status - a Union response_model documents all three in Swagger, rather
# than hiding the real shape behind a generic dict.
RunResponse = Union[RunPendingResponse, RunFailedResponse, RunCompletedResponse]


class ArtifactListResponse(BaseModel):
    artifacts: List[Artifact]