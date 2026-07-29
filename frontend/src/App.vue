<script setup lang="ts">
import ModeSwitcher from "./components/common/ModeSwitcher.vue";
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <ModeSwitcher />
    <!-- No pipeline banner here - removed entirely per Friday's decision,
         not carried forward even as a stub. -->
    <router-view v-slot="{ Component }">
      <keep-alive>
        <component :is="Component" />
      </keep-alive>
    </router-view>
  </div>
</template>