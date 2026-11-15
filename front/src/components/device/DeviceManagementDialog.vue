<template>
  <el-dialog
    v-model="visible"
    :title="t('deviceManagement.title')"
    width="min(1480px, 96vw)"
    top="5vh"
    class="device-management-dialog"
    destroy-on-close
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
  >
    <template #header>
      <div class="management-heading">
        <el-icon><Operation /></el-icon>
        <h2>{{ t("deviceManagement.title") }}</h2>
        <span>{{ t("deviceManagement.subtitle") }}</span>
      </div>
    </template>

    <div v-loading="loading" class="management-layout">
      <aside class="management-sidebar">
        <el-input
          v-model="treeSearch"
          clearable
          :prefix-icon="Search"
          :placeholder="t('deviceManagement.treeSearch')"
        />
        <div class="tree-caption">{{ t("deviceManagement.tree") }}</div>
        <el-scrollbar class="management-tree-scroll">
          <el-tree
            ref="treeRef"
            :data="treeData"
            node-key="key"
            :props="{ label: 'label', children: 'children' }"
            :default-expanded-keys="expandedKeys"
            :current-node-key="scopeKey"
            :filter-node-method="filterTreeNode"
            :expand-on-click-node="false"
            highlight-current
            :aria-label="t('deviceManagement.tree')"
            @node-click="selectScope"
          >
            <template #default="{ data }">
              <div class="management-tree-node" :title="data.label">
                <el-icon
                  :class="
                    data.kind === 'device'
                      ? deviceState(rowById.get(data.deviceIds[0]))
                      : ''
                  "
                >
                  <Monitor v-if="data.kind === 'device'" /><Folder v-else />
                </el-icon>
                <span class="tree-node-label">{{ data.label }}</span>
                <i
                  v-if="data.kind === 'device'"
                  class="status-dot"
                  :class="deviceState(rowById.get(data.deviceIds[0]))"
                />
                <small v-else>{{ data.deviceIds.length }}</small>
              </div>
            </template>
          </el-tree>
        </el-scrollbar>
        <div class="management-legend">
          <span v-for="state in ['on', 'off', 'error']" :key="state"
            ><i class="status-dot" :class="state" />{{
              t(`deviceManagement.${state}`)
            }}</span
          >
        </div>
      </aside>

      <section class="management-main">
        <el-alert
          v-if="loadError"
          :title="loadError"
          type="error"
          :closable="false"
          show-icon
        >
          <el-button
            link
            type="primary"
            :disabled="busy"
            @click="loadDevices"
            >{{ t("common.refresh") }}</el-button
          >
        </el-alert>
        <div class="management-list">
          <div class="management-filters">
            <div
              class="management-tabs"
              role="group"
              :aria-label="t('deviceManagement.statusFilter')"
            >
              <button
                v-for="tab in statusTabs"
                :key="tab.key"
                type="button"
                :class="{ active: statusFilter === tab.key }"
                :disabled="busy"
                :aria-pressed="statusFilter === tab.key"
                @click="statusFilter = tab.key"
              >
                {{ t(`deviceManagement.${tab.key}`) }}
                <span>{{ tab.count }}</span>
              </button>
            </div>
            <div class="management-search">
              <el-select
                v-model="protocolFilter"
                :disabled="busy"
                :aria-label="t('deviceManagement.protocol')"
              >
                <el-option
                  :label="t('deviceManagement.allProtocols')"
                  :value="-1"
                />
                <el-option
                  v-for="protocol in protocols"
                  :key="protocol.value"
                  :value="protocol.value"
                  :label="protocol.label"
                />
              </el-select>
              <el-input
                v-model="search"
                clearable
                :disabled="busy"
                :prefix-icon="Search"
                :placeholder="t('deviceManagement.search')"
              />
              <el-tooltip :content="t('common.refresh')"
                ><el-button
                  :icon="Refresh"
                  :aria-label="t('common.refresh')"
                  :disabled="busy || refreshing"
                  @click="loadDevices"
              /></el-tooltip>
            </div>
          </div>

          <div class="management-batch">
            <strong>{{
              t("deviceManagement.selected", { count: selected.length })
            }}</strong>
            <el-button
              link
              :disabled="busy || !selected.length"
              @click="clearSelection"
              >{{ t("common.clear") }}</el-button
            >
            <div class="batch-actions">
              <el-button
                v-for="action in actions"
                :key="action.key"
                :icon="action.icon"
                :type="
                  action.key === 'startSimulation'
                    ? 'primary'
                    : action.key === 'stop'
                      ? 'danger'
                      : 'default'
                "
                :plain="action.key === 'stop'"
                :disabled="controlsDisabled || !selected.length"
                :loading="activeOperation === action.key"
                @click="executeOperation(action.key, selected)"
              >
                {{ t(`deviceManagement.${action.key}`) }}
              </el-button>
            </div>
            <span class="batch-hint">{{
              busy
                ? t("deviceManagement.progress", {
                    done: completed,
                    total: operationTotal,
                  })
                : t("deviceManagement.selectionOnly")
            }}</span>
          </div>

          <el-alert
            v-if="operationSummary"
            :title="operationSummary"
            :type="operationFailed ? 'warning' : 'success'"
            show-icon
            closable
            @close="operationSummary = ''"
          />

          <el-table
            ref="tableRef"
            :data="pagedRows"
            row-key="id"
            height="100%"
            class="management-table"
            :empty-text="
              loading ? t('common.loading') : t('deviceManagement.empty')
            "
            @selection-change="onSelectionChange"
          >
            <el-table-column
              type="selection"
              width="44"
              reserve-selection
              :selectable="() => !controlsDisabled"
            />
            <el-table-column
              :label="t('deviceManagement.name')"
              min-width="215"
            >
              <template #default="{ row }">
                <div class="device-name-cell">
                  <span class="device-chip"
                    ><el-icon><Monitor /></el-icon
                  ></span>
                  <div>
                    <strong>{{ row.name }}</strong
                    ><small>{{ row.code }} · {{ row.groupName }}</small>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('deviceManagement.protocol')"
              min-width="115"
            >
              <template #default="{ row }">{{
                protocolName(row.protocol_type)
              }}</template>
            </el-table-column>
            <el-table-column
              :label="t('deviceManagement.address')"
              min-width="160"
              show-overflow-tooltip
            >
              <template #default="{ row }"
                ><span class="device-address">{{
                  deviceAddress(row)
                }}</span></template
              >
            </el-table-column>
            <el-table-column
              :label="t('deviceManagement.deviceStatus')"
              min-width="105"
            >
              <template #default="{ row }">
                <el-tooltip
                  :content="deviceError(row)"
                  :disabled="!deviceError(row)"
                >
                  <span class="device-status" :class="deviceState(row)"
                    ><i class="status-dot" :class="deviceState(row)" />{{
                      stateLabel(row)
                    }}</span
                  >
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('deviceManagement.simulationStatus')"
              min-width="108"
            >
              <template #default="{ row }">
                <span v-if="row.runtime?.simulating" class="simulation-badge"
                  ><el-icon><DataLine /></el-icon
                  >{{ t("deviceManagement.simulating") }}</span
                >
                <span v-else class="muted">{{
                  t("deviceManagement.idle")
                }}</span>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('deviceManagement.quickActions')"
              min-width="225"
              fixed="right"
            >
              <template #default="{ row }">
                <div class="row-actions">
                  <el-tooltip
                    :content="
                      actionHint(row, row.runtime?.running ? 'stop' : 'start')
                    "
                    :disabled="
                      !actionHint(row, row.runtime?.running ? 'stop' : 'start')
                    "
                  >
                    <span
                      ><el-button
                        link
                        type="primary"
                        :icon="SwitchButton"
                        :loading="pendingIds.has(row.id)"
                        :disabled="
                          controlsDisabled ||
                          !!deviceOperationReason(
                            row,
                            row.runtime?.running ? 'stop' : 'start',
                          )
                        "
                        @click="
                          executeOperation(
                            row.runtime?.running ? 'stop' : 'start',
                            [row],
                          )
                        "
                        >{{
                          t(
                            row.runtime?.running
                              ? "deviceManagement.powerOff"
                              : "deviceManagement.powerOn",
                          )
                        }}</el-button
                      ></span
                    >
                  </el-tooltip>
                  <span class="action-divider" />
                  <el-tooltip
                    :content="
                      actionHint(
                        row,
                        row.runtime?.simulating
                          ? 'stopSimulation'
                          : 'startSimulation',
                      )
                    "
                    :disabled="
                      !actionHint(
                        row,
                        row.runtime?.simulating
                          ? 'stopSimulation'
                          : 'startSimulation',
                      )
                    "
                  >
                    <span
                      ><el-button
                        link
                        type="primary"
                        :icon="row.runtime?.simulating ? VideoPause : VideoPlay"
                        :disabled="
                          controlsDisabled ||
                          !!deviceOperationReason(
                            row,
                            row.runtime?.simulating
                              ? 'stopSimulation'
                              : 'startSimulation',
                          )
                        "
                        @click="
                          executeOperation(
                            row.runtime?.simulating
                              ? 'stopSimulation'
                              : 'startSimulation',
                            [row],
                          )
                        "
                        >{{
                          t(
                            row.runtime?.simulating
                              ? "deviceManagement.stopSimulation"
                              : "deviceManagement.startSimulation",
                          )
                        }}</el-button
                      ></span
                    >
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div class="management-pagination">
            <span>{{
              t("deviceManagement.total", { count: filteredRows.length })
            }}</span>
            <el-pagination
              v-model:current-page="page"
              :page-size="pageSize"
              :total="filteredRows.length"
              layout="prev, pager, next"
              :disabled="busy"
              small
            />
          </div>
        </div>
        <div
          v-if="operationDetails.length"
          class="operation-details"
          aria-live="polite"
        >
          <details>
            <summary>
              {{
                t("deviceManagement.resultDetails", {
                  count: operationDetails.length,
                })
              }}
            </summary>
            <ul>
              <li v-for="(detail, index) in operationDetails" :key="index">
                {{ detail }}
              </li>
            </ul>
          </details>
        </div>
      </section>
    </div>
    <template #footer>
      <div class="management-footer">
        <span
          ><el-icon><InfoFilled /></el-icon
          >{{ t("deviceManagement.note") }}</span
        ><el-button :disabled="busy" @click="visible = false">{{
          t("common.close")
        }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  DataLine,
  Folder,
  InfoFilled,
  Monitor,
  Operation,
  Refresh,
  Search,
  SwitchButton,
  VideoPause,
  VideoPlay,
} from "@element-plus/icons-vue";
import type { TableInstance, TreeInstance } from "element-plus";
import { getChannelList, getProtocolConfig } from "@/api/channelApi";
import {
  getDeviceGroupTree,
  type DeviceGroupTreeResponse,
} from "@/api/deviceGroupApi";
import {
  controlManagedDevice,
  getDeviceManagementStatus,
} from "@/api/deviceManagementApi";
import { getApiErrorMessage } from "@/api/http";
import {
  buildManagementTree,
  deviceAddress,
  deviceOperationReason,
  runDeviceOperations,
  type DeviceOperation,
  type DeviceRuntimeStatus,
  type ManagedDevice,
  type ManagementTreeNode,
} from "@/utils/deviceManagement";
import type { ChannelInfo, ProtocolOption } from "@/types/channel";
import { useSidebarRefresh } from "@/composables/useSidebarRefresh";

