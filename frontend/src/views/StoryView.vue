<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";

const stages = [
  {
    label: "Extract",
    caption: "We compare your old and new code to find what's changed.",
  },
  {
    label: "Review",
    caption: "Every change comes with a clear reason, so nothing gets carried over silently.",
  },
  {
    label: "Apply",
    caption: "Then we carry those changes over to the new version \u2014 safely and automatically.",
  },
];

const activeIndex = ref(0);
const CYCLE_INTERVAL_MS = 3000;
let cycleHandle: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  cycleHandle = setInterval(() => {
    activeIndex.value = (activeIndex.value + 1) % stages.length;
  }, CYCLE_INTERVAL_MS);
});

// Same care as useRunPolling - don't leave a dangling timer running after
// the user navigates away from this screen.
onBeforeUnmount(() => {
  if (cycleHandle) clearInterval(cycleHandle);
});
</script>

<template>
  <div class="max-w-2xl mx-auto p-10 text-center space-y-10">
    <div>
      <h2 class="text-xl font-semibold text-gray-900">How it works</h2>
      <p class="text-sm text-gray-500 mt-1">A quick look at what happens behind the scenes.</p>
    </div>

    <div class="flex items-center justify-center">
      <template v-for="(stage, index) in stages" :key="stage.label">
        <div class="flex flex-col items-center gap-2">
          <div
            :class="[
              'w-14 h-14 rounded-full flex items-center justify-center text-sm font-medium transition-all duration-500',
              index === activeIndex
                ? 'bg-blue-600 text-white scale-110 shadow-md'
                : 'bg-gray-100 text-gray-400',
            ]"
          >
            {{ index + 1 }}
          </div>
          <span
            :class="[
              'text-sm font-medium transition-colors duration-500',
              index === activeIndex ? 'text-blue-700' : 'text-gray-400',
            ]"
          >
            {{ stage.label }}
          </span>
        </div>

        <div
          v-if="index < stages.length - 1"
          class="w-16 h-0.5 mx-2 mb-6 bg-gray-200 relative overflow-hidden"
        >
          <div
            :class="[
              'absolute inset-y-0 left-0 bg-blue-400 transition-all duration-500',
              index < activeIndex ? 'w-full' : 'w-0',
            ]"
          />
        </div>
      </template>
    </div>

    <p class="text-gray-700 text-base leading-relaxed min-h-[3rem] transition-opacity duration-500">
      {{ stages[activeIndex].caption }}
    </p>

    <p class="text-sm text-gray-500 leading-relaxed">
      This tool automatically carries previously-made rehosting changes from an older version of a
      project to a newer one, so you don't have to redo the work by hand every time the underlying
      code updates.
    </p>
  </div>
</template>