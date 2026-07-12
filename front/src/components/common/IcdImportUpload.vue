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

  </div>
</template>

<script lang="ts" setup>
import { ref } from "vue";
import { importIcdPoints } from "@/api/channelApi";
import type { PointImportResult } from "@/types/channel";

type GooseImportMode = "model_only" | "local_publish" | "remote_subscribe" | "both";

const emit = defineEmits<{
  (e: "file-change", file: File | null): void;
  (e: "import-start"): void;
  (e: "import-success", result: PointImportResult): void;
  (e: "import-error", error: any): void;
}>();

const fileInputRef = ref<HTMLInputElement | null>(null);
const importing = ref(false);
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

const importIcd = async (
  channelId: number,
  _defaultMode: GooseImportMode = "model_only"
): Promise<PointImportResult | null> => {
  if (!selectedFile) {
    throw new Error("未选择 ICD 文件");
  }

  const file = selectedFile;
  importing.value = true;
  emit("import-start");

  try {
    const result = await importIcdPoints(
      channelId,
      file,
      "eth0",
      "model_only"
    );
    emit("import-success", result);
    return result;
  } catch (error) {
    emit("import-error", error);
    throw error;
  } finally {
    importing.value = false;
  }
};


const clear = () => {
  selectedFile = null;
  importing.value = false;
  if (fileInputRef.value) fileInputRef.value.value = "";
};

defineExpose({
  openFileDialog,
  importIcd,
  clear,
  getFile: () => selectedFile,
  importing,
});
</script>
