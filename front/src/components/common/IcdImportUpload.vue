<template>
  <div class="icd-import-upload" style="display: contents">
    <!-- 隐藏的文件输入 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".icd,.scd,.cid,.xml"
      style="display: none"
      @change="onFileSelected"
    />

    <!-- 导入进度条 -->
    <div v-if="importing" class="icd-import-progress">
      <el-progress
        :percentage="100"
        :indeterminate="true"
        :duration="3"
        :stroke-width="4"
        :format="() => ''"
      />
      <p class="icd-import-hint">
        {{ $t("addDevice.icdImporting") }} ({{ importElapsed }}s)
      </p>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref } from "vue";
import { importIcdPoints } from "@/api/channelApi";
import type { PointImportResult } from "@/types/channel";

const emit = defineEmits<{
  (e: "file-change", file: File | null): void;
  (e: "import-start"): void;
  (e: "import-success", result: PointImportResult): void;
  (e: "import-error", error: any): void;
}>();

const fileInputRef = ref<HTMLInputElement | null>(null);
const importing = ref(false);
const importElapsed = ref(0);
let importTimer: number | null = null;
let selectedFile: File | null = null;

const onFileSelected = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  selectedFile = file;
  emit("file-change", file);
  // 重置 input 以便下次选择同一文件
  target.value = "";
};

const openFileDialog = () => {
  fileInputRef.value?.click();
};

const importIcd = async (channelId: number): Promise<PointImportResult | null> => {
  if (!selectedFile) {
    throw new Error("未选择 ICD 文件");
  }

  importing.value = true;
  importElapsed.value = 0;
  importTimer = window.setInterval(() => {
    importElapsed.value++;
  }, 1000);
  emit("import-start");

  try {
    const result = await importIcdPoints(channelId, selectedFile, "eth0", true);
    emit("import-success", result);
    return result;
  } catch (error) {
    emit("import-error", error);
    throw error;
  } finally {
    if (importTimer) {
      clearInterval(importTimer);
      importTimer = null;
    }
    importing.value = false;
  }
};

const clear = () => {
  selectedFile = null;
  importing.value = false;
  if (fileInputRef.value) fileInputRef.value.value = "";
  if (importTimer) {
    clearInterval(importTimer);
    importTimer = null;
  }
};

defineExpose({
  openFileDialog,
  importIcd,
  clear,
  getFile: () => selectedFile,
  importing,
});
</script>

<style lang="scss" scoped>
.icd-import-progress {
  .icd-import-hint {
    margin: 4px 0 0;
    font-size: 12px;
    color: #909399;
    text-align: center;
  }
}
</style>