const visible = defineModel<boolean>("visible", { default: false });
const { t } = useI18n();
const tableRef = ref<TableInstance>();
const treeRef = ref<TreeInstance>();
const channels = ref<ChannelInfo[]>([]);
const groups = ref<DeviceGroupTreeResponse>({ groups: [], ungrouped: [] });
const protocols = ref<ProtocolOption[]>([]);
const statuses = ref<DeviceRuntimeStatus[]>([]);
const operationErrors = ref<Record<number, string>>({});
const selected = ref<ManagedDevice[]>([]);
const scopeKey = ref("all");
const treeSearch = ref("");
const search = ref("");
const protocolFilter = ref(-1);
const statusFilter = ref("all");
const page = ref(1);
const pageSize = 8;
const loading = ref(false);
const refreshing = ref(false);
const loadError = ref("");
const statusFresh = ref(false);
const activeOperation = ref<DeviceOperation | null>(null);
const pendingIds = ref(new Set<number>());
const completed = ref(0);
const operationTotal = ref(0);
const operationSummary = ref("");
const operationFailed = ref(false);
const operationDetails = ref<string[]>([]);
const busy = computed(() => activeOperation.value !== null);
const controlsDisabled = computed(
  () => busy.value || loading.value || refreshing.value || !statusFresh.value,
);
let generation = 0;
let disposed = false;
let pollTimer: ReturnType<typeof setTimeout> | undefined;
const actions: { key: DeviceOperation; icon: typeof SwitchButton }[] = [
  { key: "start", icon: SwitchButton },
  { key: "stop", icon: SwitchButton },
  { key: "startSimulation", icon: VideoPlay },
  { key: "stopSimulation", icon: VideoPause },
];

