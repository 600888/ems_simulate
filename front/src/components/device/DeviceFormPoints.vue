<template>
  <div class="device-form-points">
    <!-- IEC 61850 服务端: ICD 文件导入 -->
    <template v-if="protocolType === 4 && connType === 2">
      <el-divider content-position="left">{{ $t('device.icdImport') }}</el-divider>

      <el-form-item :label="$t('device.icdFile')">
        <div class="icd-upload-row">
          <IcdImportUpload ref="icdUploadRef" @file-change="onIcdFileChange" />

          <el-button type="success" plain :icon="Upload" @click="icdUploadRef?.openFileDialog()">
            {{ $t('device.selectIcd') }}
          </el-button>

          <el-button
            v-if="hasIcdFile"
            type="warning"
            plain
            :icon="View"
            :loading="previewLoading"
            @click="handlePreview"
          >
            {{ $t('addDevice.previewIcd') }}
          </el-button>
        </div>
      </el-form-item>
    </template>

    <!-- IEC 61850 客户端提示 -->
    <template v-else-if="protocolType === 4 && connType === 1">
      <el-alert
        :title="$t('device.clientNoIcdNeeded')"
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 16px"
      />
    </template>

    <!-- 其他协议: Excel 点表导入 -->
    <template v-else>
      <el-divider content-position="left">{{ $t('device.pointTable') }}</el-divider>

      <el-form-item :label="$t('device.pointFile')">
        <el-upload
          ref="uploadRef"
          action="#"
          :auto-upload="true"
          :limit="1"
          :http-request="handleFileRequest"
          accept=".xlsx,.xls"
        >
          <template #trigger>
            <el-button type="success" plain :icon="Upload">{{ $t('device.selectExcel') }}</el-button>
          </template>
          <template #tip>
            <div class="el-upload__tip">
              {{ $t('device.excelTip') }}
            </div>
          </template>
        </el-upload>
      </el-form-item>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { ref } from "vue";
import { Upload, View } from "@element-plus/icons-vue";
import IcdImportUpload from "@/components/common/IcdImportUpload.vue";
import { previewIcd } from "@/api/channelApi";
import type { PointImportResult } from "@/types/channel";

const props = defineProps<{
  protocolType?: number;
  connType?: number;
  disabled?: boolean;
}>();

const uploadRef = ref();
const icdUploadRef = ref<InstanceType<typeof IcdImportUpload>>();
const hasIcdFile = ref(false);
const previewLoading = ref(false);

const emit = defineEmits<{
  (e: "file-change", file: any): void;
  (e: "icd-preview-result", result: PointImportResult): void;
}>();

const handleFileRequest = (options: any) => {
  emit("file-change", options.file);
  return Promise.resolve();
};

const onIcdFileChange = (file: File | null) => {
  hasIcdFile.value = !!file;
};

const handlePreview = async () => {
  const file = icdUploadRef.value?.getFile()
  if (!file) return
  previewLoading.value = true
  try {
    const result = await previewIcd(file)
    emit('icd-preview-result', result)
  } catch (e: any) {
    console.error('预览 ICD 失败', e)
  } finally {
    previewLoading.value = false
  }
}

const clearFiles = () => {
  uploadRef.value?.clearFiles();
  icdUploadRef.value?.clear();
  hasIcdFile.value = false;
};

defineExpose({ clearFiles, getIcdUploadRef: () => icdUploadRef.value });
</script>

<style lang="scss" scoped>
.device-form-points {
  margin-top: 10px;
}

.icd-upload-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
