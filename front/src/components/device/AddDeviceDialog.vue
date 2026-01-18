<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEditMode ? '编辑设备' : '添加设备'"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <!-- 基本信息 -->
      <el-divider content-position="left">基本信息</el-divider>
      
      <el-form-item label="设备编码" prop="code">
        <el-input v-model="form.code" placeholder="请输入设备编码，如 PCS1" />
      </el-form-item>
      
      <el-form-item label="设备名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入设备名称" />
      </el-form-item>
      
      <!-- 连接配置 -->
      <el-divider content-position="left">连接配置</el-divider>
      
      <el-form-item label="介质类型" prop="media_type">
        <el-radio-group v-model="mediaType" @change="handleMediaTypeChange">
          <el-radio :value="'serial'">串口</el-radio>
          <el-radio :value="'network'">网络</el-radio>
        </el-radio-group>
      </el-form-item>
      
      <el-form-item label="连接模式" prop="conn_type">
        <el-radio-group v-if="mediaType === 'serial'" v-model="form.conn_type" @change="handleConnTypeChange">
          <el-radio :value="3">从站（被动响应）</el-radio>
          <el-radio :value="0">主站（主动采集）</el-radio>
        </el-radio-group>
        <el-radio-group v-else v-model="form.conn_type" @change="handleConnTypeChange">
          <el-radio :value="2">服务端（监听连接）</el-radio>
          <el-radio :value="1">客户端（主动连接）</el-radio>
        </el-radio-group>
      </el-form-item>
      
      <el-form-item label="协议类型" prop="protocol_type">
        <el-select v-model="form.protocol_type" placeholder="请选择协议类型">
          <el-option
            v-for="protocol in filteredProtocols"
            :key="protocol.value"
            :label="protocol.label"
            :value="protocol.value"
          />
        </el-select>
      </el-form-item>
      
      <!-- 网络配置 -->
      <template v-if="mediaType === 'network'">
        <el-divider content-position="left">网络配置</el-divider>
        
        <el-form-item label="IP地址" prop="ip">
          <el-input 
            v-model="form.ip" 
            placeholder="请输入IP地址"
            :disabled="form.conn_type === 2"
          />
          <div v-if="form.conn_type === 2" class="form-tip">服务端模式默认监听 0.0.0.0</div>
        </el-form-item>
        
        <el-form-item label="端口" prop="port">
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
      </template>
      
      <!-- 串口配置 -->
      <template v-if="mediaType === 'serial'">
        <el-divider content-position="left">串口配置</el-divider>
        
        <el-form-item label="串口号" prop="com_port">
          <el-select v-model="form.com_port" placeholder="请选择串口" :loading="comPorts.length === 0">
            <el-option 
              v-for="port in comPorts" 
              :key="port.device" 
              :label="`${port.device} - ${port.description}`" 
              :value="port.device" 
            />
          </el-select>
          <div v-if="comPorts.length === 0" class="form-tip">未检测到可用串口</div>
        </el-form-item>
        
        <el-form-item label="波特率" prop="baud_rate">
          <el-select v-model="form.baud_rate">
            <el-option v-for="rate in baudRates" :key="rate" :label="rate" :value="rate" />
          </el-select>
        </el-form-item>
        
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="数据位" prop="data_bits">
              <el-select v-model="form.data_bits">
                <el-option :label="7" :value="7" />
                <el-option :label="8" :value="8" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="停止位" prop="stop_bits">
              <el-select v-model="form.stop_bits">
                <el-option :label="1" :value="1" />
                <el-option :label="2" :value="2" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="校验位" prop="parity">
              <el-select v-model="form.parity">
                <el-option label="无" value="N" />
                <el-option label="奇校验" value="O" />
                <el-option label="偶校验" value="E" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </template>
      
      <!-- 电表地址 - 只在DLT645协议时显示 -->
      <el-form-item v-if="form.protocol_type === 3" label="电表地址" prop="rtu_addr">
        <el-input 
          v-model="form.rtu_addr" 
          placeholder="请输入12位电表地址"
          :length="12"
        />
        <div class="form-tip">请输入完整的12位电表通讯地址</div>
      </el-form-item>
      
      <!-- 点表导入 -->
      <el-divider content-position="left">点表导入</el-divider>
      
      <el-form-item label="Excel文件">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          accept=".xlsx,.xls"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
        >
          <template #trigger>
            <el-button type="primary">选择文件</el-button>
          </template>
          <template #tip>
            <div class="el-upload__tip">
              支持 .xlsx 格式，包含遥测/遥信/遥控/遥调 四个 sheet
            </div>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>
    
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          {{ isEditMode ? '保存修改' : '确认添加' }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules, UploadFile } from 'element-plus';
import { createChannel, importPoints, createAndStartDevice, getChannel, updateChannel, getSerialPorts, reloadDeviceConfig } from '@/api/channelApi';
import type { ChannelCreateRequest, ProtocolOption } from '@/types/channel';

