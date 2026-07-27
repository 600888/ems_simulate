<template>
  <div class="goose-workbench">
    <header class="manager-header">
      <h3>{{ $t("goose.gooseManagement") }}</h3>
      <div class="header-actions">
        <span>{{ $t("goose.autoRefresh") }}</span>
        <el-switch v-model="autoRefresh" />
        <el-select
          v-model="pollInterval"
          :disabled="!autoRefresh"
          style="width: 90px"
        >
          <el-option :value="1000" label="1 s" />
          <el-option :value="2000" label="2 s" />
          <el-option :value="5000" label="5 s" />
        </el-select>
        <el-button :icon="Refresh" :loading="loading" @click="loadBlocks">{{
          $t("goose.refresh")
        }}</el-button>
        <el-button
          v-if="selected?.kind === 'publisher'"
          type="primary"
          :disabled="!selected.publisher?.is_running"
          @click="publishSelected"
          >{{ $t("goose.immediatePublish") }}</el-button
        >
        <el-button v-if="selected" type="danger" plain @click="deleteSelected">
          {{ $t("goose.deleteControlBlock") }}
        </el-button>
        <el-button @click="batchMode = !batchMode">{{
          batchMode ? $t("goose.exitBatch") : $t("goose.batchMode")
        }}</el-button>
        <template v-if="batchMode">
          <el-button
            type="success"
            :disabled="!checkedKeys.length"
            @click="batchSetEnabled(true)"
            >{{ $t("goose.batchEnable") }}</el-button
          >
          <el-button
            type="warning"
            :disabled="!checkedKeys.length"
            @click="batchSetEnabled(false)"
            >{{ $t("goose.batchDisable") }}</el-button
          >
        </template>
      </div>
    </header>

    <main class="manager-body" v-loading="loading && !blocks.length">
      <el-empty
        v-if="!loading && !blocks.length"
        :description="$t('goose.noGooseBlocks')"
      />
      <template v-else>
        <GooseBlockTreePanel
          :blocks="blocks"
          :selected-key="selected?.key"
          :batch-mode="batchMode"
          @select="selectBlock"
          @checked="checkedKeys = $event"
        />
        <section class="workspace">
          <el-empty
            v-if="!selected"
            :description="$t('goose.selectFromLeft')"
          />
          <el-tabs
            v-else
            v-model="activeTab"
            class="workspace-tabs"
            @tab-change="handleTabChange"
          >
            <el-tab-pane :label="$t('goose.propertiesTab')" name="attributes">
              <GoosePublisherControlPanel
                v-if="selected.kind === 'publisher'"
                :block="selected"
                :loading="applying"
                :interfaces="networkInterfaces"
                :data-sets="dataSets"
                @apply="applyPublisherConfig"
              />
              <GooseControlPanel
                v-else
                :block="selected"
                :loading="applying"
                :interfaces="networkInterfaces"
                :data-sets="dataSets"
                @apply="applySubscriptionConfig"
              />
            </el-tab-pane>

            <el-tab-pane
              :label="
                selected.kind === 'publisher'
                  ? $t('goose.currentData')
                  : $t('goose.recentData')
              "
              name="latest"
            >
              <div class="latest-pane">
                <div class="summary">
                  <el-tag
                    :type="
                      selected.kind === 'publisher' ? 'primary' : 'success'
                    "
                  >
                    {{
                      selected.kind === "publisher"
                        ? $t("goose.publisher")
                        : $t("goose.subscriber")
                    }}
                  </el-tag>
                  <span v-if="selected.kind === 'subscriber'"
                    >{{ $t("goose.timeLabel")
                    }}{{ formatGooseTime(selected.last_update) }}</span
                  >
                  <span>{{ $t("goose.stNumLabel") }}{{ selected.st_num }}</span>
                  <span>{{ $t("goose.sqNumLabel") }}{{ selected.sq_num }}</span>
                  <span
                    >{{ $t("goose.dataSetLabel")
                    }}{{ selected.data_set_ref || "-" }}</span
                  >
                  <span
                    >{{ $t("goose.valueLabel")
                    }}{{ selected.data_values.length }}</span
                  >
                </div>
                <GooseDataSetTable
                  :values="selected.data_values"
                  :editable="selected.kind === 'publisher'"
                  :updating-index="updatingEntryIndex"
                  @update-value="updatePublisherDataValue"
                />
              </div>
            </el-tab-pane>

            <el-tab-pane
              v-if="selected.kind === 'subscriber'"
              :label="
                $t('goose.historyTab') +
                ' (' +
                (selected.subscription?.history_count || 0) +
                ')'
              "
              name="history"
            >
              <div class="history-pane">
                <el-table
                  :data="history"
                  size="small"
                  border
                  height="100%"
                  highlight-current-row
                  row-key="received_at"
                  :current-row-key="selectedHistory?.received_at"
                  @current-change="handleHistoryCurrentChange"
                >
                  <el-table-column
                    type="index"
                    label="#"
                    width="48"
                    align="center"
                  />
                  <el-table-column
                    prop="received_at"
                    :label="$t('goose.receiveTime')"
                    min-width="185"
                    sortable
                  >
                    <template #default="{ row }">{{
                      formatGooseTime(row.received_at)
                    }}</template>
                  </el-table-column>
                  <el-table-column
                    prop="st_num"
                    :label="$t('goose.stNum')"
                    width="75"
                  />
                  <el-table-column
                    prop="sq_num"
                    :label="$t('goose.sqNum')"
                    width="75"
                  />
                  <el-table-column
                    prop="value_count"
                    :label="$t('goose.dataItems')"
                    width="70"
                  />
                  <el-table-column
                    prop="changed_count"
                    :label="$t('goose.changedItems')"
                    width="70"
                  />
                </el-table>
                <div class="history-detail">
                  <div v-if="selectedHistory" class="summary">
                    <span
                      >{{ $t("goose.timeLabel")
                      }}{{ formatGooseTime(selectedHistory.received_at) }}</span
                    >
                    <span
                      >{{ $t("goose.dataSetLabel")
                      }}{{ selectedHistory.data_set_ref || "-" }}</span
                    >
                    <span
                      >{{ $t("goose.stNumLabel")
                      }}{{ selectedHistory.st_num }}</span
                    >
                    <span
                      >{{ $t("goose.sqNumLabel")
                      }}{{ selectedHistory.sq_num }}</span
                    >
                    <span
                      >{{ $t("goose.dataItems")
                      }}{{ selectedHistory.value_count }}</span
                    >
                    <span
                      >{{ $t("goose.changedItems")
                      }}{{ selectedHistory.changed_count }}</span
                    >
                  </div>
                  <GooseDataSetTable
                    :values="selectedHistory?.data_values || []"
                  />
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onActivated,
  onDeactivated,
  onUnmounted,
  ref,
  watch,
} from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import { showError } from "@/api/http";
import { Refresh } from "@element-plus/icons-vue";
import {
  getGoosePublishers,
  getGooseReceivers,
  getGooseNetworkInterfaces,
  getGooseSubscriptionHistory,
  startGoosePublisher,
  stopGoosePublisher,
  publishGooseNow,
  updateGoosePublisherEntry,
  replaceGoosePublisherEntries,
  deleteGoosePublisher,
  removeGooseSubscription,
  stopGooseReceiver,
  updateGoosePublisher,
  updateGooseReceiver,
  updateGooseSubscription,
  type GooseMessageHistoryItem,
} from "@/api/gooseApi";
import {
  getIEC61850DatasetDetail,
  getIEC61850Structure,
  type IEC61850DataSetInfo,
  type IEC61850DataSetMember,
} from "@/api/channelApi";
import GooseBlockTreePanel from "./GooseBlockTreePanel.vue";
import GooseControlPanel from "./GooseControlPanel.vue";
import GooseDataSetTable from "./GooseDataSetTable.vue";
import GoosePublisherControlPanel from "./GoosePublisherControlPanel.vue";
import {
  flattenGooseBlocks,
  formatGooseTime,
  toGooseDataSetRef,
  type GooseBlockItem,
} from "./gooseWorkbench";

