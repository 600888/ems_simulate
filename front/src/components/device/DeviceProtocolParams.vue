<template>
  <div class="protocol-params-form">
    <el-alert
      title="这里仅配置协议运行参数，IP、端口、串口和点表等原有配置仍在“基本信息”中。"
      type="info"
      :closable="false"
      show-icon
      class="params-hint"
    />

    <el-empty
      v-if="fields.length === 0"
      description="当前协议及连接模式暂无额外运行参数"
      :image-size="72"
    />

    <template v-else>
      <el-form-item
        v-for="field in commonFields"
        :key="field.key"
        :label="field.label"
        label-width="180px"
      >
        <el-switch
          v-if="field.kind === 'boolean'"
          v-model="modelValue.values[field.key]"
        />
        <el-input-number
          v-else
          v-model="modelValue.values[field.key]"
          :min="field.min"
          :max="field.max"
          :step="field.step || 100"
          style="width: 100%"
        >
          <template #suffix>{{ field.unit }}</template>
        </el-input-number>
        <div v-if="field.tip" class="field-tip">{{ field.tip }}</div>
      </el-form-item>

      <div v-if="advancedFields.length" class="advanced-settings">
        <div class="section-title">高级设置</div>
        <el-form-item
          v-for="field in advancedFields"
          :key="field.key"
          :label="field.label"
          label-width="180px"
        >
          <el-switch
            v-if="field.kind === 'boolean'"
            v-model="modelValue.values[field.key]"
          />
          <el-input-number
            v-else
            v-model="modelValue.values[field.key]"
            :min="field.min"
            :max="field.max"
            :step="field.step || 100"
            style="width: 100%"
          >
            <template #suffix>{{ field.unit }}</template>
          </el-input-number>
          <div v-if="field.tip" class="field-tip">{{ field.tip }}</div>
        </el-form-item>
      </div>

      <div class="reset-row">
        <el-button link type="primary" @click="resetDefaults"
          >恢复默认参数</el-button
        >
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from "vue";
import type { ProtocolParamsConfig } from "@/types/channel";

type FieldDefinition = {
  key: string;
  label: string;
  kind?: "number" | "boolean";
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  advanced?: boolean;
  tip?: string;
  default: number | boolean;
};

const props = defineProps<{
  modelValue: ProtocolParamsConfig;
  protocolType: number;
  connType: number;
}>();

const modbusClient: FieldDefinition[] = [
  {
    key: "connect_timeout_ms",
    label: "连接超时",
    min: 100,
    max: 60000,
    unit: "ms",
    default: 3000,
  },
  {
    key: "command_timeout_ms",
    label: "单条命令超时",
    min: 100,
    max: 60000,
    unit: "ms",
    default: 2000,
  },
  {
    key: "command_retry_count",
    label: "命令重试次数",
    min: 0,
    max: 10,
    step: 1,
    unit: "次",
    default: 1,
  },
  {
    key: "reconnect_initial_interval_ms",
    label: "重连初始间隔",
    min: 100,
    max: 60000,
    unit: "ms",
    default: 2000,
    advanced: true,
  },
  {
    key: "reconnect_max_interval_ms",
    label: "重连最大间隔",
    min: 1000,
    max: 300000,
    unit: "ms",
    default: 30000,
    advanced: true,
  },
  {
    key: "reconnect_max_attempts",
    label: "最大重连次数",
    min: 0,
    max: 100,
    step: 1,
    unit: "次",
    default: 0,
    advanced: true,
    tip: "0 表示持续重连",
  },
];

const modbusServer: FieldDefinition[] = [
  {
    key: "client_idle_timeout_ms",
    label: "客户端空闲超时",
    min: 0,
    max: 86400000,
    step: 1000,
    unit: "ms",
    default: 0,
    tip: "超过该时间未收到报文则主动断开；0 表示不限制",
  },
  {
    key: "max_connections",
    label: "最大客户端连接数",
    min: 0,
    max: 1000,
    step: 1,
    unit: "个",
    default: 0,
    tip: "达到上限后拒绝新的客户端连接；0 表示不限制",
  },
];

