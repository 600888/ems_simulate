<template>
  <div class="scl-view">
    <el-tabs v-model="activeTab" @tab-click="handleTabClick">
      <el-tab-pane :label="$t('scl.fileManager')" name="manager">
        <SclFileManager />
      </el-tab-pane>
    </el-tabs>

    <!-- 导入向导弹窗 -->
    <SclImportWizard
      v-if="showImportWizard"
      @close="showImportWizard = false"
    />

    <!-- 对比弹窗 -->
    <SclDiffViewer v-if="showDiffViewer" @close="showDiffViewer = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import SclFileManager from "@/components/scl/SclFileManager.vue";
import SclImportWizard from "@/components/scl/SclImportWizard.vue";
import SclDiffViewer from "@/components/scl/SclDiffViewer.vue";

const route = useRoute();
const router = useRouter();
const activeTab = ref("manager");
const showImportWizard = ref(false);
const showDiffViewer = ref(false);

onMounted(() => {
  // 如果路由 query 指定了对话框操作
  if (route.query.dialog === "import") showImportWizard.value = true;
  if (route.query.dialog === "diff") showDiffViewer.value = true;
});

function handleTabClick() {
  // SCL 管理目前只有文件管理器一个 tab，后续可扩展
}
</script>

<style scoped>
.scl-view {
  height: 100%;
  min-height: 0;
  flex: 1;
  padding: 16px;
  box-sizing: border-box;
  background: #f5f7fa;
  overflow: hidden;
}
</style>
