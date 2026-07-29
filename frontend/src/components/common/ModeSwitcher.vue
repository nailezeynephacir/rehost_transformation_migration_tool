<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();

const modes = [
  { name: "extract", label: "Extract", path: "/extract" },
  { name: "apply", label: "Apply", path: "/apply" },
];

function isActive(name: string): boolean {
  return route.name === name;
}
</script>

<template>
  <header class="border-b border-gray-200 bg-white">
    <div class="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
      <div class="inline-flex rounded-lg border border-gray-200 bg-gray-100 p-1">
        <router-link
          v-for="mode in modes"
          :key="mode.name"
          :to="mode.path"
          :class="[
            'px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
            isActive(mode.name) ? 'bg-pink-600 text-white shadow-sm' : 'text-gray-500 hover:text-gray-700',
          ]"
        >
          {{ mode.label }}
        </router-link>
      </div>

      <!-- Story Time is intentionally standalone, outside the Extract/Apply switcher -->
      <router-link
        to="/story"
        :class="[
          'text-sm font-medium px-3 py-1 rounded-md transition-colors',
          route.name === 'story' ? 'bg-pink-600 text-white' : 'text-gray-500 hover:text-gray-700',
        ]"
      >
        Story Time
      </router-link>
    </div>
  </header>
</template>