const iec104Client: FieldDefinition[] = [
  {
    key: "connect_timeout_ms",
    label: "连接超时",
    min: 100,
    max: 60000,
    unit: "ms",
    default: 3000,
  },
];

const iec104Server: FieldDefinition[] = [
  {
    key: "connection_timeout_ms",
    label: "连接建立超时",
    min: 1000,
    max: 300000,
    step: 1000,
    unit: "ms",
    default: 10000,
  },
  {
    key: "message_timeout_ms",
    label: "报文确认超时",
    min: 1000,
    max: 300000,
    step: 1000,
    unit: "ms",
    default: 15000,
    tip: "发送报文后超过该时间未收到确认，协议栈将关闭异常连接",
  },
  {
    key: "keep_alive_interval_ms",
    label: "空闲链路检测间隔",
    min: 1000,
    max: 3600000,
    step: 1000,
    unit: "ms",
    default: 20000,
    tip: "链路持续无通信时发送 TESTFR 检测客户端是否存活",
  },
  {
    key: "max_connections",
    label: "最大客户端连接数",
    min: 0,
    max: 1000,
    step: 1,
    unit: "个",
    default: 0,
    advanced: true,
    tip: "0 表示不限制",
  },
];

const dlt645Client: FieldDefinition[] = [
  {
    key: "command_timeout_ms",
    label: "单条命令超时",
    min: 100,
    max: 60000,
    unit: "ms",
    default: 3000,
  },
];

const iec61850Client: FieldDefinition[] = [
  {
    key: "connect_timeout_ms",
    label: "连接超时",
    min: 100,
    max: 60000,
    unit: "ms",
    default: 3000,
  },
  {
    key: "command_timeout_ms",
    label: "单条命令超时",
    min: 100,
    max: 120000,
    unit: "ms",
    default: 3000,
  },
  {
    key: "model_discovery_timeout_ms",
    label: "模型发现总超时",
    min: 10000,
    max: 3600000,
    step: 1000,
    unit: "ms",
    default: 600000,
    advanced: true,
  },
];

const iec61850Server: FieldDefinition[] = [
  {
    key: "max_connections",
    label: "最大 MMS 连接数",
    min: 1,
    max: 1000,
    step: 1,
    unit: "个",
    default: 5,
  },
];

const fields = computed<FieldDefinition[]>(() => {
  const key = `${props.protocolType}:${props.connType}`;
  if (key === "0:0" || key === "1:1") return modbusClient;
  if (key === "1:2") return modbusServer;
  if (key === "2:1") return iec104Client;
  if (key === "2:2") return iec104Server;
  if (key === "3:0" || key === "3:1") return dlt645Client;
  if (key === "3:2" || key === "3:3") {
    return [
      {
        key: "session_idle_timeout_ms",
        label: "会话空闲超时",
        min: 1000,
        max: 600000,
        unit: "ms",
        default: 30000,
      },
    ];
  }
  if (key === "4:1") return iec61850Client;
  if (key === "4:2") return iec61850Server;
  return [];
});

const commonFields = computed(() =>
  fields.value.filter((field) => !field.advanced),
);
const advancedFields = computed(() =>
  fields.value.filter((field) => field.advanced),
);

function resetDefaults() {
  props.modelValue.schema_version = 1;
  props.modelValue.values = Object.fromEntries(
    fields.value.map((field) => [field.key, field.default]),
  );
}

watch(
  () => [props.protocolType, props.connType],
  () => resetDefaults(),
  { flush: "sync" },
);

watch(
  fields,
  (definitions) => {
    const expectedKeys = definitions.map((field) => field.key);
    const currentKeys = Object.keys(props.modelValue.values || {});
    if (
      expectedKeys.length !== currentKeys.length ||
      expectedKeys.some((key) => !currentKeys.includes(key))
    ) {
      resetDefaults();
    }
  },
  { immediate: true },
);
</script>

<style scoped lang="scss">
.params-hint {
  margin-bottom: 20px;
}
.field-tip {
  width: 100%;
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.protocol-params-form :deep(.el-form-item__label) {
  white-space: nowrap;
}
.advanced-settings {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.section-title {
  margin: 0 0 16px 18px;
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.reset-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