const treeData = computed<ManagementTreeNode[]>(() => [
  {
    key: "all",
    label: t("deviceManagement.all"),
    kind: "all",
    deviceIds: channels.value.map((c) => c.id),
    children: buildManagementTree(
      groups.value,
      channels.value,
      t("deviceManagement.ungrouped"),
    ),
  },
]);
const expandedKeys = computed(() => [
  "all",
  ...(treeData.value[0].children || []).map((n) => n.key),
]);
const rows = computed<ManagedDevice[]>(() => {
  const groupNames = new Map<number, string>();
  const visit = (nodes: ManagementTreeNode[]) =>
    nodes.forEach((n) => {
      if (n.kind === "group")
        n.deviceIds.forEach((id) => groupNames.set(id, n.label));
      if (n.children) visit(n.children);
    });
  visit(treeData.value);
  const runtime = new Map(statuses.value.map((s) => [s.channel_id, s]));
  return channels.value.map((c) => ({
    ...c,
    groupName: groupNames.get(c.id) || t("deviceManagement.ungrouped"),
    runtime: runtime.get(c.id),
  }));
});
const rowById = computed(() => new Map(rows.value.map((r) => [r.id, r])));
const scopedRows = computed(() => {
  let ids: number[] | undefined;
  const visit = (nodes: ManagementTreeNode[]) =>
    nodes.forEach((n) => {
      if (n.key === scopeKey.value) ids = n.deviceIds;
      if (n.children) visit(n.children);
    });
  visit(treeData.value);
  const allowed = new Set(ids || treeData.value[0].deviceIds);
  return rows.value.filter((r) => allowed.has(r.id));
});
const statusTabs = computed(() =>
  ["all", "on", "off", "error"].map((key) => ({
    key,
    count:
      key === "all"
        ? scopedRows.value.length
        : scopedRows.value.filter((r) => deviceState(r) === key).length,
  })),
);
const filteredRows = computed(() =>
  scopedRows.value.filter(
    (r) =>
      (statusFilter.value === "all" || deviceState(r) === statusFilter.value) &&
      (protocolFilter.value === -1 ||
        r.protocol_type === protocolFilter.value) &&
      `${r.name} ${r.code} ${deviceAddress(r)}`
        .toLowerCase()
        .includes(search.value.trim().toLowerCase()),
  ),
);
const pagedRows = computed(() =>
  filteredRows.value.slice((page.value - 1) * pageSize, page.value * pageSize),
);
function protocolName(value: number) {
  return protocols.value.find((p) => p.value === value)?.label || String(value);
}
function deviceError(row?: ManagedDevice) {
  if (!statusFresh.value) return t("deviceManagement.statusUnavailable");
  return row ? operationErrors.value[row.id] || row.runtime?.error || "" : "";
}
function deviceState(row?: ManagedDevice) {
  if (!statusFresh.value || row?.runtime?.status_available === false)
    return "error";
  if (deviceError(row)) return "error";
  return row?.runtime?.running ? "on" : "off";
}
function stateLabel(row: ManagedDevice) {
  if (!statusFresh.value || row.runtime?.status_available === false)
    return t("deviceManagement.unknown");
  return t(`deviceManagement.${deviceState(row)}`);
}
function actionHint(row: ManagedDevice, operation: DeviceOperation) {
  const reason = deviceOperationReason(row, operation);
  return reason ? t(`deviceManagement.${reason}`) : "";
}
function filterTreeNode(value: string, data: ManagementTreeNode) {
  if (!value.trim()) return true;
  const row =
    data.kind === "device" ? rowById.value.get(data.deviceIds[0]) : undefined;
  return `${data.label} ${row?.code || ""} ${row ? deviceAddress(row) : ""}`
    .toLowerCase()
    .includes(value.trim().toLowerCase());
}
function selectScope(node: ManagementTreeNode) {
  if (!busy.value) scopeKey.value = node.key;
}
function clearSelection() {
  tableRef.value?.clearSelection();
  selected.value = [];
}
function onSelectionChange(selection: ManagedDevice[]) {
  selected.value = selection;
}

