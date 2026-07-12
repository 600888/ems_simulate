<template>
  <main class="message-window">
    <MessageViewPanel :device-name="deviceName" fill-window />
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import MessageViewPanel from '@/components/device/MessageViewPanel.vue'

const route = useRoute()
const deviceName = computed(() => String(route.params.deviceName || ''))
</script>

<style scoped>
.message-window { width: 100vw; height: 100vh; padding: 16px; overflow: hidden; background: var(--bg-main); }
</style>
