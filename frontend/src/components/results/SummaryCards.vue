<script setup lang="ts">
import type { RunSummary } from "../../types/api";

defineProps<{ summary: RunSummary }>();
</script>

<template>
  <div class="grid grid-cols-3 gap-4">
    <div class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p class="text-2xl font-semibold text-green-700">{{ summary.applied }}</p>
      <p class="text-sm text-gray-500">Applied</p>
    </div>
    <div class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p class="text-2xl font-semibold text-teal-700">{{ summary.already_applied }}</p>
      <p class="text-sm text-gray-500">Already Applied</p>
    </div>
    <div class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p class="text-2xl font-semibold text-gray-600">{{ summary.skipped }}</p>
      <p class="text-sm text-gray-500">Skipped</p>
    </div>
  </div>
</template>