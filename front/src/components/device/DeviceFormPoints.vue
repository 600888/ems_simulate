<template>
  <div class="device-form-points">
    <!-- IEC 61850 服务端: ICD 文件导入 -->
    <template v-if="protocolType === 4 && connType === 2">
      <el-divider content-position="left">{{
        $t("device.icdImport")
      }}</el-divider>

      <el-form-item :label="$t('device.icdFile')">
        <el-upload
          ref="icdUploadRef"
          action="#"
          :auto-upload="true"
          :limit="1"
          :http-request="handleIcdFileRequest"
          accept=".icd,.scd,.cid,.xml"
        >
          <template #trigger>
            <el-button type="success" plain :icon="Upload">{{
              $t("device.selectIcd")
            }}</el-button>
          </template>
          <template #tip>
            <div class="el-upload__tip">
              {{ $t("device.icdTip") }}
            </div>
          </template>
        </el-upload>
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

    <!-- DL/T645: 标准库或 Excel 点表 -->
    <template v-else-if="protocolType === 3">
      <el-divider content-position="left">DL/T645 点表</el-divider>
      <el-form-item label="点表模式">
        <el-radio-group v-model="pointMode" :disabled="disabled">
          <el-radio-button value="standard">标准点表</el-radio-button>
          <el-radio-button value="import">导入点表</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-alert
        v-if="pointMode === 'standard'"
        title="将从内置 dlt645 标准数据项库自动生成完整点表"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form-item
        v-else
        :label="$t('device.pointFile')"
        class="point-file-row"
      >
        <el-upload
          ref="uploadRef"
          action="#"
          :auto-upload="true"
          :limit="1"
          :http-request="handleFileRequest"
          accept=".xlsx,.xls"
        >
          <template #trigger>
            <el-button type="success" plain :icon="Upload">{{
              $t("device.selectExcel")
            }}</el-button>
          </template>
          <template #tip>
            <div class="el-upload__tip">{{ $t("device.excelTip") }}</div>
          </template>
        </el-upload>
      </el-form-item>
    </template>

    <!-- 其他协议: Excel 点表导入 -->
    <template v-else>
      <el-divider content-position="left">{{
        $t("device.pointTable")
      }}</el-divider>

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
            <el-button type="success" plain :icon="Upload">{{
              $t("device.selectExcel")
            }}</el-button>
          </template>
          <template #tip>
            <div class="el-upload__tip">
              {{ $t("device.excelTip") }}
            </div>
          </template>
        </el-upload>
      </el-form-item>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch } from "vue";
import { Upload } from "@element-plus/icons-vue";

const props = defineProps<{
  protocolType?: number;
  connType?: number;
  disabled?: boolean;
  isEditMode?: boolean;
}>();

const uploadRef = ref();
const icdUploadRef = ref();

const emit = defineEmits<{
  (e: "file-change", file: any): void;
  (e: "icd-file-change", file: any): void;
  (e: "point-mode-change", mode: "standard" | "import"): void;
}>();

const pointMode = ref<"standard" | "import">(
  props.isEditMode ? "import" : "standard",
);

watch(
  () => props.isEditMode,
  (isEdit) => {
    pointMode.value = isEdit ? "import" : "standard";
  },
);
watch(
  pointMode,
  (mode) => {
    if (mode === "standard") {
      uploadRef.value?.clearFiles();
      emit("file-change", null);
    }
    emit("point-mode-change", mode);
  },
  { immediate: true },
);

const handleFileRequest = (options: any) => {
  emit("file-change", options.file);
  return Promise.resolve();
};

const handleIcdFileRequest = (options: any) => {
  emit("icd-file-change", options.file);
  return Promise.resolve();
};

const clearFiles = () => {
  uploadRef.value?.clearFiles();
  icdUploadRef.value?.clearFiles();
};

defineExpose({ clearFiles });
</script>

<style lang="scss" scoped>
.device-form-points {
  margin-top: 10px;
}
.point-file-row {
  margin-top: 14px;
}
</style>
