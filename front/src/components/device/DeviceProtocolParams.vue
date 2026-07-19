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
        <el-input
          v-if="field.kind === 'directory'"
          v-model="modelValue.values[field.key]"
          class="directory-path-input"
          :placeholder="field.placeholder"
        >
          <template #append>
            <el-button-group class="directory-path-actions">
              <el-button
                class="directory-path-button"
                :icon="EditPen"
                @click="chooseDirectory(field.key)"
              >
                选择目录
              </el-button>
            </el-button-group>
          </template>
        </el-input>
        <el-checkbox
          v-else-if="field.kind === 'checkbox'"
          v-model="modelValue.values[field.key]"
        />
        <el-switch
          v-else-if="field.kind === 'boolean'"
          v-model="modelValue.values[field.key]"
        />
        <el-input
          v-else-if="field.kind === 'text' || field.kind === 'password'"
          v-model="modelValue.values[field.key]"
          :type="field.kind === 'password' ? 'password' : 'text'"
          :show-password="field.kind === 'password'"
          :placeholder="field.placeholder"
          autocomplete="new-password"
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
        <div
          v-if="
            field.kind === 'directory' && hasNonAsciiDirectoryPath(field.key)
          "
          class="field-error"
        >
          文件服务目录路径必须使用英文、数字和英文符号，不能包含中文字符。
        </div>
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
          <el-input
            v-if="field.kind === 'directory'"
            v-model="modelValue.values[field.key]"
            class="directory-path-input"
            :placeholder="field.placeholder"
          >
            <template #append>
              <el-button-group class="directory-path-actions">
                <el-button
                  class="directory-path-button"
                  :icon="EditPen"
                  @click="chooseDirectory(field.key)"
                >
                  选择目录
                </el-button>
              </el-button-group>
            </template>
          </el-input>
          <el-checkbox
            v-else-if="field.kind === 'checkbox'"
            v-model="modelValue.values[field.key]"
          />
          <el-switch
            v-else-if="field.kind === 'boolean'"
            v-model="modelValue.values[field.key]"
          />
          <el-input
            v-else-if="field.kind === 'text' || field.kind === 'password'"
            v-model="modelValue.values[field.key]"
            :type="field.kind === 'password' ? 'password' : 'text'"
            :show-password="field.kind === 'password'"
            :placeholder="field.placeholder"
            autocomplete="new-password"
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
          <div
            v-if="
              field.kind === 'directory' && hasNonAsciiDirectoryPath(field.key)
            "
            class="field-error"
          >
            文件服务目录路径必须使用英文、数字和英文符号，不能包含中文字符。
          </div>
          <div v-if="field.tip" class="field-tip">{{ field.tip }}</div>
        </el-form-item>
      </div>

      <el-collapse
        v-if="protocolSpecificFields.length"
        v-model="expandedSections"
        class="protocol-specific-settings"
      >
        <el-collapse-item title="IEC 104 专属参数" name="iec104-specific">
          <div
            v-if="protocolSpecificOptionFields.length"
            class="iec104-connect-options"
          >
            <label
              v-for="field in protocolSpecificOptionFields"
              :key="field.key"
              class="iec104-connect-option"
            >
              <input
                v-model="modelValue.values[field.key]"
                class="iec104-connect-option__input"
                type="checkbox"
              />
              <span class="iec104-connect-option__box" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M4.5 12.5 9.3 17.2 19.5 6.8" />
                </svg>
              </span>
              <span class="iec104-connect-option__label">
                {{ field.label }}
              </span>
            </label>
          </div>
          <el-form-item
            v-for="field in protocolSpecificValueFields"
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
import { ElMessage } from "element-plus";
import { EditPen } from "@element-plus/icons-vue";
import type { ProtocolParamsConfig } from "@/types/channel";
import { isTauri } from "@/utils/tauri";

