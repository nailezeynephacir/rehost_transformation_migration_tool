<script setup lang="ts">
import type { TransformationResult } from "../../types/api";

defineProps<{ result: TransformationResult }>();
</script>

<template>
  <div class="bg-gray-50 border-t border-gray-200 p-4 space-y-3">
    <p class="text-sm text-gray-700">{{ result.reason }}</p>

    <div :class="['grid gap-3', result.generated_snippet ? 'grid-cols-3' : 'grid-cols-2']">
      <div v-if="result.original_snippet">
        <p class="text-xs font-medium text-gray-500 mb-1">Original</p>
        <pre class="text-xs bg-white border border-gray-200 rounded-md p-2 overflow-x-auto font-mono">{{ result.original_snippet }}</pre>
      </div>
      <div v-if="result.rehost_snippet">
        <p class="text-xs font-medium text-gray-500 mb-1">Rehosted</p>
        <pre class="text-xs bg-white border border-gray-200 rounded-md p-2 overflow-x-auto font-mono">{{ result.rehost_snippet }}</pre>
      </div>
      <!-- Only ever rendered for Apply results - this is the field that
           didn't exist until the schema design solved the "third pane" gap. -->
      <div v-if="result.generated_snippet">
        <p class="text-xs font-medium text-gray-500 mb-1">Generated</p>
        <pre class="text-xs bg-white border border-gray-200 rounded-md p-2 overflow-x-auto font-mono">{{ result.generated_snippet }}</pre>
      </div>
    </div>
  </div>
</template>