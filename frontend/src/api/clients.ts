import axios from "axios";
import type { ErrorResponse } from "../types/api";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
});

// Unwraps the backend's standard {error: {code, message}} shape into a
// plain message string, so every caller doesn't need to know that shape
// individually - matches the "one standard error response" decision.
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.data) {
    const data = error.response.data as ErrorResponse;
    if (data.error?.message) {
      return data.error.message;
    }
  }
  return "An unexpected error occurred.";
}