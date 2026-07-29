<script setup lang="ts">
import { computed, ref } from "vue";
import type { TransformationResult } from "../../types/api";
import StatusBadge from "../common/StatusBadge.vue";
import TransformationDetails from "./TransformationDetails.vue";

const props = withDefaults(
  defineProps<{ results: TransformationResult[]; showMacroColumn?: boolean }>(),
  { showMacroColumn: true }
);

const expandedIndex = ref<number | null>(null);
const detailColspan = computed(() => (props.showMacroColumn ? 5 : 4));

function toggle(index: number) {
  expandedIndex.value = expandedIndex.value === index ? null : index;
}
</script>

<template>
  <div class="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
    <table class="w-full text-sm">
      <thead class="bg-gray-50 text-left text-xs text-gray-500 uppercase">
        <tr>
          <th class="px-4 py-2">File</th>
          <th class="px-4 py-2">Function</th>
          <th class="px-4 py-2">Scope</th>
          <th class="px-4 py-2">Status</th>
          <th v-if="showMacroColumn" class="px-4 py-2">Macro</th>
        </tr>
      </thead>
      <tbody>
        <template
          v-for="(result, index) in results"
          :key="result.transformation_id ?? `${result.file}-${index}`"
        >
          <tr
            class="border-t border-gray-100 cursor-pointer hover:bg-gray-50"
            @click="toggle(index)"
          >
            <td class="px-4 py-2 font-mono text-xs">{{ result.file }}</td>
            <td class="px-4 py-2 text-gray-600">{{ result.function_name ?? "\u2014" }}</td>
            <td class="px-4 py-2 text-gray-600">{{ result.scope ?? "\u2014" }}</td>
            <td class="px-4 py-2"><StatusBadge :status="result.status" /></td>
            <td v-if="showMacroColumn" class="px-4 py-2">
              <span
                v-if="result.matched_macro"
                class="inline-block rounded-full bg-gray-100 text-gray-600 text-xs px-2 py-0.5"
              >
                {{ result.matched_macro }}
              </span>
              <span v-else class="text-gray-300">&mdash;</span>
            </td>
          </tr>
          <tr v-if="expandedIndex === index">
            <td :colspan="detailColspan" class="p-0">
              <TransformationDetails :result="result" />
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>