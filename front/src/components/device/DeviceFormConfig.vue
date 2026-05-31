<template>
  <div class="device-form-config">
    <el-divider content-position="left">{{ $t('device.commConfig') }}</el-divider>
    
    <el-form-item :label="$t('device.media')">
      <el-radio-group v-model="localMediaType" @change="onMediaTypeChange">
        <el-radio value="serial">{{ $t('device.serial') }}</el-radio>
        <el-radio value="network">{{ $t('device.network') }}</el-radio>
      </el-radio-group>
    </el-form-item>
    
    <el-form-item :label="$t('device.connMode')" prop="conn_type">
      <el-radio-group v-if="localMediaType === 'serial'" v-model="modelValue.conn_type">
        <el-radio :value="0">{{ $t('device.master') }}</el-radio>
        <el-radio :value="3">{{ $t('device.slaveMode') }}</el-radio>
      </el-radio-group>
      <el-radio-group v-else v-model="modelValue.conn_type">
        <el-radio :value="1">{{ $t('device.tcpClient') }}</el-radio>
        <el-radio :value="2">{{ $t('device.tcpServer') }}</el-radio>
      </el-radio-group>
    </el-form-item>
    
    <el-form-item :label="$t('device.protocol')" prop="protocol_type">
      <el-select v-model="modelValue.protocol_type" style="width: 100%">
        <el-option
          v-for="protocol in filteredProtocols"
          :key="protocol.value"
          :label="protocol.label"
          :value="protocol.value"
        />
      </el-select>
    </el-form-item>
    
    <template v-if="localMediaType === 'network'">
      <el-form-item :label="$t('device.ip')" prop="ip">
        <el-input v-model="modelValue.ip" :placeholder="$t('device.ipPlaceholder')" />
      </el-form-item>
      <el-form-item :label="$t('device.port')" prop="port">
        <el-input-number v-model="modelValue.port" :min="1" :max="65535" style="width: 100%" />
      </el-form-item>
    </template>
    
    <template v-if="localMediaType === 'serial'">
      <el-form-item :label="$t('device.comPort')" prop="com_port">
        <el-select v-model="modelValue.com_port" filterable allow-create :placeholder="$t('device.comPortPlaceholder')" style="width: 100%">
          <el-option v-for="p in serialPorts" :key="p.device" :label="`${p.device} (${p.description})`" :value="p.device" />
        </el-select>
      </el-form-item>
      <el-form-item :label="$t('device.baudRate')" prop="baud_rate">
        <el-select v-model="modelValue.baud_rate" style="width: 100%">
          <el-option v-for="rate in baudRates" :key="rate" :label="rate" :value="rate" />
        </el-select>
      </el-form-item>
      <el-row :gutter="20">
        <el-col :span="8">
          <el-form-item :label="$t('device.dataBits')" prop="data_bits">
            <el-select v-model="modelValue.data_bits">
              <el-option :label="7" :value="7" /><el-option :label="8" :value="8" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="$t('device.stopBits')" prop="stop_bits">
            <el-select v-model="modelValue.stop_bits">
              <el-option :label="1" :value="1" /><el-option :label="2" :value="2" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="$t('device.parity')" prop="parity">
            <el-select v-model="modelValue.parity">
              <el-option :label="$t('device.none')" value="N" /><el-option :label="$t('device.odd')" value="O" /><el-option :label="$t('device.even')" value="E" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
    </template>
    
    <el-form-item v-if="modelValue.protocol_type === 3" :label="$t('device.meterAddress')" prop="rtu_addr">
      <el-input v-model="modelValue.rtu_addr" :placeholder="$t('device.meterAddressPlaceholder')" />
    </el-form-item>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';

useI18n();
import type { ChannelCreateRequest, ProtocolOption } from '@/types/channel';
import { BAUD_RATES, PROTOCOL_DEFAULT_PORTS, PROTOCOL_DEFAULT_CLIENT_IP } from '@/constants/protocol';

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

const baudRates = BAUD_RATES;

// 协议默认端口映射已提取到 @/constants/protocol

// 监听协议切换，自动更新默认端口和客户端默认IP
watch(() => props.modelValue.protocol_type, (newType) => {
  const defaultPort = PROTOCOL_DEFAULT_PORTS[newType];
  if (defaultPort !== undefined) {
    props.modelValue.port = defaultPort;
  }
  // 协议有默认客户端 IP 时，自动设为 TCP 客户端模式
  const defaultIp = PROTOCOL_DEFAULT_CLIENT_IP[newType];
  if (defaultIp !== undefined) {
    props.modelValue.conn_type = 1;
    props.modelValue.ip = defaultIp;
  } else if (props.modelValue.conn_type === 1) {
    // 无默认客户端 IP 的协议，且当前为客户端模式时清空 IP
    props.modelValue.ip = '0.0.0.0';
  }
});

// 监听连接模式切换，自动更新客户端默认IP
watch(() => props.modelValue.conn_type, (newConnType) => {
  if (newConnType === 1) {
    // 切换为 TCP 客户端时，设置协议默认 IP
    const defaultIp = PROTOCOL_DEFAULT_CLIENT_IP[props.modelValue.protocol_type];
    props.modelValue.ip = defaultIp !== undefined ? defaultIp : '127.0.0.1';
  } else if (newConnType === 2) {
    // 切换为 TCP 服务端时，恢复监听所有 IP
    props.modelValue.ip = '0.0.0.0';
  }
});

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
