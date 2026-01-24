<template>
  <div class="device-form-points">
    <el-divider content-position="left">点表导入</el-divider>
    
    <el-form-item label="测点表格">
      <el-upload
        ref="uploadRef"
        action="#"
        :auto-upload="true"
        :limit="1"
        :http-request="handleFileRequest"
        accept=".xlsx,.xls"
      >
        <template #trigger>
          <el-button type="success" plain :icon="Upload">选择 Excel 文件</el-button>
        </template>
        <template #tip>
          <div class="el-upload__tip">
            支持 .xlsx 格式，包含遥测/遥信/遥控/遥调 四个 sheet
          </div>
        </template>
      </el-upload>
    </el-form-item>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue';
import { Upload } from "@element-plus/icons-vue";

const uploadRef = ref();

const emit = defineEmits<{
  (e: 'file-change', file: any): void;
}>();

const handleFileRequest = (options: any) => {
  emit('file-change', options.file);
  return Promise.resolve();
};

const clearFiles = () => {
  uploadRef.value?.clearFiles();
};

defineExpose({ clearFiles });
</script>

<style lang="scss" scoped>
.device-form-points {
  margin-top: 10px;
}
</style>