type FieldDefinition = {
  key: string;
  label: string;
  kind?: "number" | "boolean" | "checkbox" | "text" | "password" | "directory";
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  advanced?: boolean;
  protocolSpecific?: boolean;
  visibleWhen?: { key: string; value: number | boolean | string };
  placeholder?: string;
  tip?: string;
  default: number | boolean | string;
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
    default: 0,
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
    default: 10,
    protocolSpecific: true,
  },
  {
    key: "t1_timeout_s",
    label: "报文确认超时（t1）",
    min: 1,
    max: 3600,
    step: 1,
    unit: "s",
    default: 15,
    protocolSpecific: true,
  },
  {
    key: "t2_timeout_s",
    label: "接收确认间隔（t2）",
    min: 1,
    max: 3600,
    step: 1,
    unit: "s",
    default: 10,
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
  {
    key: "general_interrogation_on_connect",
    label: "连接后立即执行总召唤",
    kind: "checkbox",
    default: true,
    protocolSpecific: true,
  },
  {
    key: "counter_interrogation_on_connect",
    label: "连接后立即执行计数量召唤",
    kind: "checkbox",
    default: false,
    protocolSpecific: true,
  },
  ...iec104LinkFields.map((field) => {
    const clientDefaults: Record<string, number> = {
      t0_timeout_s: 10,
      t1_timeout_s: 15,
      t2_timeout_s: 10,
    };
    return field.key in clientDefaults
      ? { ...field, default: clientDefaults[field.key] }
      : field;
  }),
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
    tip: "0 表示不定时发送；是否在连接建立时发送由上方开关控制",
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
    default: 0,
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
    key: "mms_capture_enabled",
    label: "MMS 报文抓包",
    kind: "boolean",
    default: false,
    tip: "开启后使用 Npcap/libpcap 捕获 MMS 报文，关闭可减少系统资源占用。",
  },
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
    key: "model_discovery_timeout_s",
    label: "模型发现总超时",
    min: 10,
    max: 3600,
    step: 1,
    unit: "s",
    default: 60,
    advanced: true,
  },
  {
    key: "authentication_enabled",
    label: "用户认证",
    kind: "boolean",
    default: false,
    advanced: true,
    tip: "启用 IEC 61850 ACSE 密码认证。",
  },
  {
    key: "authentication_password",
    label: "认证密码",
    kind: "password",
    default: "",
    advanced: true,
    visibleWhen: { key: "authentication_enabled", value: true },
    placeholder: "请输入 ACSE 认证密码",
  },
  {
    key: "remote_ap_title",
    label: "Remote AP Title",
    kind: "text",
    default: "1,1,1,999,1",
    advanced: true,
  },
  {
    key: "remote_ae_qualifier",
    label: "Remote AE Qualifier",
    min: 0,
    max: 2147483647,
    step: 1,
    default: 12,
    advanced: true,
  },
  {
    key: "remote_p_selector",
    label: "Remote P Selector",
    kind: "text",
    default: "00 00 00 01",
    advanced: true,
  },
  {
    key: "remote_s_selector",
    label: "Remote S Selector",
    kind: "text",
    default: "00 01",
    advanced: true,
  },
  {
    key: "remote_t_selector",
    label: "Remote T Selector",
    kind: "text",
    default: "00 01",
    advanced: true,
  },
  {
    key: "local_ap_title",
    label: "Local AP Title",
    kind: "text",
    default: "1,1,1,999,1",
    advanced: true,
  },
  {
    key: "local_ae_qualifier",
    label: "Local AE Qualifier",
    min: 0,
    max: 2147483647,
    step: 1,
    default: 12,
    advanced: true,
  },
  {
    key: "local_p_selector",
    label: "Local P Selector",
    kind: "text",
    default: "00 00 00 01",
    advanced: true,
  },
  {
    key: "local_s_selector",
    label: "Local S Selector",
    kind: "text",
    default: "00 01",
    advanced: true,
  },
  {
    key: "local_t_selector",
    label: "Local T Selector",
    kind: "text",
    default: "00 01",
    advanced: true,
  },
];

