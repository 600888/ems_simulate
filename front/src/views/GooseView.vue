<template>
  <div class="goose-view">
    <GooseSubscriberManager :channel-id="channelId" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import GooseSubscriberManager from '@/components/goose/GooseSubscriberManager.vue'

const route = useRoute()
const channelId = ref<number>(0)

// 监听路由变化，更新 channelId (侧边栏 GOOSE 节点会带上 ?channel_id=N)
watch(
  () => route.query.channel_id,
  (newVal) => {
    channelId.value = Number(newVal) || 0
  },
  { immediate: true },
)
</script>

<style lang="scss" scoped>
.goose-view {
  height: calc(100vh - var(--header-height) - var(--tags-height) - var(--footer-height));
  padding: 16px;
  box-sizing: border-box;
  background: #f5f7fa;
  overflow: hidden;
}
</style>
