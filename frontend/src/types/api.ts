// Mirrors backend/app/schemas/runs.py directly. If a field changes on one
// side, it needs to change here too - this file IS the frontend's half of
// the contract, not just documentation of it.

export type RunStatus = "queued" | "running" | "completed" | "failed";
export type Operation = "extract" | "apply";
export type ResultStatus =
  | "Created"
  | "Applied"
  | "Skipped"
  | "Already Applied";

export interface RunCreatedResponse {
  run_id: string;
  status: "queued";
}

export interface ExtractionSummary {
  created: number;
  skipped: number;
  support_files_stored: number;
}

export interface ApplicationSummary {
  applied: number;
  skipped: number;
  already_applied: number;
}

export type RunSummary = ExtractionSummary | ApplicationSummary;

export interface TransformationResult {
  transformation_id: string | null;
  file: string;
  scope: string | null;
  function_name: string | null;
  status: ResultStatus;
  matched_macro: string | null;
  opening_line: number | null;
  reason: string;
  original_snippet: string | null;
  rehost_snippet: string | null;
  // Only ever populated for operation "apply" - this is the field that
  // makes the third diff pane possible.
  generated_snippet: string | null;
}

export interface Artifact {
  name: string;
  type: string;
}

export interface RunPendingResponse {
  run_id: string;
  operation: Operation;
  status: "queued" | "running";
  created_at: string;
  started_at: string | null;
  target_macros: string[] | null;
}

export interface RunFailedResponse {
  run_id: string;
  operation: Operation;
  status: "failed";
  error: string;
}

interface RunCompletedResponseBase {
  run_id: string;
  status: "completed";
  completed_at: string;
  target_macros: string[] | null;
  results: TransformationResult[];
  artifacts: Artifact[];
}

export interface ExtractionCompletedResponse
  extends RunCompletedResponseBase {
  operation: "extract";
  summary: ExtractionSummary;
}

export interface ApplicationCompletedResponse
  extends RunCompletedResponseBase {
  operation: "apply";
  summary: ApplicationSummary;
}

export type RunCompletedResponse =
  | ExtractionCompletedResponse
  | ApplicationCompletedResponse;

// The response shape genuinely varies by status - a union, not one loose
// type with everything optional, so callers are forced to narrow by
// `status` before touching fields that only exist on one variant.
export type RunResponse = RunPendingResponse | RunFailedResponse | RunCompletedResponse;

export interface ErrorResponse {
  error: { code: string; message: string };
}