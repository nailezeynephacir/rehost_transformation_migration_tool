<script setup lang="ts">
defineProps<{ label: string; macros: string[] }>();
</script>

<template>
  <div class="flex flex-wrap gap-2 items-center text-sm">
    <span class="text-gray-500">{{ label }}</span>
    <span
      v-for="macro in macros"
      :key="macro"
      class="rounded-full bg-gray-100 text-gray-600 text-xs px-2.5 py-1"
    >
      {{ macro }}
    </span>
  </div>
</template>