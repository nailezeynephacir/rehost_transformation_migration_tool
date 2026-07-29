<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { postApply } from "../api/rehostApi";
import { useRunPolling } from "../composables/useRunPolling";
import { parseTargetMacrosFromJson } from "../utils/parseTargetMacro";
import FileDropzone from "../components/upload/FileDropzone.vue";
import MacroChipList from "../components/common/MacroChipList.vue";
import SummaryCards from "../components/results/SummaryCards.vue";
import TransformationTable from "../components/results/TransformationTable.vue";
import DownloadCard from "../components/results/DownloadCard.vue";

const newOriginalFile = ref<File | null>(null);
const transformationsFile = ref<File | null>(null);
const uploadedMacros = ref<string[] | null>(null);

const { run, errorMessage, isSubmitting, isPending, start } = useRunPolling();

// Preview the macros a rules file was built for, read directly from the
// file the moment it's picked - purely informational, doesn't gate
// anything. Fails silently on a bad/unreadable file: the real, meaningful
// error already surfaces when the user actually hits Run and the backend
// validates the upload for real, so there's no need to alarm them before
// they've attempted anything.
watch(transformationsFile, async (file) => {
  uploadedMacros.value = null;
  if (!file) return;

  try {
    const text = await file.text();
    uploadedMacros.value = parseTargetMacrosFromJson(text);
  } catch {
    uploadedMacros.value = null;
  }
});

// No macro validation here, deliberately - apply doesn't use target_macros
// at all (confirmed against the real engine: it never re-derives target
// status, it only replays what extraction already decided).
const canRun = computed(
  () => !!newOriginalFile.value && !!transformationsFile.value && !isSubmitting.value && !isPending.value
);

function handleRun() {
  if (!newOriginalFile.value || !transformationsFile.value) return;
  start(() => postApply(newOriginalFile.value as File, transformationsFile.value as File));
}
</script>

<template>
  <div class="max-w-3xl mx-auto p-6 space-y-6">
    <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
      <h2 class="text-lg font-semibold text-gray-900">Apply transformations</h2>

      <div class="grid grid-cols-2 gap-4">
        <FileDropzone v-model="newOriginalFile" label="New Original Project (.zip)" accept=".zip" />
        <FileDropzone v-model="transformationsFile" label="Transformation Rules (.json)" accept=".json" />
      </div>

      <MacroChipList
        v-if="uploadedMacros?.length"
        label="Target macros in this file:"
        :macros="uploadedMacros"
      />

      <button
        type="button"
        :disabled="!canRun"
        :class="[
          'w-full rounded-lg py-2.5 text-sm font-medium transition-colors',
          canRun ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-200 text-gray-400 cursor-not-allowed',
        ]"
        @click="handleRun"
      >
        {{ isSubmitting ? "Starting…" : isPending ? "Running…" : "Run Application" }}
      </button>

      <p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>
    </div>

    <div v-if="run && isPending" class="text-center text-gray-500 text-sm">
      Run {{ run.run_id }} is {{ run.status }}\u2026
    </div>

    <div v-if="run && run.status === 'failed'" class="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
      Run failed: {{ run.error }}
    </div>

    <div v-if="run && run.status === 'completed'" class="space-y-4">
      <SummaryCards :summary="run.summary" />
      <TransformationTable :results="run.results" :show-macro-column="false" />
      <DownloadCard :run-id="run.run_id" :artifacts="run.artifacts" />
    </div>
  </div>
</template>