// Props
const props = defineProps<{
  visible: boolean;
  channelId?: number | null;
}>();

// Emits
const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'success', deviceName: string, isEdit?: boolean, oldName?: string): void;
  (e: 'close'): void;
}>();

// 是否为编辑模式
const isEditMode = computed(() => !!props.channelId);

// 对话框可见性
const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
});

// 当对话框打开且为编辑模式时，加载通道数据
watch(() => [props.visible, props.channelId], async ([visible, channelId]) => {
  if (visible && channelId) {
    try {
      const channel = await getChannel(channelId as number);
      if (channel) {
        form.code = channel.code || '';
        form.name = channel.name || '';
        form.protocol_type = channel.protocol_type ?? 1;
        form.conn_type = channel.conn_type ?? 2;
        form.ip = channel.ip || '0.0.0.0';
        form.port = channel.port || 502;
        form.com_port = channel.com_port || '';
        form.baud_rate = channel.baud_rate || 9600;
        form.data_bits = channel.data_bits || 8;
        form.stop_bits = channel.stop_bits || 1;
        form.parity = channel.parity || 'N';
        form.rtu_addr = channel.rtu_addr || '1';
        originalName.value = channel.name || ''; // 保存原始名称
        
        // 根据conn_type设置mediaType
        mediaType.value = (form.conn_type === 0 || form.conn_type === 3) ? 'serial' : 'network';
        
        // 如果是串口模式，加载串口列表
        if (mediaType.value === 'serial') {
          loadSerialPorts();
        }
      }
    } catch (error) {
      console.error('加载通道数据失败:', error);
    }
  }
}, { immediate: true });

// 表单引用
const formRef = ref<FormInstance>();
const uploadRef = ref();

// 加载状态
const loading = ref(false);

// 原始设备名称（用于编辑模式下判断是否改名）
const originalName = ref<string>('');

// 介质类型：'serial' 或 'network'
const mediaType = ref<'serial' | 'network'>('network');

// 介质类型改变处理
const handleMediaTypeChange = (value: 'serial' | 'network') => {
  if (value === 'serial') {
    form.conn_type = 3; // 默认为从站（被动响应）
    loadSerialPorts();
  } else {
    form.conn_type = 2; // 默认为服务端
  }
  handleConnTypeChange();
};

// 选择的文件
const selectedFile = ref<File | null>(null);

// 协议选项
const protocols: ProtocolOption[] = [
  { value: 0, label: 'Modbus RTU', conn_types: [0, 3] },
  { value: 1, label: 'Modbus TCP', conn_types: [1, 2] },
  { value: 2, label: 'IEC 104', conn_types: [1, 2] },
  { value: 3, label: 'DL/T645-2007', conn_types: [0, 1, 2, 3] },
];

// 串口列表（动态加载）
const comPorts = ref<Array<{device: string, description: string}>>([]);

// 加载串口列表
const loadSerialPorts = async () => {
  try {
    const ports = await getSerialPorts();
    comPorts.value = ports;
    // 自动选择第一个串口
    if (ports.length > 0 && !form.com_port) {
      form.com_port = ports[0].device;
    }
  } catch (error) {
    console.error('加载串口列表失败:', error);
    comPorts.value = [];
  }
};

// 波特率列表
const baudRates = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200];