const props = defineProps<{ channelId?: number }>();
const { t } = useI18n();
const publishers = ref<Awaited<ReturnType<typeof getGoosePublishers>>>([]);
const receivers = ref<Awaited<ReturnType<typeof getGooseReceivers>>>([]);
const networkInterfaces = ref<
  Awaited<ReturnType<typeof getGooseNetworkInterfaces>>
>([]);
const dataSets = ref<IEC61850DataSetInfo[]>([]);
const blocks = computed(() =>
  flattenGooseBlocks(publishers.value, receivers.value),
);
const selectedKey = ref("");
const selected = computed(
  () => blocks.value.find((item) => item.key === selectedKey.value) || null,
);
const activeTab = ref("attributes");
const history = ref<GooseMessageHistoryItem[]>([]);
const selectedHistory = ref<GooseMessageHistoryItem | null>(null);
const loading = ref(false);
const applying = ref(false);
const updatingEntryIndex = ref<number | null>(null);
const autoRefresh = ref(true);
const pollInterval = ref(2000);
const batchMode = ref(false);
const checkedKeys = ref<string[]>([]);
let timer: ReturnType<typeof setTimeout> | null = null;
let active = true;
let historyRequestId = 0;
let historyKnownRevision = -1;

watch(
  () => props.channelId,
  async () => {
    selectedKey.value = "";
    history.value = [];
    await Promise.all([loadBlocks(), loadNetworkInterfaces(), loadDataSets()]);
  },
  { immediate: true },
);
watch([autoRefresh, pollInterval], schedule);