const iec61850Server: FieldDefinition[] = [
  {
    key: "file_service_directory",
    label: "文件服务目录",
    kind: "directory",
    default: "",
    placeholder: "请选择向 MMS 客户端公开的文件目录",
    tip: "该目录仅对当前设备生效；留空时不开启文件服务。Windows 下目录路径及目录内文件名请使用英文。",
  },
  {
    key: "mms_capture_enabled",
    label: "MMS 报文抓包",
    kind: "boolean",
    default: false,
    tip: "开启后使用 Npcap/libpcap 捕获 MMS 报文，关闭可减少系统资源占用。",
  },
  {
    key: "max_connections",
    label: "最大 MMS 连接数",
    min: 1,
    max: 1000,
    step: 1,
    unit: "个",
    default: 5,
  },
  {
    key: "authentication_enabled",
    label: "用户认证",
    kind: "boolean",
    default: false,
    advanced: true,
    tip: "启用后仅接受密码正确的 IEC 61850 ACSE 客户端连接。",
  },
  {
    key: "authentication_password",
    label: "服务端认证密码",
    kind: "password",
    default: "",
    advanced: true,
    visibleWhen: { key: "authentication_enabled", value: true },
    placeholder: "请输入服务端 ACSE 认证密码",
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
  fields.value.filter(
    (field) =>
      !field.advanced && !field.protocolSpecific && isFieldVisible(field),
  ),
);
const advancedFields = computed(() =>
  fields.value.filter(
    (field) =>
      field.advanced && !field.protocolSpecific && isFieldVisible(field),
  ),
);
const protocolSpecificFields = computed(() =>
  fields.value.filter((field) => field.protocolSpecific),
);
const protocolSpecificOptionFields = computed(() =>
  protocolSpecificFields.value.filter((field) => field.kind === "checkbox"),
);
const protocolSpecificValueFields = computed(() =>
  protocolSpecificFields.value.filter((field) => field.kind !== "checkbox"),
);

function isFieldVisible(field: FieldDefinition) {
  if (!field.visibleWhen) return true;
  return modelValueEquals(field.visibleWhen.key, field.visibleWhen.value);
}

function modelValueEquals(key: string, value: number | boolean | string) {
  return props.modelValue.values[key] === value;
}

function hasNonAsciiDirectoryPath(key: string): boolean {
  const value = props.modelValue.values[key];
  if (typeof value !== "string" || !value.trim()) return false;
  return !/^[\x20-\x7E]+$/.test(value.trim());
}

function validate(): boolean {
  if (props.protocolType !== 4 || props.connType !== 2) return true;
  if (!hasNonAsciiDirectoryPath("file_service_directory")) return true;
  ElMessage.error(
    "文件服务目录路径必须使用英文、数字和英文符号，不能包含中文字符",
  );
  return false;
}

async function chooseDirectory(key: string) {
  if (!isTauri()) {
    ElMessage.info("浏览器模式不支持目录选择，请直接输入完整路径");
    return;
  }
  try {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const currentValue = props.modelValue.values[key];
    const selected = await open({
      directory: true,
      multiple: false,
      defaultPath:
        typeof currentValue === "string" && currentValue.trim()
          ? currentValue
          : undefined,
    });
    if (typeof selected === "string") {
      if (!/^[\x20-\x7E]+$/.test(selected.trim())) {
        ElMessage.error(
          "文件服务目录路径必须使用英文、数字和英文符号，不能包含中文字符",
        );
        return;
      }
      props.modelValue.values[key] = selected;
    }
  } catch (error) {
    console.error("选择 IEC61850 文件服务目录失败", error);
    ElMessage.error("选择目录失败");
  }
}

function resetDefaults() {
  props.modelValue.schema_version = 1;
  props.modelValue.values = Object.fromEntries(
    fields.value.map((field) => [field.key, field.default]),
  );
}

function fillMissingDefaults() {
  const currentValues = props.modelValue.values || {};
  const normalizedValues = Object.fromEntries(
    fields.value.map((field) => [
      field.key,
      Object.prototype.hasOwnProperty.call(currentValues, field.key)
        ? currentValues[field.key]
        : field.default,
    ]),
  );
  props.modelValue.schema_version = 1;
  props.modelValue.values = normalizedValues;
}

watch(
  () => [props.protocolType, props.connType],
  () => {
    expandedSections.value = ["iec104-specific"];
  },
  { flush: "sync" },
);

watch(
  [
    fields,
    () =>
      Object.keys(props.modelValue.values || {})
        .sort()
        .join("|"),
  ],
  ([definitions]) => {
    const expectedKeys = definitions.map((field) => field.key);
    const currentKeys = Object.keys(props.modelValue.values || {});
    if (
      expectedKeys.length !== currentKeys.length ||
      expectedKeys.some((key) => !currentKeys.includes(key))
    ) {
      // 兼容旧数据库只缺少新增字段的情况：仅补默认值，绝不能把
      // 已持久化的认证开关、密码和 ISO 地址整体恢复为默认配置。
      fillMissingDefaults();
    }
  },
  { immediate: true },
);

defineExpose({ resetDefaults, validate });
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
.field-error {
  width: 100%;
  margin-top: 4px;
  color: var(--el-color-danger);
  font-size: 12px;
}
.directory-path-input {
  :deep(.el-input__wrapper) {
    padding: 1px 14px;
    border-radius: 10px 0 0 10px !important;
    transition: box-shadow 0.2s ease;
  }

  :deep(.el-input-group__append) {
    padding: 4px;
    background: linear-gradient(
      135deg,
      rgba(59, 130, 246, 0.08),
      rgba(14, 165, 233, 0.12)
    );
    border-radius: 0 10px 10px 0;
    box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.18) inset;
  }

  &:hover :deep(.el-input__wrapper),
  &:focus-within :deep(.el-input__wrapper) {
    box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.55) inset !important;
  }
}
.directory-path-actions {
  display: inline-flex;
  vertical-align: middle;

  :deep(.el-button) {
    height: 32px;
    margin: 0;
    padding: 0 12px;
    border: 0;
    border-radius: 7px !important;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.01em;
    transition:
      transform 0.18s ease,
      box-shadow 0.18s ease,
      background 0.18s ease;
  }

  :deep(.directory-path-button) {
    color: var(--color-primary);
    background: rgba(59, 130, 246, 0.12);

    &:hover,
    &:focus {
      color: #2563eb;
      background: rgba(59, 130, 246, 0.2);
      box-shadow: 0 3px 10px rgba(37, 99, 235, 0.14);
      transform: translateY(-1px);
    }

    &:active {
      transform: translateY(0);
    }
  }
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
.iec104-connect-options {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 32px;
  margin: 0 18px 20px;
}

.iec104-connect-option {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  color: var(--el-text-color-primary);
  cursor: pointer;
  user-select: none;
}

.iec104-connect-option__input {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: 0;
  opacity: 0;
  pointer-events: none;
}

.iec104-connect-option__box {
  display: inline-flex;
  width: 16px;
  height: 16px;
  flex: none;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
  transition:
    background-color 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease;

  svg {
    width: 13px;
    height: 13px;
    overflow: visible;
    opacity: 0;
    transform: scale(0.7);
    transition:
      opacity 0.12s ease,
      transform 0.12s ease;
  }

  path {
    fill: none;
    stroke: #fff;
    stroke-width: 2.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
}

.iec104-connect-option:hover .iec104-connect-option__box {
  border-color: var(--el-color-primary);
}

.iec104-connect-option__input:checked + .iec104-connect-option__box {
  background: #67aaf4;
  border-color: #337ecc;
  box-shadow: 0 1px 3px rgba(51, 126, 204, 0.24);

  svg {
    opacity: 1;
    transform: scale(1);
  }
}

.iec104-connect-option__input:focus-visible + .iec104-connect-option__box {
  outline: 2px solid rgba(64, 158, 255, 0.32);
  outline-offset: 2px;
}

.iec104-connect-option__label {
  padding-left: 6px;
  font-size: 15px;
  font-weight: 500;
  line-height: 20px;
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
