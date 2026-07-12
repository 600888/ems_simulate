<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEditMode ? $t('addDevice.titleEdit') : $t('addDevice.titleAdd')"
    width="640px"
    :close-on-click-modal="false"
    @close="handleClose"
    class="modern-dialog"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="110px"
      label-position="right"
    >
      <DeviceFormBasic :model-value="form" :group-options="deviceGroupOptions" />

      <DeviceFormConfig
        :model-value="form"
        v-model:media-type="mediaType"
        :protocols="protocols"
        :serial-ports="serialPorts"
      />

      <DeviceFormPoints
        ref="uploadCompRef"
        :protocol-type="form.protocol_type"
        :conn-type="form.conn_type"
        :disabled="saving"
        @file-change="(f) => (selectedFile = f)"
        @icd-file-change="handleIcdFileChange"
      />

      <!-- 操作进度条 -->
      <div v-if="saving" class="icd-import-progress">
        <el-progress
          :percentage="100"
          :indeterminate="true"
          :duration="3"
          :stroke-width="4"
          :format="() => ''"
        />
        <p class="icd-import-hint">{{ progressText }} ({{ importElapsed }}s)</p>
      </div>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button
          v-if="isIec61850Server && icdFile && !saving"
          type="warning"
          plain
          :icon="View"
          :loading="previewLoading"
          @click="handlePreviewIcd"
        >
          {{ $t("addDevice.previewIcd") }}
        </el-button>
        <el-button :disabled="saving" @click="handleClose" round>{{
          $t("common.cancel")
        }}</el-button>
        <el-button
          type="primary"
          :disabled="saving"
          @click="handleSubmit"
          round
          class="submit-btn"
          :icon="Check"
        >
          {{ isEditMode ? $t("addDevice.saveChanges") : $t("addDevice.confirmAdd") }}
        </el-button>
      </div>
    </template>
  </el-dialog>

  <!-- GOOSE 预览对话框 -->
  <el-dialog
    v-model="goosePreviewVisible"
    :title="$t('addDevice.icdPreview')"
    width="90%"
    style="max-width: 1100px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-alert
      :title="
        $t('addDevice.mmsPoints', {
          total: goosePreviewData?.total || 0,
          yc: goosePreviewData?.yc_count || 0,
          yx: goosePreviewData?.yx_count || 0,
          yk: goosePreviewData?.yk_count || 0,
          yt: goosePreviewData?.yt_count || 0,
        })
      "
      type="success"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <div v-if="gooseControlList.length > 0">
      <el-alert
        :title="$t('addDevice.gooseControlBlocks', { count: gooseControlList.length })"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />

      <el-table :data="gooseControlList" border size="small" max-height="350">
        <el-table-column
          prop="go_cb_ref"
          label="GoCBRef"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column prop="go_id" label="GOOSE标识符 (GoID)" width="180" />
        <el-table-column prop="app_id" label="APPID" width="70" />
        <el-table-column
          prop="dat_set"
          label="DataSet"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column prop="conf_rev" label="ConfRev" width="70" />
        <el-table-column :label="$t('addDevice.macAddress')" width="140">
          <template #default="{ row }">{{ formatMac(row) }}</template>
        </el-table-column>
        <el-table-column
          :label="$t('addDevice.datasetMembers')"
          width="90"
          align="center"
        >
          <template #default="{ row }">{{ row.dataset_member_count }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else-if="previewDone">
      <el-alert
        :title="$t('addDevice.noGooseControl')"
        type="warning"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <el-button type="primary" @click="goosePreviewVisible = false">
        {{ $t("addDevice.close") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n'
import type { FormInstance, FormRules } from 'element-plus';
import { Check, View } from "@element-plus/icons-vue";

// 子组件
import DeviceFormBasic from './DeviceFormBasic.vue';
import DeviceFormConfig from './DeviceFormConfig.vue';
import DeviceFormPoints from './DeviceFormPoints.vue';

// API
import { createChannel, importPoints, getChannel, updateChannel, getSerialPorts, reloadDeviceConfig, getProtocolConfig } from '@/api/channelApi';
import { getAllDeviceGroups, type DeviceGroupInfo } from '@/api/deviceGroupApi';
import type { ChannelCreateRequest, ProtocolOption, PointImportResult } from '@/types/channel';

const props = defineProps<{
  visible: boolean;
  channelId?: number | null;
  initialGroupId?: number | null;
}>();

const { t } = useI18n()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'success', deviceName: string, isEdit?: boolean, oldName?: string): void;
  (e: 'close'): void;
}>();