async function loadDevices() {
  if (
    disposed ||
    !visible.value ||
    busy.value ||
    loading.value ||
    refreshing.value
  )
    return;
  const epoch = generation;
  loading.value = true;
  try {
    const [channelData, groupData, statusData, config] = await Promise.all([
      getChannelList(),
      getDeviceGroupTree(),
      getDeviceManagementStatus(),
      getProtocolConfig(),
    ]);
    if (epoch !== generation) return;
    clearSelection();
    channels.value = channelData;
    groups.value = groupData;
    statuses.value = statusData;
    protocols.value = config.protocols;
    loadError.value = "";
    statusFresh.value = true;
    await nextTick();
    treeRef.value?.filter(treeSearch.value);
  } catch (error) {
    if (epoch === generation) {
      loadError.value = getApiErrorMessage(error);
      statusFresh.value = false;
    }
  } finally {
    if (epoch === generation) loading.value = false;
  }
}
async function refreshStatuses() {
  if (disposed || !visible.value || loading.value || refreshing.value) return;
  const epoch = generation;
  refreshing.value = true;
  try {
    const result = await getDeviceManagementStatus();
    if (epoch === generation) {
      statuses.value = result;
      statusFresh.value = true;
      loadError.value = "";
    }
  } catch (error) {
    if (epoch === generation) {
      statusFresh.value = false;
      loadError.value = getApiErrorMessage(error);
    }
  } finally {
    if (epoch === generation) refreshing.value = false;
  }
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (disposed || !visible.value) return;
  pollTimer = setTimeout(async () => {
    if (!busy.value && !document.hidden) await refreshStatuses();
    schedulePoll();
  }, 5000);
}
async function executeOperation(
  operation: DeviceOperation,
  targets: ManagedDevice[],
) {
  if (controlsDisabled.value || !targets.length) return;
  activeOperation.value = operation;
  completed.value = 0;
  operationTotal.value = targets.length;
  operationSummary.value = "";
  operationDetails.value = [];
  let success = 0,
    skipped = 0,
    failed = 0;
  try {
    // Resolve reserved selections against current data, never execute stale row state.
    const current = targets
      .map((r) => rowById.value.get(r.id))
      .filter((r): r is ManagedDevice => !!r);
    skipped += targets.length - current.length;
    await runDeviceOperations(current, async (row) => {
      const reason = deviceOperationReason(row, operation);
      if (reason) {
        skipped++;
        operationDetails.value.push(
          `${row.name}：${t("deviceManagement.skipped")} · ${t(`deviceManagement.${reason}`)}`,
        );
      } else {
        pendingIds.value.add(row.id);
        try {
          await controlManagedDevice(row, operation);
          delete operationErrors.value[row.id];
          success++;
        } catch (error) {
          failed++;
          const message = getApiErrorMessage(error);
          operationErrors.value[row.id] = message;
          operationDetails.value.push(`${row.name}：${message}`);
        } finally {
          pendingIds.value.delete(row.id);
        }
      }
      completed.value++;
    });
    operationFailed.value = failed > 0;
    operationSummary.value = t("deviceManagement.result", {
      action: t(`deviceManagement.${operation}`),
      success,
      skipped,
      failed,
    });
    await refreshStatuses();
  } finally {
    activeOperation.value = null;
  }
}

