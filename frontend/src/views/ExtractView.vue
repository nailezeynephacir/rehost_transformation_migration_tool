<script setup lang="ts">
import { computed } from "vue";
import { ref } from "vue";
import { postExtract } from "../api/rehostApi";
import { useRunPolling } from "../composables/useRunPolling";
import FileDropzone from "../components/upload/FileDropzone.vue";
import TargetMacroInput from "../components/common/TargetMacroInput.vue";
import MacroChipList from "../components/common/MacroChipList.vue";
import SummaryCards from "../components/results/SummaryCards.vue";
import TransformationTable from "../components/results/TransformationTable.vue";
import DownloadCard from "../components/results/DownloadCard.vue";

const originalFile = ref<File | null>(null);
const rehostFile = ref<File | null>(null);
const targetMacros = ref<string[]>([]);

const { run, errorMessage, isSubmitting, start } = useRunPolling();

// Only valid (identifier-shaped) macros count toward "ready to run" -
// mirrors the same rule TargetMacroInput uses to flag chips, so the two
// don't quietly disagree with each other.
const IDENTIFIER_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
const hasValidMacro = computed(() => targetMacros.value.some((m) => IDENTIFIER_PATTERN.test(m)));

const canRun = computed(
  () => !!originalFile.value && !!rehostFile.value && hasValidMacro.value && !isSubmitting.value
);

function handleRun() {
  if (!originalFile.value || !rehostFile.value) return;
  start(() => postExtract(originalFile.value as File, rehostFile.value as File, targetMacros.value));
}
</script>

<template>
  <div class="max-w-3xl mx-auto p-6 space-y-6">
    <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
      <h2 class="text-lg font-semibold text-gray-900">Upload projects</h2>

      <div class="grid grid-cols-2 gap-4">
        <FileDropzone v-model="originalFile" label="Original Project (.zip)" accept=".zip" />
        <FileDropzone v-model="rehostFile" label="Rehosted Project (.zip)" accept=".zip" />
      </div>

      <TargetMacroInput v-model="targetMacros" />

      <button
        type="button"
        :disabled="!canRun"
        :class="[
          'w-full rounded-lg py-2.5 text-sm font-medium transition-colors',
          canRun ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-200 text-gray-400 cursor-not-allowed',
        ]"
        @click="handleRun"
      >
        {{ isSubmitting ? "Starting\u2026" : "Run Extraction" }}
      </button>

      <p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>
    </div>

    <div v-if="run && (run.status === 'queued' || run.status === 'running')" class="text-center text-gray-500 text-sm">
      Run {{ run.run_id }} is {{ run.status }}\u2026
    </div>

    <div v-if="run && run.status === 'failed'" class="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
      Run failed: {{ run.error }}
    </div>

    <div v-if="run && run.status === 'completed'" class="space-y-4">
      <MacroChipList
        v-if="run.target_macros?.length"
        label="This run searched for:"
        :macros="run.target_macros"
      />

      <SummaryCards :summary="run.summary" />
      <TransformationTable :results="run.results" />
      <DownloadCard :run-id="run.run_id" :artifacts="run.artifacts" />
    </div>
  </div>
</template>