<template>
  <el-dialog
    v-model="visible"
    title="导出模型"
    width="480px"
    :before-close="handleClose"
    destroy-on-close
    class="export-dialog"
  >
    <div class="export-content">
      <p class="export-desc">选择导出格式，将 IEC 61850 服务器模型导出为文件。</p>

      <el-form label-position="top" class="export-form">
        <el-form-item label="导出格式">
          <el-radio-group v-model="exportType" class="export-type-group">
            <el-radio value="icd" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">ICD 文件</span>
                <span class="type-desc">SCL/ICD 标准格式，可导入其他工具</span>
              </div>
            </el-radio>
            <el-radio value="json" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">JSON 文件</span>
                <span class="type-desc">结构化 JSON 数据，便于程序处理</span>
              </div>
            </el-radio>
            <el-radio value="xml" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">XML 文件</span>
                <span class="type-desc">自定义 XML 格式，保留完整模型结构</span>
              </div>
            </el-radio>
            <el-radio value="csv" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">CSV 文件</span>
                <span class="type-desc">扁平化测点表，可用 Excel 打开</span>
              </div>
            </el-radio>
            <el-radio value="tree" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">树形文本</span>
                <span class="type-desc">树形结构文本，便于阅读浏览</span>
              </div>
            </el-radio>
          </el-radio-group>
        </el-form-item>

      </el-form>
    </div>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        @click="handleExport"
        :loading="exporting"
      >
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { exportModel, type ExportModelType } from '@/api/deviceApi';

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const visible = ref(false);
const exportType = ref<ExportModelType>('icd');
const exporting = ref(false);

watch(() => props.modelValue, (val) => {
  visible.value = val;
});

watch(visible, (val) => {
  emit('update:modelValue', val);
});

const handleClose = () => {
  visible.value = false;
};

const handleExport = async () => {
  exporting.value = true;
  try {
    await exportModel(props.deviceName, exportType.value);
    ElMessage.success('模型导出成功!');
    handleClose();
  } catch (error: any) {
    // 用户取消文件保存对话框
    if (error?.name === 'AbortError') {
      return;
    }
    ElMessage.error(error.message || '导出模型失败');
  } finally {
    exporting.value = false;
  }
};
</script>

<style lang="scss" scoped>
.export-dialog {
  :deep(.el-dialog__body) {
    padding: 16px 20px;
  }
}

.export-desc {
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.export-form {
  .export-type-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
  }

  .export-type-radio {
    width: 100%;
    height: auto;
    padding: 10px 14px;
    border: 1px solid var(--sidebar-border);
    border-radius: 8px;
    transition: all 0.2s ease;
    margin: 0;

    &:hover {
      border-color: var(--color-primary);
      background-color: rgba(59, 130, 246, 0.04);
    }

    &.is-checked {
      border-color: var(--color-primary);
      background-color: rgba(59, 130, 246, 0.08);
    }
  }

  .type-option {
    display: flex;
    flex-direction: column;
    gap: 2px;

    .type-name {
      font-weight: 600;
      font-size: 14px;
    }

    .type-desc {
      font-size: 12px;
      color: var(--text-secondary);
    }
  }
}
</style>