async function loadBlocks(showLoading = true) {
  if (!props.channelId) return;
  if (showLoading) loading.value = true;
  try {
    [publishers.value, receivers.value] = await Promise.all([
      getGoosePublishers(props.channelId),
      getGooseReceivers(props.channelId),
    ]);
    if (selectedKey.value && !selected.value) selectedKey.value = "";
    if (
      activeTab.value === "history" &&
      selected.value?.kind === "subscriber"
    ) {
      await loadHistory(false);
    }
  } finally {
    loading.value = false;
    schedule();
  }
}

// 网卡列表只需首次加载一次，不参与轮询
async function loadNetworkInterfaces() {
  try {
    const list = await getGooseNetworkInterfaces();
    networkInterfaces.value = list.filter(
      (item) => item.is_up && !item.is_loopback && item.supports_raw_ethernet,
    );
  } catch {
    // 静默失败，不影响主流程
  }
}

async function loadDataSets() {
  if (!props.channelId) {
    dataSets.value = [];
    return;
  }
  try {
    const structure = await getIEC61850Structure(props.channelId);
    dataSets.value = structure.DataSets.flatMap((ld) =>
      ld.children.flatMap((ln) => ln.datasets),
    ).map((dataSet) => ({
      ...dataSet,
      ref: toGooseDataSetRef(dataSet.ref),
    }));
  } catch {
    dataSets.value = [];
  }
}

function selectBlock(block: GooseBlockItem) {
  selectedKey.value = block.key;
  history.value = [];
  selectedHistory.value = null;
  historyKnownRevision = -1;
  historyRequestId++;
  if (block.kind === "publisher" && activeTab.value === "history")
    activeTab.value = "attributes";
  if (activeTab.value === "history") void loadHistory(true);
}

async function publishSelected() {
  const block = selected.value;
  if (!props.channelId || block?.kind !== "publisher" || !block.publisher)
    return;
  try {
    await publishGooseNow(props.channelId, block.publisher.id);
    ElMessage.success(t("goose.publishSuccess"));
    await loadBlocks(false);
  } catch (error) {
    showError(error, t("goose.publishFailed"));
  }
}

