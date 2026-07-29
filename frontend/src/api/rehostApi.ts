import { apiClient } from "./clients";
import type { RunCreatedResponse, RunResponse } from "../types/api";

export async function postExtract(
  original: File,
  rehost: File,
  targetMacros: string[]
): Promise<RunCreatedResponse> {
  const form = new FormData();
  form.append("original", original);
  form.append("rehost", rehost);
  targetMacros.forEach((macro) => form.append("target_macros", macro));

  const response = await apiClient.post<RunCreatedResponse>("/extract", form);
  return response.data;
}

export async function postApply(
  newOriginal: File,
  transformations: File
): Promise<RunCreatedResponse> {
  const form = new FormData();
  form.append("new_original", newOriginal);
  form.append("transformations", transformations);

  const response = await apiClient.post<RunCreatedResponse>("/apply", form);
  return response.data;
}

export async function getRun(runId: string): Promise<RunResponse> {
  const response = await apiClient.get<RunResponse>(`/runs/${runId}`);
  return response.data;
}

export function artifactDownloadUrl(runId: string, artifactName: string): string {
  const base = apiClient.defaults.baseURL ?? "";
  return `${base}/runs/${runId}/artifacts/${artifactName}`;
}