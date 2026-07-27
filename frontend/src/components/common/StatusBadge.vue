<script setup lang="ts">
import { computed } from "vue";
import type { ResultStatus } from "../../types/api";

const props = defineProps<{ status: ResultStatus }>();

// Deliberately only three keys - TypeScript will error at build time if
// ResultStatus ever grows a fourth value this map doesn't cover, rather
// than silently rendering nothing for it.
const styles: Record<ResultStatus, string> = {
  Applied: "bg-green-100 text-green-800",
  "Already Applied": "bg-teal-100 text-teal-800",
  Skipped: "bg-gray-100 text-gray-700",
};

const classes = computed(() => styles[props.status]);
</script>

<template>
  <span :class="['inline-block rounded-full px-2.5 py-0.5 text-xs font-medium', classes]">
    {{ status }}
  </span>
</template>