watch([scopeKey, search, protocolFilter, statusFilter], () => {
  page.value = 1;
  clearSelection();
});
watch(treeSearch, (value) => treeRef.value?.filter(value));
watch(
  () => filteredRows.value.length,
  (count) => {
    page.value = Math.max(1, Math.min(page.value, Math.ceil(count / pageSize)));
  },
);
const { refreshCounter } = useSidebarRefresh();
watch(refreshCounter, () => {
  if (visible.value && !busy.value) void loadDevices();
});
watch(
  visible,
  async (open) => {
    generation++;
    clearTimeout(pollTimer);
    loading.value = false;
    refreshing.value = false;
    if (open) {
      statusFresh.value = false;
      operationSummary.value = "";
      operationDetails.value = [];
      operationErrors.value = {};
      await loadDevices();
      if (visible.value) schedulePoll();
    }
  },
  { immediate: true },
);
onUnmounted(() => {
  disposed = true;
  generation++;
  clearTimeout(pollTimer);
});
</script>

<style lang="scss">
.device-management-dialog {
  --management-accent: #5265e8;
  --management-soft: color-mix(
    in srgb,
    var(--management-accent) 8%,
    var(--panel-bg)
  );
  padding: 0;
  border-radius: 10px;
  overflow: hidden;
  background: var(--panel-bg);
  color: var(--text-primary);
  .el-dialog__header {
    margin: 0;
    padding: 20px 24px;
    border-bottom: 1px solid var(--border-color);
  }
  .el-dialog__headerbtn {
    top: 10px;
  }
  .el-dialog__body {
    padding: 0;
  }
  .el-dialog__footer {
    padding: 14px 24px;
    border-top: 1px solid var(--border-color);
  }
  .management-heading {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-right: 24px;
    > .el-icon {
      font-size: 21px;
      color: var(--management-accent);
    }
    h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }
    > span {
      font-size: 12px;
      color: var(--text-secondary);
    }
  }
  .management-layout {
    display: flex;
    height: min(720px, 72vh);
    min-height: 360px;
  }
  .management-sidebar {
    display: flex;
    flex-direction: column;
    gap: 16px;
    width: 232px;
    flex-shrink: 0;
    padding: 18px 14px;
    border-right: 1px solid var(--border-color);
    background: var(--bg-subtle);
  }
  .tree-caption {
    font-size: 12px;
    color: var(--text-secondary);
    padding: 0 8px;
  }
  .management-tree-scroll {
    flex: 1;
    min-height: 0;
  }
  .el-tree {
    background: transparent;
    --el-tree-node-hover-bg-color: var(--item-hover-bg);
    color: var(--text-primary);
  }
  .el-tree-node__content {
    height: 38px;
    border-radius: 5px;
    margin-bottom: 3px;
  }
  .el-tree-node.is-current > .el-tree-node__content {
    background: var(--management-soft);
    color: var(--management-accent);
  }
  .management-tree-node {
    display: flex;
    align-items: center;
    gap: 7px;
    flex: 1;
    min-width: 0;
    padding-right: 8px;
    font-size: 12px;
    .tree-node-label {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    small {
      margin-left: auto;
      color: var(--text-secondary);
    }
    .status-dot {
      margin-left: auto;
      flex-shrink: 0;
    }
  }
  .status-dot {
    width: 5px;
    height: 5px;
    display: inline-block;
    border-radius: 50%;
    background: currentColor;
  }
  .on {
    color: var(--color-success);
  }
  .off {
    color: var(--text-secondary);
  }
  .error {
    color: var(--color-warning);
  }
  .management-legend {
    display: flex;
    gap: 12px;
    font-size: 10px;
    color: var(--text-secondary);
    span {
      display: flex;
      align-items: center;
      gap: 4px;
    }
  }
  .management-main {
    flex: 1;
    min-width: 0;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .management-list {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    overflow: hidden;
  }
  .management-filters {
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    flex-wrap: wrap;
  }
  .management-tabs {
    display: flex;
    gap: 16px;
    button {
      padding: 4px 0;
      border: 0;
      background: transparent;
      font: inherit;
      font-size: 12px;
      color: var(--text-secondary);
      cursor: pointer;
      white-space: nowrap;
    }
    button.active {
      color: var(--management-accent);
      font-weight: 600;
    }
    button:focus-visible {
      outline: 2px solid var(--management-accent);
      outline-offset: 3px;
    }
    button:disabled {
      cursor: default;
    }
    span {
      margin-left: 4px;
    }
  }
  .management-search {
    display: flex;
    align-items: center;
    gap: 8px;
    .el-select {
      width: 124px;
    }
    .el-input {
      width: 200px;
    }
  }
  .management-batch {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    padding: 10px 16px;
    background: var(--management-soft);
    border-block: 1px solid var(--border-color);
    font-size: 12px;
    > strong {
      color: var(--management-accent);
      font-weight: 500;
    }
    .el-button + .el-button {
      margin-left: 0;
    }
  }
  .batch-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .batch-hint {
    margin-left: auto;
    font-size: 11px;
    color: var(--text-secondary);
  }
  .management-table {
    flex: 1;
    min-height: 0;
    font-size: 12px;
    --el-table-header-bg-color: var(--bg-subtle);
    --el-table-border-color: var(--border-color);
    --el-table-text-color: var(--text-primary);
    --el-table-header-text-color: var(--text-secondary);
    th.el-table__cell {
      font-weight: 500;
      height: 38px;
    }
    td.el-table__cell {
      height: 54px;
      padding: 6px 0;
    }
    .el-table__inner-wrapper::before {
      display: none;
    }
  }
  .device-name-cell {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
    > div {
      min-width: 0;
    }
    strong,
    small {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    strong {
      font-weight: 500;
      font-size: 12px;
    }
    small {
      color: var(--text-secondary);
      font-size: 10px;
      margin-top: 2px;
    }
  }
  .device-chip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 5px;
    background: var(--bg-muted);
    color: var(--text-secondary);
    flex-shrink: 0;
    font-size: 15px;
  }
  .device-address {
    font-variant-numeric: tabular-nums;
    font-size: 11px;
    color: var(--text-secondary);
  }
  .device-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
  }
  .simulation-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 7px;
    border-radius: 4px;
    color: var(--management-accent);
    background: var(--management-soft);
    font-size: 11px;
  }
  .muted {
    color: var(--text-secondary);
    font-size: 11px;
  }
  .row-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
    .el-button {
      font-size: 12px;
    }
  }
  .action-divider {
    height: 12px;
    width: 1px;
    background: var(--border-color);
  }
  .management-pagination {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 16px;
    font-size: 11px;
    color: var(--text-secondary);
  }
  .management-footer {
    display: flex;
    align-items: center;
    gap: 16px;
    justify-content: space-between;
    > span {
      display: flex;
      align-items: center;
      gap: 7px;
      color: var(--text-secondary);
      font-size: 11px;
      text-align: left;
    }
  }
  .operation-details {
    font-size: 12px;
    color: var(--text-secondary);
    max-height: 100px;
    overflow: auto;
    summary {
      cursor: pointer;
    }
    ul {
      padding-left: 20px;
    }
    li {
      margin: 5px 0;
      overflow-wrap: anywhere;
    }
  }
  @media (max-width: 1100px) {
    .management-sidebar {
      width: 200px;
    }
    .management-search .el-input {
      width: 170px;
    }
    .batch-hint {
      display: none;
    }
  }
  @media (max-width: 720px) {
    .management-heading > span {
      display: none;
    }
    .management-sidebar {
      width: 165px;
      padding: 12px 8px;
    }
    .management-main {
      padding: 8px;
    }
    .management-search {
      flex-wrap: wrap;
    }
    .management-legend {
      flex-wrap: wrap;
      gap: 6px;
    }
    .management-footer > span {
      max-width: 80%;
    }
  }
}
</style>