async function updatePublisherDataValue(payload: {
  index: number;
  value: string | number | boolean;
}) {
  const block = selected.value;
  if (block?.kind !== "publisher" || !block.publisher) return;
  updatingEntryIndex.value = payload.index;
  try {
    await updateGoosePublisherEntry(
      block.publisher.id,
      payload.index,
      payload.value,
    );
    await loadBlocks(false);
    ElMessage.success(t("goose.datasetValueUpdated"));
  } catch (error) {
    showError(error, t("goose.datasetsUpdated"));
    await loadBlocks(false);
  } finally {
    updatingEntryIndex.value = null;
  }
}

async function deleteSelected() {
  const block = selected.value;
  if (!props.channelId || !block) return;
  try {
    await ElMessageBox.confirm(
      t("goose.deleteControlConfirm", { name: block.display_name }),
      t("goose.deleteControlTitle"),
      {
        confirmButtonText: t("common.confirm"),
        cancelButtonText: t("common.cancel"),
        type: "warning",
      },
    );
    if (block.kind === "publisher" && block.publisher) {
      await deleteGoosePublisher(props.channelId, block.publisher.id);
    } else if (block.receiver_id) {
      const receiver = receivers.value.find(
        (item) => item.id === block.receiver_id,
      );
      if (receiver?.is_running)
        await stopGooseReceiver(props.channelId, receiver.id);
      await removeGooseSubscription(block.receiver_id, block.go_cb_ref);
    }
    selectedKey.value = "";
    await loadBlocks(false);
    ElMessage.success(t("goose.deletedControl"));
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      showError(error, t("goose.controlDeleteFailed"));
    }
  }
}

function parseMac(value: string): number[] | null {
  if (!value.trim()) return null;
  const parts = value.split(/[:-]/);
  if (
    parts.length !== 6 ||
    parts.some((item) => !/^[0-9a-fA-F]{2}$/.test(item))
  ) {
    throw new Error(t("goose.macFormatError"));
  }
  return parts.map((item) => Number.parseInt(item, 16));
}

function defaultGooseMulticastMac(appId: number): string {
  const normalized = Number(appId || 0) & 0xffff;
  const high = ((normalized >> 8) & 0xff)
    .toString(16)
    .toUpperCase()
    .padStart(2, "0");
  const low = (normalized & 0xff).toString(16).toUpperCase().padStart(2, "0");
  return `01:0C:CD:01:${high}:${low}`;
}

function normalizeGooseEntryType(iecType: string): string {
  const normalized = String(iecType || "")
    .trim()
    .toLowerCase();
  if (
    [
      "boolean",
      "integer",
      "float",
      "string",
      "bitstring",
      "timestamp",
    ].includes(normalized)
  ) {
    return normalized;
  }
  return "boolean";
}

function defaultGooseEntryValue(iecType: string): boolean | number | string {
  if (iecType === "boolean") return false;
  if (iecType === "string") return "";
  return 0;
}

function dataSetMemberToPublisherEntry(member: IEC61850DataSetMember) {
  const iecType = normalizeGooseEntryType(member.iec_type);
  const value = member.value;
  return {
    name: member.ref,
    value:
      typeof value === "boolean" ||
      typeof value === "number" ||
      typeof value === "string"
        ? value
        : defaultGooseEntryValue(iecType),
    iec_type: iecType,
  };
}

