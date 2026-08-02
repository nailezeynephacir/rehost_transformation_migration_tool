<script setup lang="ts">
import { computed } from "vue";
import type { RunSummary } from "../../types/api";

const props = defineProps<{ summary: RunSummary }>();

const cards = computed(() => {
  if ("created" in props.summary) {
    return [
      {
        label: "Transformations Created",
        value: props.summary.created,
        color: "text-green-700",
      },
      {
        label: "Skipped Blocks",
        value: props.summary.skipped,
        color: "text-gray-600",
      },
      {
        label: "Support Files Stored",
        value: props.summary.support_files_stored,
        color: "text-teal-700",
      },
    ];
  }

  return [
    {
      label: "Applied",
      value: props.summary.applied,
      color: "text-green-700",
    },
    {
      label: "Already Applied",
      value: props.summary.already_applied,
      color: "text-teal-700",
    },
    {
      label: "Skipped",
      value: props.summary.skipped,
      color: "text-gray-600",
    },
  ];
});
</script>

<template>
  <div class="grid grid-cols-3 gap-4">
    <div
      v-for="card in cards"
      :key="card.label"
      class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
    >
      <p class="text-2xl font-semibold" :class="card.color">
        {{ card.value }}
      </p>
      <p class="text-sm text-gray-500">
        {{ card.label }}
      </p>
    </div>
  </div>
</template>