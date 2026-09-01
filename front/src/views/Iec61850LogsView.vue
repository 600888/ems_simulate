<template>
  <div class="protocol-workbench-view">
    <Iec61850LogsManager :channel-id="channelId" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import Iec61850LogsManager from "@/components/iec61850-logs/Iec61850LogsManager.vue";

const route = useRoute();
const channelId = ref(0);

watch(
  () => [route.path, route.query.channel_id] as const,
  ([path, value]) => {
    if (path === "/iec61850-logs") channelId.value = Number(value) || 0;
  },
  { immediate: true },
);
</script>

<style scoped>
.protocol-workbench-view {
  box-sizing: border-box;
  display: flex;
  flex: 1;
  min-height: 0;
  height: 100%;
  padding: 14px;
  background: var(--bg-main);
  overflow: hidden;
}
</style>