// 表单数据
const form = reactive<ChannelCreateRequest>({
  code: '',
  name: '',
  protocol_type: 1,
  conn_type: 2,
  ip: '0.0.0.0',
  port: 502,
  com_port: '',
  baud_rate: 9600,
  data_bits: 8,
  stop_bits: 1,
  parity: 'N',
  rtu_addr: '1',
});

// 表单验证规则
const rules: FormRules = {
  code: [
    { required: true, message: '请输入设备编码', trigger: 'blur' },
    { min: 1, max: 32, message: '长度在 1 到 32 个字符', trigger: 'blur' },
  ],
  name: [
    { required: true, message: '请输入设备名称', trigger: 'blur' },
    { min: 1, max: 64, message: '长度在 1 到 64 个字符', trigger: 'blur' },
  ],
  port: [
    { required: true, message: '请输入端口号', trigger: 'blur' },
  ],
};

// 根据连接类型过滤协议
const filteredProtocols = computed(() => {
  return protocols.filter(p => p.conn_types.includes(form.conn_type));
});

// 连接类型改变时，重置协议类型
const handleConnTypeChange = () => {
  const available = filteredProtocols.value;
  if (available.length > 0 && !available.find(p => p.value === form.protocol_type)) {
    form.protocol_type = available[0].value;
  }
  // 切换到串口模式时加载串口列表
  if (form.conn_type === 0) {
    loadSerialPorts();
  }
};

// 文件选择
const handleFileChange = (uploadFile: UploadFile) => {
  if (uploadFile.raw) {
    selectedFile.value = uploadFile.raw;
  }
};

// 文件移除
const handleFileRemove = () => {
  selectedFile.value = null;
};

// 关闭对话框
const handleClose = () => {
  dialogVisible.value = false;
  resetForm();
};

// 重置表单
const resetForm = () => {
  form.code = '';
  form.name = '';
  form.protocol_type = 1;
  form.conn_type = 2;
  form.ip = '0.0.0.0';
  form.port = 502;
  form.com_port = 'COM1';
  form.baud_rate = 9600;
  form.data_bits = 8;
  form.stop_bits = 1;
  form.parity = 'N';
  form.rtu_addr = '1';
  mediaType.value = 'network';
  selectedFile.value = null;
  uploadRef.value?.clearFiles();
};

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return;
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    
    loading.value = true;
    
    try {
      let channelId: number;
      
      if (isEditMode.value && props.channelId) {
        // 编辑模式：更新通道
        await updateChannel(props.channelId, form);
        channelId = props.channelId;
        ElMessage.success('通道更新成功');
      } else {
        // 新增模式：创建通道
        const createResult = await createChannel(form);
        channelId = createResult.channel_id;
        ElMessage.success('通道创建成功');
      }
      
      // 2. 如果有文件，导入点表
      if (selectedFile.value) {
        try {
          const importResult = await importPoints(channelId, selectedFile.value);
          ElMessage.success(`点表导入成功：共 ${importResult.total} 个测点`);
        } catch (error) {
          ElMessage.warning('点表导入失败，但通道已创建');
        }
      }
      
      // 3. 创建并启动设备（仅新增模式）
      if (!isEditMode.value) {
        const startResult = await createAndStartDevice(channelId);
        ElMessage.success(`设备 ${startResult.device_name} 启动成功`);
        // 刷新页面以更新UI（确保设备列表顺序与后端一致）
        window.location.reload();
      } else {
        // 编辑模式：重新加载配置（不自动启动）
        await reloadDeviceConfig(channelId);
        window.location.reload();
        ElMessage.success('设备配置已保存并重新加载，请手动启动设备');
      }
      
      // 5. 关闭对话框
      handleClose();
      
    } catch (error: any) {
      ElMessage.error(error.message || '添加设备失败');
    } finally {
      loading.value = false;
    }
  });
};
</script>

<style scoped>
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.el-divider {
  margin: 24px 0 16px 0;
}

.el-divider__text {
  font-weight: bold;
  color: #303133;
}

.el-form-item {
  margin-bottom: 18px;
}
</style>
