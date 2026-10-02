<template>
  <header class="ua-page-heading">
    <div class="ua-heading-copy">
      <h2>{{ title }}</h2>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="ua-heading-actions">
      <slot />
    </div>
  </header>
</template>
<script setup lang="ts">
defineProps<{ title: string; description?: string }>();
</script>

<style scoped>
.ua-heading-copy {
  flex: 1 1 320px;
  min-width: 0;
}
.ua-heading-copy h2,
.ua-heading-copy p {
  overflow-wrap: anywhere;
}
.ua-heading-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
}
.ua-heading-actions :deep(.el-radio-group) {
  flex-wrap: wrap;
  max-width: 100%;
}
</style>