async function applyPublisherConfig(form: {
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
}) {
  const block = selected.value;
  if (!props.channelId || block?.kind !== "publisher" || !block.publisher)
    return;
  applying.value = true;
  const publisherId = block.publisher.id;
  try {
    const dataSetDetail = form.data_set_ref
      ? await getIEC61850DatasetDetail(props.channelId, form.data_set_ref)
      : null;
    if (
      form.data_set_ref &&
      (!dataSetDetail || !dataSetDetail.members.length)
    ) {
      throw new Error(
        t("goose.noPublishableMembers", { name: form.data_set_ref }),
      );
    }

    if (block.publisher.is_running)
      await stopGoosePublisher(props.channelId, publisherId);
    await updateGoosePublisher(publisherId, {
      channel_id: props.channelId,
      interface: form.interface,
      go_id: form.go_id,
      data_set_ref: form.data_set_ref,
      app_id: form.app_id,
      conf_rev: form.conf_rev,
      time_allowed_to_live: form.time_allowed_to_live,
      dst_mac: form.dst_mac ? parseMac(form.dst_mac) : null,
      vlan_id: form.vlan_id,
      vlan_prio: form.vlan_prio,
      simulation: form.simulation,
    });
    if (dataSetDetail) {
      const expectedNames = dataSetDetail.members.map((member) => member.ref);
      const currentNames = (block.publisher.entries || []).map(
        (entry) => entry.name,
      );
      const entriesMatch =
        expectedNames.length === currentNames.length &&
        expectedNames.every((name, index) => name === currentNames[index]);
      if (!entriesMatch) {
        await replaceGoosePublisherEntries(
          props.channelId,
          publisherId,
          dataSetDetail.members.map(dataSetMemberToPublisherEntry),
        );
      }
    }
    if (form.enabled) await startGoosePublisher(props.channelId, publisherId);
    ElMessage.success(
      form.dst_mac
        ? t("goose.publishApplySuccess")
        : t("goose.publishApplySuccessNoMac", {
            mac: defaultGooseMulticastMac(form.app_id),
          }),
    );
    await loadBlocks(false);
  } catch (error) {
    showError(error, t("goose.publishApplyFailed"));
  } finally {
    applying.value = false;
  }
}

async function applySubscriptionConfig(form: {
  enabled: boolean;
  interface: string;
  app_id: number | null;
  go_id: string;
  dst_mac: string;
  data_set_ref: string;
  conf_rev: number;
  description: string;
}) {
  const block = selected.value;
  if (
    !props.channelId ||
    block?.kind !== "subscriber" ||
    !block.subscription ||
    !block.receiver_id
  )
    return;
  applying.value = true;
  try {
    const receiver = receivers.value.find(
      (item) => item.id === block.receiver_id,
    );
    if (receiver && form.interface && form.interface !== receiver.interface) {
      if (receiver.is_running)
        await stopGooseReceiver(props.channelId, receiver.id);
      await updateGooseReceiver(props.channelId, receiver.id, {
        interface: form.interface,
        name: receiver.name || "default",
        description: receiver.description || "",
        auto_start: receiver.auto_start || false,
      });
    }
    await updateGooseSubscription(
      props.channelId,
      block.receiver_id,
      block.go_cb_ref,
      {
        enabled: form.enabled,
        app_id: form.app_id,
        dst_mac: form.dst_mac ? parseMac(form.dst_mac) : null,
        description: form.description,
        data_set_ref: form.data_set_ref,
        conf_rev: form.conf_rev,
        ied_name: block.ied_name,
        ld_inst: block.ld_inst,
        ln_name: block.ln_name,
        dataset_entries: block.subscription.dataset_entries,
        go_id: form.go_id,
      },
    );
    ElMessage.success(t("goose.subApplySuccess"));
    await loadBlocks(false);
  } catch (error) {
    showError(error, t("goose.subApplyFailed"));
  } finally {
    applying.value = false;
  }
}

