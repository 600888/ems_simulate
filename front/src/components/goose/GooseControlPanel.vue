<template>
  <el-empty v-if="!block" :description="$t('goose.selectControlBlock')" />
  <div v-else class="control-panel">
    <el-descriptions :column="2" border size="small" label-width="auto">
      <el-descriptions-item :label="$t('goose.name')">{{
        block.display_name
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.state')">
        <el-tag :type="stateTag">{{ stateLabel }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item :label="$t('goose.goCbRefLabel')" :span="2">{{
        block.go_cb_ref
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.goId')">{{
        block.go_id || "-"
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.appId')">{{
        formatAppId(block.app_id)
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.dataSet')" :span="2">{{
        block.data_set_ref || "-"
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.iedLdLn')"
        >{{ block.ied_name }} / {{ block.ld_inst }} /
        {{ block.ln_name }}</el-descriptions-item
      >
      <el-descriptions-item :label="$t('goose.stNumSqNum')"
        >{{ block.st_num }} / {{ block.sq_num }}</el-descriptions-item
      >
      <el-descriptions-item :label="$t('goose.confRevLabel')">
        <span :class="{ mismatch: block.subscription?.config_mismatch }"
          >{{ block.conf_rev }} /
          {{ block.subscription?.received_conf_rev || "-" }}</span
        >
      </el-descriptions-item>
      <el-descriptions-item :label="$t('goose.interface')">{{
        interfaceLabel
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.lastUpdate')">{{
        formatGooseTime(block.last_update)
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.messageCountLabel')">{{
        block.message_count || 0
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.timeAllowedToLive')"
        >{{
          block.subscription?.time_allowed_to_live || 0
        }}
        ms</el-descriptions-item
      >
    </el-descriptions>

    <section class="config-section">
      <div class="section-title">{{ $t("goose.subConfig") }}</div>
      <el-form label-width="200px" class="config-form">
        <el-form-item :label="$t('goose.goEna')">
          <el-switch
            v-model="form.enabled"
            :active-text="$t('goose.enabled')"
            :inactive-text="$t('goose.disabled')"
          />
        </el-form-item>
        <el-form-item :label="$t('goose.interface')">
          <el-select
            v-model="form.interface"
            style="width: 100%"
            :placeholder="$t('goose.interfaceSelect')"
          >
            <el-option
              v-for="item in interfaces"
              :key="item.id"
              :value="item.id"
              class="network-option-item"
            >
              <div class="network-option">
                <el-icon class="network-option-icon"><Monitor /></el-icon>
                <div class="network-option-body">
                  <span class="network-option-name">{{
                    item.display_name
                  }}</span>
                  <span class="network-option-mac"
                    >MAC: {{ (item.mac || "-").replace(/-/g, ":") }}</span
                  >
                </div>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('goose.filterAppId')">
          <el-input
            v-model="appIdHex"
            placeholder="0x0000"
            maxlength="6"
            @blur="normalizeAppIdHex"
          />
        </el-form-item>
        <el-form-item :label="$t('goose.goId')">
          <el-input v-model="form.go_id" />
        </el-form-item>
        <el-form-item :label="$t('goose.dstAddressFilter')">
          <el-input
            v-model="form.dst_mac"
            :placeholder="$t('goose.dstMacPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('goose.dataSet')">
          <el-select
            v-model="form.data_set_ref"
            style="width: 100%"
            :placeholder="$t('goose.dataSetSelect')"
            filterable
          >
            <el-option
              v-for="item in availableDataSets"
              :key="item.ref"
              :value="item.ref"
              :label="`${item.name} (${item.member_count} members) — ${item.ref}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('goose.confRev')">
          <el-input-number
            v-model="form.conf_rev"
            :min="0"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item :label="$t('goose.description')">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
    </section>
    <div class="actions">
      <el-button type="primary" :loading="loading" @click="apply">{{
        $t("goose.applyConfig")
      }}</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Monitor } from "@element-plus/icons-vue";
import type { NetworkInterfaceInfo } from "@/api/gooseApi";
import type { GooseBlockItem } from "./gooseWorkbench";
import { formatGooseTime } from "./gooseWorkbench";

const { t } = useI18n();

const props = defineProps<{
  block: GooseBlockItem | null;
  loading?: boolean;
  interfaces: NetworkInterfaceInfo[];
  dataSets: Array<{ ref: string; name: string; member_count: number }>;
}>();
const emit = defineEmits<{ (e: "apply", value: typeof form): void }>();
const form = reactive({
  enabled: false,
  interface: "",
  app_id: null as number | null,
  go_id: "",
  dst_mac: "",
  data_set_ref: "",
  conf_rev: 0,
  description: "",
});
const appIdHex = ref("");
const availableDataSets = computed(() => {
  if (
    !form.data_set_ref ||
    props.dataSets.some((item) => item.ref === form.data_set_ref)
  ) {
    return props.dataSets;
  }
  return [
    { ref: form.data_set_ref, name: form.data_set_ref, member_count: 0 },
    ...props.dataSets,
  ];
});
watch(appIdHex, (value) => {
  form.app_id = parseAppId(value);
});
watch(() => props.block?.key, sync, { immediate: true });
function sync() {
  Object.assign(form, {
    enabled: !!props.block?.enabled,
    app_id: parseAppId(props.block?.app_id),
    go_id: props.block?.go_cb_ref || props.block?.go_id || "",
    dst_mac: props.block?.dst_mac || "",
    interface: props.block?.interface || "",
    data_set_ref: props.block?.data_set_ref || "",
    conf_rev: props.block?.conf_rev || 0,
    description: props.block?.subscription?.description || "",
  });
  appIdHex.value = form.app_id == null ? "" : formatAppId(form.app_id);
}
const stateLabel = computed(() =>
  !props.block?.enabled
    ? t("goose.disabled")
    : {
        connected: t("gooseStateLabels.connected"),
        lost: t("gooseStateLabels.lost"),
        error: t("gooseStateLabels.error"),
        init: t("goose.waiting"),
      }[props.block.state] || props.block.state,
);
const stateTag = computed(() =>
  !props.block?.enabled
    ? "info"
    : props.block.state === "connected"
      ? "success"
      : props.block.state === "init"
        ? "primary"
        : "danger",
);
const interfaceLabel = computed(() => {
  const item = props.interfaces.find(
    (candidate) => candidate.id === props.block?.interface,
  );
  return item
    ? `${item.display_name} (${item.mac || "-"})`
    : props.block?.interface || "-";
});
function formatAppId(value: number | null) {
  return value == null
    ? "-"
    : `0x${value.toString(16).toUpperCase().padStart(4, "0")}`;
}
function parseAppId(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isInteger(value) && value >= 0 && value <= 0xffff
      ? value
      : null;
  }
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text) return null;
  const digits = text.replace(/^0x/i, "");
  if (!/^[0-9a-fA-F]{1,4}$/.test(digits)) return null;
  return Number.parseInt(digits, 16);
}
function normalizeAppIdHex() {
  appIdHex.value = form.app_id == null ? "" : formatAppId(form.app_id);
}
function apply() {
  emit("apply", { ...form, app_id: parseAppId(form.app_id) });
}
</script>

<style scoped lang="scss">
.control-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.config-section {
  padding: 14px 16px;
  border: 1px solid var(--border-color);
  background: var(--bg-subtle);
}
.section-title {
  margin-bottom: 14px;
  color: var(--text-primary);
  font-weight: 700;
}
.config-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 0 18px;
}
.config-form :deep(.el-form-item) {
  margin-bottom: 14px;
}
.config-form :deep(.el-input),
.config-form :deep(.el-input-number) {
  width: 100%;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
.mismatch {
  color: #d98200;
  font-weight: 700;
}
@container (max-width: 1000px) {
  .config-form {
    grid-template-columns: 1fr;
  }
}
</style>

<style lang="scss">
.el-select-dropdown__item.network-option-item {
  height: auto;
  min-height: auto;
  padding: 4px 12px;
}
.el-select-dropdown__item.network-option-item:first-child {
  padding-top: 0;
}
.el-select-dropdown__item.network-option-item:last-child {
  padding-bottom: 0;
}
.network-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  .network-option-icon {
    font-size: 16px;
    color: #409eff;
    flex-shrink: 0;
  }
  .network-option-body {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .network-option-name {
    font-size: 13px;
    color: var(--text-primary);
    line-height: 1.3;
  }
  .network-option-mac {
    font-family:
      "Cascadia Code", "Fira Code", "JetBrains Mono", Consolas, monospace;
    font-size: 11px;
    color: #909399;
    line-height: 1.2;
  }
}
</style>
