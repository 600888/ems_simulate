<template>
  <div class="device-form-config">
    <el-divider content-position="left">通迅配置</el-divider>
    
    <el-form-item label="通讯介质">
      <el-radio-group v-model="localMediaType" @change="onMediaTypeChange">
        <el-radio value="serial">串口</el-radio>
        <el-radio value="network">网络</el-radio>
      </el-radio-group>
    </el-form-item>
    
    <el-form-item label="连接模式" prop="conn_type">
      <el-radio-group v-if="localMediaType === 'serial'" v-model="modelValue.conn_type">
        <el-radio :value="0">主站（主动轮询）</el-radio>
        <el-radio :value="3">从站（被动响应）</el-radio>
      </el-radio-group>
      <el-radio-group v-else v-model="modelValue.conn_type">
        <el-radio :value="1">TCP客户端</el-radio>
        <el-radio :value="2">TCP服务端</el-radio>
      </el-radio-group>
    </el-form-item>
    
    <el-form-item label="通讯协议" prop="protocol_type">
      <el-select v-model="modelValue.protocol_type" style="width: 100%">
        <el-option
          v-for="protocol in filteredProtocols"
          :key="protocol.value"
          :label="protocol.label"
          :value="protocol.value"
        />
      </el-select>
    </el-form-item>
    
    <!-- 网络专有配置 -->
    <template v-if="localMediaType === 'network'">
      <el-form-item label="IP地址" prop="ip">
        <el-input v-model="modelValue.ip" placeholder="0.0.0.0 (服务端监听所有IP)" />
      </el-form-item>
      <el-form-item label="端口" prop="port">
        <el-input-number v-model="modelValue.port" :min="1" :max="65535" style="width: 100%" />
      </el-form-item>
    </template>
    
    <!-- 串口专有配置 -->
    <template v-if="localMediaType === 'serial'">
      <el-form-item label="串口号" prop="com_port">
        <el-select v-model="modelValue.com_port" filterable allow-create placeholder="选择或输入串口" style="width: 100%">
          <el-option v-for="p in serialPorts" :key="p.device" :label="`${p.device} (${p.description})`" :value="p.device" />
        </el-select>
      </el-form-item>
      <el-form-item label="波特率" prop="baud_rate">
        <el-select v-model="modelValue.baud_rate" style="width: 100%">
          <el-option v-for="rate in baudRates" :key="rate" :label="rate" :value="rate" />
        </el-select>
      </el-form-item>
      <el-row :gutter="20">
        <el-col :span="8">
          <el-form-item label="数据位" prop="data_bits">
            <el-select v-model="modelValue.data_bits">
              <el-option :label="7" :value="7" /><el-option :label="8" :value="8" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="停止位" prop="stop_bits">
            <el-select v-model="modelValue.stop_bits">
              <el-option :label="1" :value="1" /><el-option :label="2" :value="2" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="校验" prop="parity">
            <el-select v-model="modelValue.parity">
              <el-option label="无" value="N" /><el-option label="奇" value="O" /><el-option label="偶" value="E" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
    </template>
    
    <el-form-item v-if="modelValue.protocol_type === 3" label="电表地址" prop="rtu_addr">
      <el-input v-model="modelValue.rtu_addr" placeholder="DLT645 电表 12 位地址" />
    </el-form-item>
    <el-form-item v-else label="从机地址" prop="rtu_addr">
      <el-input v-model="modelValue.rtu_addr" placeholder="Modbus 从机地址 (通常为 1)" />
    </el-form-item>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, watch } from 'vue';
import type { ChannelCreateRequest, ProtocolOption } from '@/types/channel';

const props = defineProps<{
  modelValue: ChannelCreateRequest;
  mediaType: 'serial' | 'network';
  protocols: ProtocolOption[];
  serialPorts: Array<{device: string, description: string}>;
}>();

const emit = defineEmits<{
  (e: 'update:mediaType', value: 'serial' | 'network'): void;
}>();

const localMediaType = ref(props.mediaType);
watch(() => props.mediaType, (val) => localMediaType.value = val);

const filteredProtocols = computed(() => {
  return props.protocols.filter(p => p.conn_types.includes(props.modelValue.conn_type));
});

const baudRates = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200];

const onMediaTypeChange = (val: any) => {
  emit('update:mediaType', val);
  // 切换介质时自动调整 conn_type
  if (val === 'serial') {
    props.modelValue.conn_type = 3;
  } else {
    props.modelValue.conn_type = 2;
  }
};
</script>