async function setBlockEnabled(block: GooseBlockItem, enabled: boolean) {
  if (!props.channelId) return;
  if (block.kind === "publisher" && block.publisher) {
    if (enabled) await startGoosePublisher(props.channelId, block.publisher.id);
    else await stopGoosePublisher(props.channelId, block.publisher.id);
    return;
  }
  if (block.subscription && block.receiver_id) {
    await updateGooseSubscription(
      props.channelId,
      block.receiver_id,
      block.go_cb_ref,
      {
        enabled,
        app_id: block.subscription.app_id,
        dst_mac: block.dst_mac ? parseMac(block.dst_mac) : null,
        description: block.subscription.description,
        data_set_ref: block.data_set_ref,
        conf_rev: block.conf_rev,
        ied_name: block.ied_name,
        ld_inst: block.ld_inst,
        ln_name: block.ln_name,
        dataset_entries: block.subscription.dataset_entries,
      },
    );
  }
}

async function batchSetEnabled(enabled: boolean) {
  const targets = blocks.value.filter((item) =>
    checkedKeys.value.includes(item.key),
  );
  if (!targets.length) return;
  applying.value = true;
  try {
    for (const block of targets) await setBlockEnabled(block, enabled);
    ElMessage.success(
      enabled
        ? t("goose.batchEnableResult", { count: targets.length })
        : t("goose.batchDisableResult", { count: targets.length }),
    );
    await loadBlocks(false);
  } finally {
    applying.value = false;
  }
}

async function loadHistory(force = true) {
  const block = selected.value;
  if (!props.channelId || block?.kind !== "subscriber" || !block.receiver_id)
    return;
  const revision = block.subscription?.message_count || 0;
  if (!force && revision === historyKnownRevision) return;

  const requestId = ++historyRequestId;
  const requestedKey = block.key;
  const items = await getGooseSubscriptionHistory(
    props.channelId,
    block.receiver_id,
    block.go_cb_ref,
    200,
  );
  if (requestId !== historyRequestId || selected.value?.key !== requestedKey)
    return;

  historyKnownRevision = revision;
  history.value = items;
  const selectedReceivedAt = selectedHistory.value?.received_at;
  selectedHistory.value =
    items.find((item) => item.received_at === selectedReceivedAt) ||
    items[0] ||
    null;
}

function handleTabChange(tab: string | number) {
  if (tab === "history") void loadHistory(true);
}

function handleHistoryCurrentChange(row: GooseMessageHistoryItem | null) {
  // Replacing the polled table data briefly emits null. Keep the user's
  // selection and let current-row-key bind it to the refreshed row object.
  if (row) selectedHistory.value = row;
}

function schedule() {
  if (timer) clearTimeout(timer);
  timer = null;
  if (!active || !autoRefresh.value || !props.channelId) return;
  timer = setTimeout(() => void loadBlocks(false), pollInterval.value);
}

onActivated(() => {
  active = true;
  schedule();
});
onDeactivated(() => {
  active = false;
  if (timer) clearTimeout(timer);
});
onUnmounted(() => {
  active = false;
  if (timer) clearTimeout(timer);
});
</script>

<style scoped lang="scss">
.goose-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  border-radius: 4px;
  background: var(--panel-bg);
}
.manager-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-subtle);
}
.manager-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 700;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #5d6876;
  font-size: 13px;
}
.manager-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.manager-body > .el-empty {
  width: 100%;
}
.workspace {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}
.workspace-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}
:deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
:deep(.el-tab-pane) {
  height: 100%;
  overflow: auto;
}
.latest-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
}
.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 18px;
  padding: 9px 11px;
  border: 1px solid var(--border-color);
  background: var(--bg-muted);
  font-size: 13px;
}
.history-pane {
  display: grid;
  grid-template-columns: 390px minmax(0, 1fr);
  height: 100%;
  min-height: 0;
}
.history-detail {
  display: flex;
  flex-direction: column;
  gap: 9px;
  min-width: 0;
  padding-left: 10px;
}
@container (max-width: 900px) {
  .manager-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }
  .header-actions {
    flex-wrap: wrap;
  }
  .manager-body {
    flex-direction: column;
    overflow: auto;
  }
  .history-pane {
    grid-template-columns: 1fr;
    grid-template-rows: 240px minmax(300px, 1fr);
  }
}
</style>
