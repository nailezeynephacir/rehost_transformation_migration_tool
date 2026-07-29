<script setup lang="ts">
import { ref, computed } from "vue";

const props = defineProps<{ modelValue: string[] }>();
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();

const draft = ref("");

// C preprocessor identifiers only: letters/digits/underscore, not starting
// with a digit. Matching is exact on the backend (confirmed, no wildcard
// support) - flagging an invalid entry here is cheaper than discovering a
// silently-empty result set after a run completes.
const IDENTIFIER_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

function isValid(macro: string): boolean {
  return IDENTIFIER_PATTERN.test(macro);
}

function commitDraft() {
  const value = draft.value.trim();
  if (!value) return;
  if (!props.modelValue.includes(value)) {
    emit("update:modelValue", [...props.modelValue, value]);
  }
  draft.value = "";
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault();
    commitDraft();
  }
}

function removeMacro(macro: string) {
  emit("update:modelValue", props.modelValue.filter((m) => m !== macro));
}

const showCount = computed(() => props.modelValue.length >= 3);
</script>

<template>
  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">
      Target Macros
      <span v-if="showCount" class="text-gray-400 font-normal">
        ({{ modelValue.length }} macros configured)
      </span>
    </label>

    <div class="flex flex-wrap gap-2 items-center rounded-lg border border-gray-300 p-2 min-h-[3rem] focus-within:border-blue-500">
      <span
        v-for="macro in modelValue"
        :key="macro"
        :class="[
          'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm',
          isValid(macro) ? 'bg-blue-100 text-blue-800' : 'bg-red-100 text-red-700 border border-red-400',
        ]"
      >
        {{ macro }}
        <button
          type="button"
          class="text-current opacity-60 hover:opacity-100"
          :aria-label="`Remove ${macro}`"
          @click="removeMacro(macro)"
        >
          &times;
        </button>
      </span>

      <input
        v-model="draft"
        type="text"
        placeholder="e.g. REHOST_MODE"
        class="flex-1 min-w-[8rem] outline-none text-sm py-1"
        @keydown="handleKeydown"
        @blur="commitDraft"
      />
    </div>

    <p class="text-xs text-gray-500 mt-1">
      The exact preprocessor macros that mark rehost changes. Add as many as you need.
    </p>
  </div>
</template>