// 状态
const formRef = ref<FormInstance>();
const uploadCompRef = ref();
const originalName = ref('');
const mediaType = ref<'serial' | 'network'>('network');
const selectedFile = ref<File | null>(null);
const icdFile = ref<File | null>(null);
const deviceGroupOptions = ref<DeviceGroupInfo[]>([]);
const serialPorts = ref<Array<{device: string, description: string}>>([]);
const protocols = ref<ProtocolOption[]>([]);

// GOOSE 预览状态
const previewLoading = ref(false);
const goosePreviewVisible = ref(false);
const goosePreviewData = ref<PointImportResult | null>(null);
const previewDone = ref(false);

// 操作进度
const saving = ref(false);
const progressText = ref("");
const importElapsed = ref(0);
let progressTimer: number | null = null;

const gooseControlList = computed(() => {
  return goosePreviewData.value?.goose?.summary?.gse_controls || [];
});

const isEditMode = computed(() => !!props.channelId);
const isIec61850Server = computed(() => form.protocol_type === 4 && form.conn_type === 2);
const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const form = reactive<ChannelCreateRequest>({
  code: '', name: '', protocol_type: 1, conn_type: 2,
  ip: '0.0.0.0', port: 502, com_port: '',
  baud_rate: 9600, data_bits: 8, stop_bits: 1,
  parity: 'N', rtu_addr: '1', group_id: null,
});

const rules: FormRules = {
  code: [{ required: true, message: t('addDevice.codeRequired'), trigger: 'blur' }],
  name: [{ required: true, message: t('addDevice.nameRequired'), trigger: 'blur' }],
  port: [{ required: true, message: t('addDevice.portRequired'), trigger: 'blur' }],
};

// 生命周期与监听
onMounted(async () => {
  try {
    const config = await getProtocolConfig();
    protocols.value = config.protocols;
    await loadSerialPorts();
  } catch (e) {
    console.error('加载系统配置失败', e);
  }
});

watch(() => props.visible, async (val) => {
  if (val) {
    clearPendingPointFiles();
    await loadDeviceGroups();
    if (!isEditMode.value) {
      resetForm();
      if (props.initialGroupId) form.group_id = props.initialGroupId;
    }
  }
});

watch(() => [props.visible, props.channelId], async ([v, c]) => {
  if (v && c) {
    clearPendingPointFiles();
    await loadChannelData(c as number);
  }
}, { immediate: true });

watch(
  () => [form.protocol_type, form.conn_type],
  ([protocolType, connType]) => {
    if (protocolType === 4 && connType === 2) {
      selectedFile.value = null;
    } else {
      icdFile.value = null;
    }
    uploadCompRef.value?.clearFiles();
  },
);

// 核心逻辑
const loadDeviceGroups = async () => { deviceGroupOptions.value = await getAllDeviceGroups(); };
const loadSerialPorts = async () => { serialPorts.value = await getSerialPorts(); };

const loadChannelData = async (id: number) => {
  try {
    const data = await getChannel(id);
    if (!data) return;
    Object.assign(form, data);
    originalName.value = data.name || '';
    mediaType.value = (data.conn_type === 0 || data.conn_type === 3) ? 'serial' : 'network';
  } catch (e) { console.error('加载通道失败', e); }
};

const resetForm = () => {
  Object.assign(form, {
    code: '', name: '', protocol_type: 1, conn_type: 2,
    ip: '0.0.0.0', port: 502, com_port: 'COM1',
    baud_rate: 9600, data_bits: 8, stop_bits: 1, parity: 'N', rtu_addr: '1',
    group_id: null
  });
  clearPendingPointFiles();
  goosePreviewData.value = null;
  previewDone.value = false;
};

