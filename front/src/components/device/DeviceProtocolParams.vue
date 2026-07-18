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
          <template v-if="field.unit" #suffix>
            <span class="field-unit">{{ field.unit }}</span>
          </template>
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
            <template v-if="field.unit" #suffix>
              <span class="field-unit">{{ field.unit }}</span>
            </template>
          </el-input-number>
          <div v-if="field.tip" class="field-tip">{{ field.tip }}</div>
        </el-form-item>
      </div>

      <el-collapse
        v-if="protocolSpecificFields.length"
        v-model="expandedSections"
        class="protocol-specific-settings"
      >
        <el-collapse-item title="IEC 104 专属参数" name="iec104-specific">
          <el-form-item
            v-for="field in protocolSpecificFields"
            :key="field.key"
            :label="field.label"
            label-width="180px"
          >
            <el-input-number
              v-model="modelValue.values[field.key]"
              :min="field.min"
              :max="field.max"
              :step="field.step || 1"
              style="width: 100%"
            >
              <template #suffix>
                <span class="field-unit">{{ field.unit || "" }}</span>
              </template>
            </el-input-number>
            <div v-if="field.tip" class="field-tip">{{ field.tip }}</div>
          </el-form-item>
        </el-collapse-item>
      </el-collapse>

      <div class="reset-row">
        <el-button link type="primary" @click="resetDefaults"
          >恢复默认参数</el-button
        >
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
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
  protocolSpecific?: boolean;
  tip?: string;
  default: number | boolean;
};

const props = defineProps<{
  modelValue: ProtocolParamsConfig;
  protocolType: number;
  connType: number;
}>();

const expandedSections = ref<string[]>(["iec104-specific"]);

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
    min: -1,
    max: 100,
    step: 1,
    unit: "次",
    default: -1,
    advanced: true,
    tip: "-1 表示持续重连，0 表示不自动重连",
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

const iec104LinkFields: FieldDefinition[] = [
  {
    key: "send_window_size",
    label: "发送窗口（k）",
    min: 1,
    max: 32767,
    step: 1,
    unit: "帧",
    default: 12,
    protocolSpecific: true,
  },
  {
    key: "receive_window_size",
    label: "接收窗口（w）",
    min: 1,
    max: 32767,
    step: 1,
    unit: "帧",
    default: 8,
    tip: "w 不能大于 k",
    protocolSpecific: true,
  },
  {
    key: "t0_timeout_s",
    label: "连接建立超时（t0）",
    min: 1,
    max: 3600,
    step: 1,
    unit: "s",
    default: 3,
    protocolSpecific: true,
  },
  {
    key: "t1_timeout_s",
    label: "报文确认超时（t1）",
    min: 1,
    max: 3600,
    step: 1,
    unit: "s",
    default: 3,
    protocolSpecific: true,
  },
  {
    key: "t2_timeout_s",
    label: "接收确认间隔（t2）",
    min: 1,
    max: 3600,
    step: 1,
    unit: "s",
    default: 1,
    tip: "t2 不能大于 t1",
    protocolSpecific: true,
  },
  {
    key: "t3_interval_s",
    label: "空闲链路检测间隔（t3）",
    min: 1,
    max: 86400,
    step: 1,
    unit: "s",
    default: 20,
    protocolSpecific: true,
  },
];

const iec104Client: FieldDefinition[] = [
  ...iec104LinkFields,
  {
    key: "originator_address",
    label: "源发站地址",
    min: 0,
    max: 255,
    step: 1,
    default: 0,
    protocolSpecific: true,
  },
  {
    key: "clock_sync_interval_s",
    label: "时钟同步周期",
    min: 0,
    max: 86400,
    step: 1,
    unit: "s",
    default: 0,
    protocolSpecific: true,
    tip: "0 表示不定时发送",
  },
  {
    key: "general_interrogation_interval_s",
    label: "总召唤命令间隔",
    min: 0,
    max: 86400,
    step: 1,
    unit: "s",
    default: 0,
    protocolSpecific: true,
    tip: "0 表示不定时发送；连接建立时仍自动总召唤",
  },
  {
    key: "counter_interrogation_interval_s",
    label: "累计量召唤命令间隔",
    min: 0,
    max: 86400,
    step: 1,
    unit: "s",
    default: 0,
    protocolSpecific: true,
    tip: "0 表示不定时发送",
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
    min: -1,
    max: 100,
    step: 1,
    unit: "次",
    default: -1,
    advanced: true,
    tip: "-1 表示持续重连，0 表示不自动重连",
  },
];

const iec104Server: FieldDefinition[] = [
  ...iec104LinkFields,
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
  fields.value.filter((field) => !field.advanced && !field.protocolSpecific),
);
const advancedFields = computed(() =>
  fields.value.filter((field) => field.advanced && !field.protocolSpecific),
);
const protocolSpecificFields = computed(() =>
  fields.value.filter((field) => field.protocolSpecific),
);

function resetDefaults() {
  props.modelValue.schema_version = 1;
  props.modelValue.values = Object.fromEntries(
    fields.value.map((field) => [field.key, field.default]),
  );
}

watch(
  () => [props.protocolType, props.connType],
  () => {
    expandedSections.value = ["iec104-specific"];
    resetDefaults();
  },
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
.field-unit {
  display: inline-block;
  width: 28px;
  text-align: left;
}
.protocol-params-form :deep(.el-input-number .el-input__inner) {
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.protocol-params-form :deep(.el-form-item__label) {
  white-space: nowrap;
}
.advanced-settings {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.protocol-specific-settings {
  margin-top: 18px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.protocol-specific-settings :deep(.el-collapse-item__header) {
  padding: 0 18px;
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.protocol-specific-settings :deep(.el-collapse-item__content) {
  padding: 16px 0 4px;
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
