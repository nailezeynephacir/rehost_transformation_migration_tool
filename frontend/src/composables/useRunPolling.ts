import { ref, computed, onBeforeUnmount } from "vue";
import { getRun } from "../api/rehostApi";
import { extractErrorMessage } from "../api/clients";
import type { RunCreatedResponse, RunResponse } from "../types/api";

const POLL_INTERVAL_MS = 2000;

// Shared by ExtractView and ApplyView - both follow the identical
// submit -> get run_id -> poll -> render pattern. Extracted here rather
// than duplicated, since two real consumers is exactly the point at which
// that's justified, not before.
export function useRunPolling() {
  const run = ref<RunResponse | null>(null);
  const errorMessage = ref<string | null>(null);
  const isSubmitting = ref(false);

  let pollHandle: ReturnType<typeof setTimeout> | null = null;

  const isPending = computed(
    () => run.value?.status === "queued" || run.value?.status === "running"
  );

  async function start(startFn: () => Promise<RunCreatedResponse>) {
    isSubmitting.value = true;
    errorMessage.value = null;
    run.value = null;

    try {
      const created = await startFn();
      schedulePoll(created.run_id);
    } catch (error) {
      errorMessage.value = extractErrorMessage(error);
    } finally {
      isSubmitting.value = false;
    }
  }

  function schedulePoll(runId: string) {
    const poll = async () => {
      try {
        const response = await getRun(runId);
        run.value = response;

        if (response.status === "queued" || response.status === "running") {
          pollHandle = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (error) {
        errorMessage.value = extractErrorMessage(error);
      }
    };
    poll();
  }

  // Stop polling if the component using this composable unmounts mid-run -
  // otherwise a dangling timer keeps calling an API for a view that no
  // longer exists. Safe to call here: this composable is only ever invoked
  // synchronously from a component's own <script setup>, so this correctly
  // registers against whichever component called it.
  onBeforeUnmount(() => {
    if (pollHandle) clearTimeout(pollHandle);
  });

  return { run, errorMessage, isSubmitting, isPending, start };
}