function clearPendingPointFiles() {
  selectedFile.value = null;
  icdFile.value = null;
  uploadCompRef.value?.clearFiles();
}

const handleIcdFileChange = async (file: File | null) => {
  icdFile.value = file;
};

// MAC 地址格式化：优先用 ICD 中的，否则按 GOOSE 标准根据 APPID 自动推算
const formatMac = (row: any) => {
  if (row.mac_address) return row.mac_address;
  if (row.app_id) {
    const prefix = '01:0C:CD';
    let appId = typeof row.app_id === 'number' ? row.app_id : parseInt(row.app_id, 16) || parseInt(row.app_id, 10) || 0;
    const high = (appId >> 8) & 0xFF;
    const low = appId & 0xFF;
    return `${prefix}:${high.toString(16).padStart(2, '0').toUpperCase()}:${low.toString(16).padStart(2, '0').toUpperCase()}`;
  }
  return '-';
};

// ICD 预览：调用后端接口解析 ICD 文件中的 GOOSE 控制块信息
const handlePreviewIcd = async () => {
  if (!icdFile.value) return;
  previewLoading.value = true;
  try {
    const { previewIcd } = await import('@/api/channelApi');
    const result = await previewIcd(icdFile.value);
    goosePreviewData.value = result;
    previewDone.value = true;
    goosePreviewVisible.value = true;
  } catch (e: any) {
    console.error('预览 ICD 失败', e);
  } finally {
    previewLoading.value = false;
  }
};

// 提交保存：全程使用进度条，按钮不转圈
const handleSubmit = async () => {
  if (!formRef.value || saving.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    importElapsed.value = 0;
    progressTimer = window.setInterval(() => { importElapsed.value++; }, 1000);
    try {
      let resultId: number;

      // 1. 保存通道
      progressText.value = t('addDevice.savingChannel');
      if (isEditMode.value && props.channelId) {
        await updateChannel(props.channelId, form);
        resultId = props.channelId;
      } else {
        const createRes = await createChannel(form);
        resultId = createRes.channel_id;
      }

      // 2. 编辑模式：重载配置
      if (isEditMode.value && props.channelId) {
        progressText.value = t('addDevice.reloadingConfig');
        await reloadDeviceConfig(props.channelId);
      }

      // 3. Excel 点表导入
      if (!isIec61850Server.value && selectedFile.value) {
        progressText.value = t('addDevice.importingPoints');
        await importPoints(resultId, selectedFile.value);
      }

      // 4. ICD 文件导入
      if (isIec61850Server.value && icdFile.value) {
        progressText.value = t('addDevice.icdImporting');
        const { importIcdPoints } = await import('@/api/channelApi');
        await importIcdPoints(resultId, icdFile.value, 'eth0', 'model_only');
      }

      emit('success', form.name, isEditMode.value, originalName.value);
      dialogVisible.value = false;
      localStorage.setItem('_pendingDevice', form.name);
      window.location.reload();
    } catch (e: any) {
      console.error(e.message || '操作失败');
    } finally {
      if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
      saving.value = false;
    }
  });
};

const handleClose = () => {
  clearPendingPointFiles();
  dialogVisible.value = false;
  goosePreviewVisible.value = false;
  goosePreviewData.value = null;
  previewDone.value = false;
  emit('close');
};
</script>

<style lang="scss">
.modern-dialog {
  border-radius: 16px;
  overflow: hidden;
  .el-dialog__header {
    margin-right: 0;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--sidebar-border);
  }
  .el-dialog__body {
    padding: 24px 30px;
  }
}
.submit-btn {
  padding-left: 20px;
  padding-right: 20px;
  font-weight: 600;
}
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.icd-import-progress {
  padding: 24px 0 12px;
  text-align: center;
  :deep(.el-progress) {
    padding-right: 0;
  }
  :deep(.el-progress-bar) {
    margin-right: 0;
    width: 100%;
  }
  :deep(.el-progress__text) {
    display: none;
  }
}
.icd-import-hint {
  margin-top: 10px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}
</style>
