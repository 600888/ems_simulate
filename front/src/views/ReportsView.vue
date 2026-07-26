<template>
  <div class="reports-view">
    <ReportsManager :channel-id="channelId" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import ReportsManager from "@/components/reports/ReportsManager.vue";

const route = useRoute();
const channelId = ref<number>(0);

// 监听路由变化，更新 channelId
// 注意：keep-alive 缓存后 route.query 仍会响应全局路由变化，
// 必须加上 path 判断，避免其他页面（如 Files）的 query 被误当成 Reports 的 channelId
watch(
  () => [route.path, route.query.channel_id] as const,
  ([path, newVal]) => {
    if (path !== "/reports") return;
    channelId.value = Number(newVal) || 0;
  },
  { immediate: true },
);
</script>

<style scoped>
.reports-view {
  height: 100%;
  min-height: 0;
  flex: 1;
  padding: 16px;
  box-sizing: border-box;
  background: var(--bg-main);
  overflow: hidden;
}
</style>
