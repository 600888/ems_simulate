<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEditMode ? '编辑设备' : '添加设备'"
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
      <DeviceFormBasic v-model:modelValue="form" :group-options="deviceGroupOptions" />
      
      <DeviceFormConfig 
        v-model:modelValue="form" 
        v-model:media-type="mediaType"
        :protocols="protocols"
        :serial-ports="serialPorts"
      />
      
      <DeviceFormPoints ref="uploadCompRef" @file-change="(f) => selectedFile = f" />
    </el-form>
    
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose" round>取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit" round class="submit-btn" :icon="Check">
          {{ isEditMode ? '保存修改' : '确认添加' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { Check } from "@element-plus/icons-vue";

// 子组件
import DeviceFormBasic from './DeviceFormBasic.vue';
import DeviceFormConfig from './DeviceFormConfig.vue';
import DeviceFormPoints from './DeviceFormPoints.vue';

// API
import { createChannel, importPoints, getChannel, updateChannel, getSerialPorts, reloadDeviceConfig, getProtocolConfig, restartDevice } from '@/api/channelApi';
import { getAllDeviceGroups, type DeviceGroupInfo } from '@/api/deviceGroupApi';
import type { ChannelCreateRequest, ProtocolOption } from '@/types/channel';

const props = defineProps<{
  visible: boolean;
  channelId?: number | null;
  initialGroupId?: number | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'success', deviceName: string, isEdit?: boolean, oldName?: string): void;
  (e: 'close'): void;
}>();

// 状态
const formRef = ref<FormInstance>();
const uploadCompRef = ref();
const loading = ref(false);
const originalName = ref('');
const mediaType = ref<'serial' | 'network'>('network');
const selectedFile = ref<File | null>(null);
const deviceGroupOptions = ref<DeviceGroupInfo[]>([]);
const serialPorts = ref<Array<{device: string, description: string}>>([]);
const protocols = ref<ProtocolOption[]>([]);

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
  code: [{ required: true, message: '请输入编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  port: [{ required: true, message: '请输入端口', trigger: 'blur' }],
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
  uploadCompRef.value?.clearFiles();
};

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
        // 更新后重新加载配置（不自动启动设备）
        await reloadDeviceConfig(props.channelId);
        ElMessage.success('更新成功，配置已重新加载');
      } else {
        const createRes = await createChannel(form);
        resultId = createRes.channel_id;
        ElMessage.success('创建成功');
      }
      
      if (selectedFile.value) await importPoints(resultId, selectedFile.value);
      
      emit('success', form.name, isEditMode.value, originalName.value);
      dialogVisible.value = false;
    } catch (e: any) {
      ElMessage.error(e.message || '操作失败');
    } finally { loading.value = false; }
  });
};

const handleClose = () => { emit('close'); };
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
