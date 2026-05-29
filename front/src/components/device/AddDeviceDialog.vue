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
        @file-change="(f) => selectedFile = f" 
        @icd-file-change="(f) => selectedIcdFile = f" 
      />
    </el-form>
    
    <template #footer>
      <div class="dialog-footer">
        <el-button v-if="showPreviewBtn" type="warning" :icon="View" :loading="previewLoading" @click="handlePreview">
          {{ $t('addDevice.previewIcd') }}
        </el-button>
        <el-button @click="handleClose" round>{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit" round class="submit-btn" :icon="Check">
          {{ isEditMode ? $t('addDevice.saveChanges') : $t('addDevice.confirmAdd') }}
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
      :title="$t('addDevice.mmsPoints', { total: goosePreviewData?.total || 0, yc: goosePreviewData?.yc_count || 0, yx: goosePreviewData?.yx_count || 0, yk: goosePreviewData?.yk_count || 0, yt: goosePreviewData?.yt_count || 0 })"
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
        <el-table-column prop="go_cb_ref" label="GoCBRef" min-width="240" show-overflow-tooltip />
        <el-table-column prop="go_id" label="GoID" width="100" />
        <el-table-column prop="app_id" label="APPID" width="70" />
        <el-table-column prop="dat_set" label="DataSet" width="120" show-overflow-tooltip />
        <el-table-column prop="conf_rev" label="ConfRev" width="70" />
        <el-table-column :label="$t('addDevice.macAddress')" width="140">
          <template #default="{ row }">{{ formatMac(row) }}</template>
        </el-table-column>
        <el-table-column :label="$t('addDevice.datasetMembers')" width="90" align="center">
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
        {{ $t('addDevice.close') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { Check, View } from "@element-plus/icons-vue";

// 子组件
import DeviceFormBasic from './DeviceFormBasic.vue';
import DeviceFormConfig from './DeviceFormConfig.vue';
import DeviceFormPoints from './DeviceFormPoints.vue';

// API
import { createChannel, importPoints, importIcdPoints, previewIcd, getChannel, updateChannel, getSerialPorts, reloadDeviceConfig, getProtocolConfig } from '@/api/channelApi';
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
const loading = ref(false);
const previewLoading = ref(false);
const originalName = ref('');
const mediaType = ref<'serial' | 'network'>('network');
const selectedFile = ref<File | null>(null);
const selectedIcdFile = ref<File | null>(null);
const deviceGroupOptions = ref<DeviceGroupInfo[]>([]);
const serialPorts = ref<Array<{device: string, description: string}>>([]);
const protocols = ref<ProtocolOption[]>([]);

// GOOSE 预览状态
const goosePreviewVisible = ref(false);
const goosePreviewData = ref<PointImportResult | null>(null);
const previewDone = ref(false);

const showPreviewBtn = computed(() => !!selectedIcdFile.value);

const gooseControlList = computed(() => {
  return goosePreviewData.value?.goose?.summary?.gse_controls || [];
});

const isEditMode = computed(() => !!props.channelId);
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
    await loadDeviceGroups();
    if (!isEditMode.value) {
      resetForm();
      if (props.initialGroupId) form.group_id = props.initialGroupId;
    }
  }
});

watch(() => [props.visible, props.channelId], async ([v, c]) => {
  if (v && c) await loadChannelData(c as number);
}, { immediate: true });

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
  selectedFile.value = null;
  selectedIcdFile.value = null;
  goosePreviewData.value = null;
  previewDone.value = false;
  uploadCompRef.value?.clearFiles();
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

// ICD 预览
const handlePreview = async () => {
  if (!selectedIcdFile.value) return;
  previewLoading.value = true;
  try {
    const result = await previewIcd(selectedIcdFile.value);
    goosePreviewData.value = result;
    previewDone.value = true;
    goosePreviewVisible.value = true;
  } catch (e: any) {
    console.error('预览 ICD 失败', e);
    // error handled by global interceptor
  } finally {
    previewLoading.value = false;
  }
};

// 提交保存
const handleSubmit = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      let resultId: number;
      if (isEditMode.value && props.channelId) {
        await updateChannel(props.channelId, form);
        resultId = props.channelId;
        await reloadDeviceConfig(props.channelId);
        ElMessage.success(t('addDevice.updateSuccess'));
      } else {
        const createRes = await createChannel(form);
        resultId = createRes.channel_id;
        ElMessage.success(t('addDevice.createSuccess'));
      }
      
      if (selectedIcdFile.value) {
        const importResult = await importIcdPoints(resultId, selectedIcdFile.value, 'eth0', true);
        ElMessage.success(t('addDevice.icdImportSuccess', { total: importResult?.total || 0, goose: importResult?.goose?.created_count || 0 }));
      } else if (selectedFile.value) {
        await importPoints(resultId, selectedFile.value);
      }
      
      emit('success', form.name, isEditMode.value, originalName.value);
      dialogVisible.value = false;
      window.location.reload();
    } catch (e: any) {
      console.error(e.message || '操作失败');
      // error message is handled by global interceptor
    } finally { loading.value = false; }
  });
};

const handleClose = () => {
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
</style>
