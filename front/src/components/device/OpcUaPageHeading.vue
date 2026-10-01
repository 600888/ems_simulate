<template>
  <header class="ua-page-heading">
    <div>
      <h2>{{ title }}</h2>
      <p v-if="description">{{ description }}</p>
    </div>
    <slot />
  </header>
</template>
<script setup lang="ts">
defineProps<{ title: string; description?: string }>();
</script>
