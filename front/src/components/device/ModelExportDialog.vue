<template>
  <el-dialog
    v-model="visible"
    :title="$t('modelExport.title')"
    width="480px"
    :before-close="handleClose"
    destroy-on-close
    class="export-dialog"
  >
    <div class="export-content">
      <p class="export-desc">{{ $t('modelExport.desc') }}</p>

      <el-form label-position="top" class="export-form">
        <el-form-item :label="$t('modelExport.format')">
          <el-radio-group v-model="exportType" class="export-type-group">
            <el-radio value="icd" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">{{ $t('modelExport.icdFile') }}</span>
                <span class="type-desc">{{ $t('modelExport.icdDesc') }}</span>
              </div>
            </el-radio>
            <el-radio value="json" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">{{ $t('modelExport.jsonFile') }}</span>
                <span class="type-desc">{{ $t('modelExport.jsonDesc') }}</span>
              </div>
            </el-radio>
            <el-radio value="xml" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">{{ $t('modelExport.xmlFile') }}</span>
                <span class="type-desc">{{ $t('modelExport.xmlDesc') }}</span>
              </div>
            </el-radio>
            <el-radio value="csv" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">{{ $t('modelExport.csvFile') }}</span>
                <span class="type-desc">{{ $t('modelExport.csvDesc') }}</span>
              </div>
            </el-radio>
            <el-radio value="tree" class="export-type-radio">
              <div class="type-option">
                <span class="type-name">{{ $t('modelExport.treeFile') }}</span>
                <span class="type-desc">{{ $t('modelExport.treeDesc') }}</span>
              </div>
            </el-radio>
          </el-radio-group>
        </el-form-item>

      </el-form>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
      <el-button
        type="primary"
        @click="handleExport"
        :loading="exporting"
      >
        {{ $t('common.export') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { exportModel, type ExportModelType } from '@/api/deviceApi';

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const { t } = useI18n()
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
  const type = exportType.value;
  const extMap: Record<string, string> = { icd: '.icd', json: '.json', xml: '.xml', csv: '.csv', tree: '.txt' };
  const mimeMap: Record<string, string> = { icd: 'application/xml', json: 'application/json', xml: 'application/xml', csv: 'text/csv', tree: 'text/plain' };
  const defaultFilename = `${props.deviceName}_model${extMap[type] || '.icd'}`;

  let fileHandle: FileSystemFileHandle | null = null;

  // ✅ 关键：showSaveFilePicker 必须是用户点击后的第一个异步操作
  if (typeof (window as any).showSaveFilePicker === 'function') {
    try {
      // ✅ 对非标准扩展名做兼容处理
      const accept = type === 'icd'
        ? { 'application/xml': ['.icd', '.xml'] }
        : { [mimeMap[type]]: [extMap[type]] };

      fileHandle = await (window as any).showSaveFilePicker({
        suggestedName: defaultFilename,
        types: [{ description: `${type.toUpperCase()} File`, accept }],
      });
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      console.error('showSaveFilePicker error:', err);
      ElMessage.error(err.message || 'Failed to open save dialog');
      return; // ✅ 阻止后续导出逻辑
    }
  }

  // ✅ 在对话框成功打开/关闭后才设置 loading
  exporting.value = true;
  try {
    await exportModel(props.deviceName, type, fileHandle, defaultFilename);
    ElMessage.success(t('modelExport.exportSuccess'));
    handleClose();
  } catch (error: any) {
    if (error?.name !== 'AbortError') {
      ElMessage.error(error.message || t('modelExport.exportFailed'));
    }
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
