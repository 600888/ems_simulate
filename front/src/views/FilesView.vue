<script lang="ts" setup>
/**
 * IEC 61850 文件浏览器页面
 *
 * 通过 URL query 参数 channel_id 指定设备。
 * 侧边栏的 Files 分类节点点击后导航到本页面。
 */

import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import FileExplorer from "@/components/files/FileExplorer.vue";

const route = useRoute();
const channelId = ref<number>(0);

watch(
  () => [route.path, route.query.channel_id] as const,
  ([path, newVal]) => {
    if (path !== "/files") return;
    channelId.value = Number(newVal) || 0;
  },
  { immediate: true },
);
</script>

<template>
  <div class="files-view">
    <div v-if="channelId" class="files-content">
      <FileExplorer :channel-id="channelId" />
    </div>
    <div v-else class="files-empty">
      <el-empty :description="$t('views.files.selectDevicePrompt')" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.files-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.files-content {
  flex: 1;
  padding: 16px;
  background: var(--bg-main);
  overflow: auto;
}

.files-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: var(--bg-main);
}
</style>
