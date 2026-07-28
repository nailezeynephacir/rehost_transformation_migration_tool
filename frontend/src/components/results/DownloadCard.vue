<script setup lang="ts">
import { artifactDownloadUrl } from "../../api/rehostApi";
import type { Artifact } from "../../types/api";

const props = defineProps<{ runId: string; artifacts: Artifact[] }>();

function labelFor(artifact: Artifact): string {
  if (artifact.type === "generated_file") return artifact.name;
  if (artifact.type === "extraction_report" || artifact.type === "application_report") {
    return "Download Report (.txt)";
  }
  if (artifact.type === "transformation_json") return "Download Transformation Rules (.json)";
  return artifact.name;
}
</script>

<template>
  <div class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm space-y-2">
    <h3 class="text-sm font-medium text-gray-700">Downloads</h3>
    <div class="flex flex-wrap gap-2">
      <a
        v-for="artifact in props.artifacts"
        :key="artifact.name"
        :href="artifactDownloadUrl(props.runId, artifact.name)"
        class="inline-flex items-center rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-50"
        download
      >
        {{ labelFor(artifact) }}
      </a>
    </div>
  </div>
</template>