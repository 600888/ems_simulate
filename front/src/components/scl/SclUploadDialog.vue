<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t('scl.upload')"
    width="480px"
    :before-close="handleClose"
    destroy-on-close
  >
    <el-upload
      ref="uploadRef"
      drag
      :auto-upload="false"
      :on-change="handleFileChange"
      accept=".icd,.scd,.cid,.xml"
      :limit="1"
    >
      <el-icon class="upload-icon" :size="48"><UploadFilled /></el-icon>
      <div class="upload-text">{{ $t("addDevice.icdTip") }}</div>
      <template #tip>
        <div class="upload-hint">.icd / .scd / .cid / .xml</div>
      </template>
    </el-upload>
    <template #footer>
      <el-button @click="handleClose">{{ $t("common.cancel") }}</el-button>
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="!selectedFile"
        @click="handleUpload"
      >
        {{
          uploading
            ? $t("scl.uploadProgress", { pct: uploadProgress })
            : $t("scl.upload")
        }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";
import type { UploadInstance, UploadFile } from "element-plus";
import { uploadSclFile } from "@/api/sclApi";

const { t } = useI18n();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "success"): void;
}>();

const dialogVisible = ref(true);
const uploadRef = ref<UploadInstance>();
const selectedFile = ref<File | null>(null);
const uploading = ref(false);
const uploadProgress = ref(0);

function handleFileChange(uploadFile: UploadFile) {
  selectedFile.value = uploadFile.raw || null;
}

async function handleUpload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadProgress.value = 0;
  try {
    const formData = new FormData();
    formData.append("file", selectedFile.value);
    await uploadSclFile(formData);
    ElMessage.success(t("scl.uploadSuccess"));
    emit("success");
    handleClose();
  } catch (e) {
    // handled by interceptor
  } finally {
    uploading.value = false;
  }
}

function handleClose() {
  emit("close");
}
</script>

<style scoped>
.upload-icon {
  margin-bottom: 8px;
}
.upload-text {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.upload-hint {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
</style>
