<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="440px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-alert
      v-if="isDanger"
      type="warning"
      :title="t('slave.dlt645DangerTip')"
      :closable="false"
      show-icon
      class="dlt645-danger-alert"
    />

    <!-- 读通讯地址结果区 -->
    <div v-if="command === 'read_address'" class="dlt645-address-result">
      <div class="dlt645-address-label">
        {{ t("slave.dlt645CurrentAddress") }}
      </div>
      <div
        class="dlt645-address-value"
        :class="{ 'dlt645-address-muted': readingAddress || !currentAddress }"
      >
        {{
          readingAddress
            ? t("slave.dlt645Reading")
            : (currentAddress ??
              (addressError ? t("slave.dlt645ReadFailed") : "--"))
        }}
      </div>
      <el-button
        size="small"
        class="dlt645-reread-btn"
        :loading="readingAddress"
        :icon="Refresh"
        @click="emit('read-address')"
      >
        {{ t("slave.dlt645ReRead") }}
      </el-button>
    </div>

    <!-- 写通讯地址：显示原通讯地址 -->
    <div v-if="command === 'write_address'" class="dlt645-address-result">
      <div class="dlt645-address-label">
        {{ t("slave.dlt645OriginalAddress") }}
      </div>
      <div
        class="dlt645-address-value"
        :class="{ 'dlt645-address-muted': readingAddress || !currentAddress }"
      >
        {{
          readingAddress
            ? t("slave.dlt645Reading")
            : (currentAddress ??
              (addressError ? t("slave.dlt645ReadFailed") : "--"))
        }}
      </div>
    </div>

    <el-form
      v-if="fields.length > 0"
      label-width="90px"
      class="dlt645-cmd-form"
    >
      <el-form-item
        v-for="field in fields"
        :key="field.key"
        :label="t(field.labelKey)"
      >
        <el-date-picker
          v-if="field.type === 'datetime'"
          v-model="form[field.key]"
          type="datetime"
          :placeholder="t('slave.dlt645TimePlaceholder')"
          format="YYYY-MM-DD HH:mm:ss"
          value-format="YYYY-MM-DDTHH:mm:ss"
          style="width: 100%"
        />
        <el-select
          v-else-if="field.type === 'select'"
          v-model="form[field.key]"
          style="width: 100%"
        >
          <el-option
            v-for="opt in field.options"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-input
          v-else
          v-model="form[field.key]"
          :placeholder="field.placeholderKey ? t(field.placeholderKey) : ''"
          :maxlength="field.maxlength"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="close">{{ t("common.cancel") }}</el-button>
      <el-button
        v-if="command !== 'read_address'"
        :type="isDanger ? 'danger' : 'primary'"
        :loading="loading"
        @click="confirm"
      >
        {{ isDanger ? t("slave.dlt645Execute") : t("common.confirm") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { computed, reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Refresh } from "@element-plus/icons-vue";

export interface Dlt645FieldConfig {
  key: string;
  labelKey: string;
  type: "text" | "password" | "select" | "datetime";
  default?: string | number;
  maxlength?: number;
  placeholderKey?: string;
  options?: { label: string; value: string | number }[];
}

const props = defineProps<{
  modelValue: boolean;
  command: string;
  isServer: boolean;
  loading?: boolean;
  /** 当前（原）通讯地址，由父组件读取后传入 */
  currentAddress?: string | null;
  /** 通讯地址读取中 */
  readingAddress?: boolean;
  /** 通讯地址读取失败 */
  addressError?: boolean;
  /** 当前通信速率（更改速率弹窗默认选中值） */
  currentBaudRate?: number | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "confirm", params: Record<string, unknown>): void;
  (e: "read-address"): void;
}>();

const { t } = useI18n();

/** 需要输入参数的命令 → 表单字段定义（主站） */
const CLIENT_FIELDS: Record<string, Dlt645FieldConfig[]> = {
  write_address: [
    {
      key: "address",
      labelKey: "slave.dlt645Address",
      type: "text",
      placeholderKey: "slave.dlt645AddressPlaceholder",
      maxlength: 12,
      default: "",
    },
  ],
  broadcast_time_sync: [
    {
      key: "datetime",
      labelKey: "slave.dlt645Time",
      type: "datetime",
      default: "",
    },
  ],
  change_baud_rate: [
    {
      key: "baud",
      labelKey: "slave.dlt645BaudRate",
      type: "select",
      default: 9600,
      options: [1200, 2400, 4800, 9600, 19200].map((v) => ({
        label: `${v} bps`,
        value: v,
      })),
    },
  ],
  change_password: [
    {
      key: "old_password",
      labelKey: "slave.dlt645OldPassword",
      type: "password",
      placeholderKey: "slave.dlt645PasswordPlaceholder",
      maxlength: 8,
      default: "00000000",
    },
    {
      key: "new_password",
      labelKey: "slave.dlt645NewPassword",
      type: "password",
      placeholderKey: "slave.dlt645PasswordPlaceholder",
      maxlength: 8,
      default: "00000000",
    },
  ],
  clear_demand: [passwordField("slave.dlt645Password")],
  clear_meter: [passwordField("slave.dlt645Password")],
  clear_event: [passwordField("slave.dlt645Password")],
};

/** 从站（模拟电表）命令 → 表单字段定义 */
const SERVER_FIELDS: Record<string, Dlt645FieldConfig[]> = {
  write_address: CLIENT_FIELDS.write_address,
  set_time: [
    {
      key: "datetime",
      labelKey: "slave.dlt645Time",
      type: "datetime",
      default: "",
    },
  ],
  change_password: [passwordField("slave.dlt645NewPassword")],
};

/** 危险命令（需二次确认，按钮变红） */
const DANGER_COMMANDS = new Set(["clear_demand", "clear_meter", "clear_event"]);

function passwordField(labelKey: string): Dlt645FieldConfig {
  return {
    key: "password",
    labelKey,
    type: "password",
    placeholderKey: "slave.dlt645PasswordPlaceholder",
    maxlength: 8,
    default: "00000000",
  };
}

const fields = computed<Dlt645FieldConfig[]>(() => {
  const map = props.isServer ? SERVER_FIELDS : CLIENT_FIELDS;
  const list = map[props.command] ?? [];
  // 更改通信速率：默认选中当前速率（有值时覆盖静态默认 9600）
  if (props.command === "change_baud_rate" && props.currentBaudRate != null) {
    return list.map((field) =>
      field.key === "baud"
        ? { ...field, default: props.currentBaudRate ?? 9600 }
        : field,
    );
  }
  return list;
});

const isDanger = computed(() => DANGER_COMMANDS.has(props.command));

const title = computed(() => {
  const key = props.isServer
    ? `slave.dlt645ServerCmd.${props.command}`
    : `slave.dlt645ClientCmd.${props.command}`;
  return t(key);
});

const form = reactive<Record<string, unknown>>({});

/** 初始化表单默认值（含时间字段默认当前时间） */
const initForm = () => {
  for (const key of Object.keys(form)) delete form[key];
  for (const field of fields.value) {
    if (field.type === "datetime") {
      const now = new Date();
      const pad = (n: number) => String(n).padStart(2, "0");
      form[field.key] =
        `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
        `T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    } else {
      form[field.key] = field.default ?? "";
    }
  }
};

watch(
  () => [props.modelValue, props.command],
  ([visible]) => {
    if (visible) initForm();
  },
);

const close = () => emit("update:modelValue", false);

const confirm = () => {
  const params: Record<string, unknown> = {};
  for (const field of fields.value) {
    params[field.key] = form[field.key];
  }
  emit("confirm", params);
};
</script>

<style scoped>
.dlt645-danger-alert {
  margin-bottom: 14px;
}
.dlt645-cmd-form {
  margin-top: 4px;
}
.dlt645-address-result {
  margin: 2px 0 16px;
  padding: 12px 14px;
  background: var(--color-bg-secondary, #f8fafc);
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.dlt645-address-label {
  font-size: 13px;
  color: var(--text-secondary, #94a3b8);
  white-space: nowrap;
}
.dlt645-address-value {
  flex: 1;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 1px;
  font-family: "Consolas", "Menlo", monospace;
  color: var(--color-primary, #3b82f6);
}
.dlt645-address-value.dlt645-address-muted {
  color: var(--text-secondary, #94a3b8);
  font-size: 14px;
  font-weight: 500;
}
.dlt645-reread-btn {
  flex-shrink: 0;
}
</style>
