<template>
  <div class="reports-view">
    <ReportsManager :channel-id="channelId" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import ReportsManager from '@/components/reports/ReportsManager.vue';

const route = useRoute();
const channelId = ref<number>(0);

// 监听路由变化，更新 channelId
watch(
  () => route.query.channel_id,
  (newVal) => {
    channelId.value = Number(newVal) || 0;
  },
  { immediate: true },
);
</script>

<style scoped>
.reports-view {
  height: 100%;
  padding: 16px;
  background: #f5f7fa;
}
</style>
