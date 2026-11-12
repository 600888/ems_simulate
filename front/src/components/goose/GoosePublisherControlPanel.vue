<template>
  <el-empty
    v-if="!block?.publisher"
    :description="$t('goose.selectPublisherBlock')"
  />
  <div v-else class="control-panel">
    <el-descriptions :column="2" border size="small" label-width="auto">
      <el-descriptions-item :label="$t('goose.detailLabels.name')">{{
        block.display_name
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.detailLabels.publisherType')"
        ><el-tag type="primary">{{
          $t("goose.publisher")
        }}</el-tag></el-descriptions-item
      >
      <el-descriptions-item
        :label="$t('goose.detailLabels.goCbRef')"
        :span="2"
        >{{ block.go_cb_ref }}</el-descriptions-item
      >
      <el-descriptions-item :label="$t('goose.detailLabels.goId')">{{
        block.go_id || "-"
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.detailLabels.appId')">{{
        formatAppId(block.app_id)
      }}</el-descriptions-item>
      <el-descriptions-item
        :label="$t('goose.detailLabels.dataSet')"
        :span="2"
        >{{ block.data_set_ref || "-" }}</el-descriptions-item
      >
      <el-descriptions-item :label="$t('goose.detailLabels.iedLdLn')"
        >{{ block.ied_name }} / {{ block.ld_inst }} /
        {{ block.ln_name }}</el-descriptions-item
      >
      <el-descriptions-item :label="$t('goose.detailLabels.stNumSqNum')"
        >{{ block.st_num }} / {{ block.sq_num }}</el-descriptions-item
      >
      <el-descriptions-item :label="$t('goose.detailLabels.interface')">{{
        block.interface
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('goose.detailLabels.numEntries')">{{
        block.data_values.length
      }}</el-descriptions-item>
    </el-descriptions>

    <section class="config-section">
      <div class="section-header">
        <div class="section-title">{{ $t("goose.publishConfig") }}</div>
        <el-button
          type="primary"
          :loading="loading"
          @click="emit('apply', { ...form })"
          >{{ $t("goose.applyConfig") }}</el-button
        >
      </div>
      <el-form label-width="200px" class="config-form">
        <div class="config-switches">
          <el-form-item :label="$t('goose.publishEnable')">
            <el-switch
              v-model="form.enabled"
              inline-prompt
              :active-text="$t('goose.enabled')"
              :inactive-text="$t('goose.disabled')"
            />
          </el-form-item>
          <el-form-item
            :label="$t('goose.configLabels.simulation')"
            label-width="auto"
          >
            <el-switch
              v-model="form.simulation"
              inline-prompt
              :active-text="$t('goose.enabled')"
              :inactive-text="$t('goose.disabled')"
            />
          </el-form-item>
          <el-form-item
            class="commissioning-switch"
            :label="$t('goose.configLabels.needsCommissioning')"
          >
            <el-switch
              v-model="form.needs_commissioning"
              inline-prompt
              :active-text="$t('goose.enabled')"
              :inactive-text="$t('goose.disabled')"
            />
          </el-form-item>
        </div>
        <el-form-item :label="$t('goose.configLabels.interface')">
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
        <el-form-item :label="$t('goose.configLabels.goId')"
          ><el-input v-model="form.go_id"
        /></el-form-item>
        <el-form-item :label="$t('goose.configLabels.dstMacOptional')">
          <el-input
            v-model="form.dst_mac"
            :placeholder="`${$t('goose.autoUseAppId')} ${defaultMulticastMac}`"
          />
        </el-form-item>
        <el-form-item :label="$t('goose.detailLabels.appId')"
          ><el-input-number
            v-model="form.app_id"
            :min="0"
            :max="65535"
            controls-position="right"
        /></el-form-item>
        <el-form-item :label="$t('goose.configLabels.dataSet')">
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
              :label="`${item.name} (${item.member_count} ${$t('goose.members')}) — ${item.ref}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('goose.configLabels.confRev')"
          ><el-input-number
            v-model="form.conf_rev"
            :min="1"
            controls-position="right"
        /></el-form-item>
        <el-form-item :label="$t('goose.configLabels.timeAllowedToLive')"
          ><el-input-number
            v-model="form.time_allowed_to_live"
            :min="1"
            :max="120000"
        /></el-form-item>
        <el-form-item :label="$t('goose.configLabels.vlanId')"
          ><el-input-number v-model="form.vlan_id" :min="0" :max="4095"
        /></el-form-item>
        <el-form-item :label="$t('goose.configLabels.vlanPrio')"
          ><el-input-number v-model="form.vlan_prio" :min="0" :max="7"
        /></el-form-item>
        <el-form-item :label="$t('goose.configLabels.retransmitInitial')">
          <el-input-number
            v-model="form.retransmit_initial_ms"
            :min="1"
            :max="form.retransmit_final_ms"
            :precision="0"
            :value-on-clear="2"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item :label="$t('goose.configLabels.retransmitMultiplier')">
          <el-input-number
            v-model="form.retransmit_multiplier"
            :min="1"
            :max="100"
            :step="0.1"
            :value-on-clear="2"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item :label="$t('goose.configLabels.retransmitFinal')">
          <el-input-number
            v-model="form.retransmit_final_ms"
            :min="form.retransmit_initial_ms"
            :max="60000"
            :precision="0"
            :value-on-clear="5000"
            controls-position="right"
          />
        </el-form-item>
      </el-form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Monitor } from "@element-plus/icons-vue";
import type { NetworkInterfaceInfo } from "@/api/gooseApi";
import type { GooseBlockItem } from "./gooseWorkbench";
import { DEFAULT_TIME_ALLOWED_TO_LIVE } from "./goosePublisherDefaults";
const { t } = useI18n();
const props = defineProps<{
  block: GooseBlockItem | null;
  loading?: boolean;
  interfaces: NetworkInterfaceInfo[];
  dataSets: Array<{ ref: string; name: string; member_count: number }>;
}>();
interface PublisherForm {
  enabled: boolean;
  interface: string;
  go_id: string;
  dst_mac: string;
  data_set_ref: string;
  app_id: number;
  conf_rev: number;
  time_allowed_to_live: number;
  vlan_id: number;
  vlan_prio: number;
  simulation: boolean;
  retransmit_initial_ms: number;
  retransmit_multiplier: number;
  retransmit_final_ms: number;
  needs_commissioning: boolean;
}
const form = reactive<PublisherForm>({
  enabled: false,
  interface: "",
  go_id: "",
  dst_mac: "",
  data_set_ref: "",
  app_id: 1,
  conf_rev: 1,
  time_allowed_to_live: DEFAULT_TIME_ALLOWED_TO_LIVE,
  vlan_id: 0,
  vlan_prio: 4,
  simulation: true,
  retransmit_initial_ms: 2,
  retransmit_multiplier: 2,
  retransmit_final_ms: 5000,
  needs_commissioning: false,
});
const emit = defineEmits<{ (e: "apply", form: PublisherForm): void }>();
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
const defaultMulticastMac = computed(() => {
  const appId = Number(form.app_id || 0) & 0xffff;
  return `01:0C:CD:01:${((appId >> 8) & 0xff).toString(16).toUpperCase().padStart(2, "0")}:${(appId & 0xff).toString(16).toUpperCase().padStart(2, "0")}`;
});
watch(
  () => props.block?.key,
  () => {
    const publisher = props.block?.publisher;
    if (!publisher) return;
    Object.assign(form, {
      enabled: publisher.is_running,
      interface: publisher.interface,
      go_id: publisher.go_id || "",
      dst_mac: publisher.dst_mac || "",
      data_set_ref: publisher.data_set_ref,
      app_id: publisher.app_id,
      conf_rev: publisher.conf_rev,
      time_allowed_to_live: publisher.time_allowed_to_live,
      vlan_id: publisher.vlan_id,
      vlan_prio: publisher.vlan_prio,
      simulation: publisher.simulation,
      retransmit_initial_ms: publisher.retransmit_initial_ms ?? 2,
      retransmit_multiplier: publisher.retransmit_multiplier ?? 2,
      retransmit_final_ms: publisher.retransmit_final_ms ?? 5000,
      needs_commissioning: publisher.needs_commissioning ?? false,
    });
  },
  { immediate: true },
);
function formatAppId(value: number | null) {
  return value == null
    ? "-"
    : `0x${value.toString(16).toUpperCase().padStart(4, "0")}`;
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
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.section-title {
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
.config-form :deep(.el-form-item__label) {
  height: auto;
  min-height: 32px;
  align-items: center;
  line-height: 20px;
  overflow-wrap: anywhere;
}
.config-form :deep(.el-input),
.config-form :deep(.el-input-number) {
  width: 100%;
}
.config-switches {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: center;
  gap: 18px;
}
.config-switches :deep(.el-form-item) {
  min-width: 0;
}
.config-switches :deep(.el-form-item__label-wrap) {
  margin-left: 0 !important;
}
.commissioning-switch {
  // Align the label and switch with the second parameter column.
  transform: translateX(calc(-50% - 9px));
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
