<script setup lang="ts">
import { ref, computed } from "vue";

const props = defineProps<{ modelValue: File | null; label: string; accept: string }>();
const emit = defineEmits<{ "update:modelValue": [file: File | null] }>();

const isDragging = ref(false);
const inputRef = ref<HTMLInputElement | null>(null);

function handleDrop(event: DragEvent) {
  isDragging.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file) emit("update:modelValue", file);
}

function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  emit("update:modelValue", file ?? null);
}

function clearFile() {
  emit("update:modelValue", null);
  if (inputRef.value) inputRef.value.value = "";
}

const sizeLabel = computed(() => {
  if (!props.modelValue) return "";
  const kb = props.modelValue.size / 1024;
  return kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(0)} KB`;
});
</script>

<template>
  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ label }}</label>
    <div
      :class="[
        'rounded-lg border-2 border-dashed p-4 text-center cursor-pointer transition-colors',
        isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400',
      ]"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="handleDrop"
      @click="inputRef?.click()"
    >
      <input ref="inputRef" type="file" :accept="accept" class="hidden" @change="handleFileSelect" />

      <template v-if="modelValue">
        <p class="text-sm text-gray-800 font-medium">{{ modelValue.name }}</p>
        <p class="text-xs text-gray-500">{{ sizeLabel }}</p>
        <button
          type="button"
          class="text-xs text-red-600 hover:underline mt-1"
          @click.stop="clearFile"
        >
          Remove
        </button>
      </template>
      <template v-else>
        <p class="text-sm text-gray-500">Drop {{ accept }} file here, or click to browse</p>
      </template>
    </div>
  </div>
</template>