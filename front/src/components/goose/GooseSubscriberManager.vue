<template>
  <div class="goose-workbench">
    <header class="manager-header">
      <h3>GOOSE 管理</h3>
      <div class="header-actions">
        <span>自动刷新</span>
        <el-switch v-model="autoRefresh" />
        <el-select v-model="pollInterval" :disabled="!autoRefresh" style="width: 90px">
          <el-option :value="1000" label="1 s" />
          <el-option :value="2000" label="2 s" />
          <el-option :value="5000" label="5 s" />
        </el-select>
        <el-button :icon="Refresh" :loading="loading" @click="loadBlocks">刷新</el-button>
        <el-button
          v-if="selected?.kind === 'publisher'"
          type="primary"
          :disabled="!selected.publisher?.is_running"
          @click="publishSelected"
        >立即发布</el-button>
        <el-button v-if="selected" type="danger" plain @click="deleteSelected">
          删除控制块
        </el-button>
        <el-button @click="batchMode = !batchMode">{{
          batchMode ? "退出批量" : "批量模式"
        }}</el-button>
        <template v-if="batchMode">
          <el-button
            type="success"
            :disabled="!checkedKeys.length"
            @click="batchSetEnabled(true)"
            >批量使能</el-button
          >
          <el-button
            type="warning"
            :disabled="!checkedKeys.length"
            @click="batchSetEnabled(false)"
            >批量禁用</el-button
          >
        </template>
      </div>
    </header>

    <main class="manager-body" v-loading="loading && !blocks.length">
      <el-empty
        v-if="!loading && !blocks.length"
        description="没有 GOOSE 发布或订阅控制块"
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
          <el-empty v-if="!selected" description="从左侧选择一个 GOOSE 控制块" />
          <el-tabs
            v-else
            v-model="activeTab"
            class="workspace-tabs"
            @tab-change="handleTabChange"
          >
            <el-tab-pane label="属性配置" name="attributes">
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
              :label="selected.kind === 'publisher' ? '当前 GOOSE 数据' : '最近 GOOSE 数据'"
              name="latest"
            >
              <div class="latest-pane">
                <div class="summary">
                  <el-tag :type="selected.kind === 'publisher' ? 'primary' : 'success'">
                    {{ selected.kind === "publisher" ? "发布器" : "订阅器" }}
                  </el-tag>
                  <span v-if="selected.kind === 'subscriber'"
                    >时间：{{ formatGooseTime(selected.last_update) }}</span
                  >
                  <span>状态号：{{ selected.st_num }}</span>
                  <span>顺序号：{{ selected.sq_num }}</span>
                  <span>数据集：{{ selected.data_set_ref || "-" }}</span>
                  <span>值：{{ selected.data_values.length }}</span>
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
              :label="`GOOSE 数据历史 (${selected.subscription?.history_count || 0})`"
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
                  <el-table-column type="index" label="#" width="48" align="center" />
                  <el-table-column prop="received_at" label="接收时间" min-width="185" sortable>
                    <template #default="{ row }">{{
                      formatGooseTime(row.received_at)
                    }}</template>
                  </el-table-column>
                  <el-table-column prop="st_num" label="状态号" width="75" />
                  <el-table-column prop="sq_num" label="顺序号" width="75" />
                  <el-table-column prop="value_count" label="数据项" width="70" />
                  <el-table-column prop="changed_count" label="变化项" width="70" />
                </el-table>
                <div class="history-detail">
                  <div v-if="selectedHistory" class="summary">
                    <span>时间：{{ formatGooseTime(selectedHistory.received_at) }}</span>
                    <span>数据集：{{ selectedHistory.data_set_ref || "-" }}</span>
                    <span>状态号：{{ selectedHistory.st_num }}</span>
                    <span>顺序号：{{ selectedHistory.sq_num }}</span>
                    <span>数据项：{{ selectedHistory.value_count }}</span>
                    <span>变化项：{{ selectedHistory.changed_count }}</span>
                  </div>
                  <GooseDataSetTable :values="selectedHistory?.data_values || []" />
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
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Refresh } from '@element-plus/icons-vue';
import {
  getGoosePublishers,
  getGooseReceivers,
  getGooseNetworkInterfaces,
  getGooseSubscriptionHistory,
  startGoosePublisher,
  stopGoosePublisher,
  publishGooseNow,
  updateGoosePublisherEntry,
  deleteGoosePublisher,
  removeGooseSubscription,
  stopGooseReceiver,
  updateGoosePublisher,
  updateGooseReceiver,
  updateGooseSubscription,
  type GooseMessageHistoryItem,
} from '@/api/gooseApi';
import { getIEC61850Structure, type IEC61850DataSetInfo } from '@/api/channelApi';
import GooseBlockTreePanel from './GooseBlockTreePanel.vue';
import GooseControlPanel from './GooseControlPanel.vue';
import GooseDataSetTable from './GooseDataSetTable.vue';
import GoosePublisherControlPanel from './GoosePublisherControlPanel.vue';
import { flattenGooseBlocks, formatGooseTime, type GooseBlockItem } from './gooseWorkbench';

const props = defineProps<{ channelId?: number }>();
const publishers = ref<Awaited<ReturnType<typeof getGoosePublishers>>>([]);
const receivers = ref<Awaited<ReturnType<typeof getGooseReceivers>>>([]);
const networkInterfaces = ref<Awaited<ReturnType<typeof getGooseNetworkInterfaces>>>([]);
const dataSets = ref<IEC61850DataSetInfo[]>([]);
const blocks = computed(() => flattenGooseBlocks(publishers.value, receivers.value));
const selectedKey = ref('');
const selected = computed(() => blocks.value.find((item) => item.key === selectedKey.value) || null);
const activeTab = ref('attributes');
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
    selectedKey.value = '';
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
    if (selectedKey.value && !selected.value) selectedKey.value = '';
    if (activeTab.value === 'history' && selected.value?.kind === 'subscriber') {
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
    );
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
  if (block.kind === 'publisher' && activeTab.value === 'history') activeTab.value = 'attributes';
  if (activeTab.value === 'history') void loadHistory(true);
}

async function publishSelected() {
  const block = selected.value;
  if (!props.channelId || block?.kind !== 'publisher' || !block.publisher) return;
  try {
    await publishGooseNow(props.channelId, block.publisher.id);
    ElMessage.success('GOOSE 报文已发布');
    await loadBlocks(false);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'GOOSE 发布失败');
  }
}

async function updatePublisherDataValue(payload: { index: number; value: string | number | boolean }) {
  const block = selected.value;
  if (block?.kind !== 'publisher' || !block.publisher) return;
  updatingEntryIndex.value = payload.index;
  try {
    await updateGoosePublisherEntry(block.publisher.id, payload.index, payload.value);
    await loadBlocks(false);
    ElMessage.success('数据集值已更新');
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '数据集值更新失败');
    await loadBlocks(false);
  } finally {
    updatingEntryIndex.value = null;
  }
}

async function deleteSelected() {
  const block = selected.value;
  if (!props.channelId || !block) return;
  try {
    await ElMessageBox.confirm(`确定删除 ${block.display_name}？`, '删除 GOOSE 控制块', {
      type: 'warning',
    });
    if (block.kind === 'publisher' && block.publisher) {
      await deleteGoosePublisher(props.channelId, block.publisher.id);
    } else if (block.receiver_id) {
      const receiver = receivers.value.find((item) => item.id === block.receiver_id);
      if (receiver?.is_running) await stopGooseReceiver(props.channelId, receiver.id);
      await removeGooseSubscription(block.receiver_id, block.go_cb_ref);
    }
    selectedKey.value = '';
    await loadBlocks(false);
    ElMessage.success('GOOSE 控制块已删除');
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error instanceof Error ? error.message : '删除失败');
    }
  }
}

function parseMac(value: string): number[] | null {
  if (!value.trim()) return null;
  const parts = value.split(/[:-]/);
  if (parts.length !== 6 || parts.some((item) => !/^[0-9a-fA-F]{2}$/.test(item))) {
    throw new Error('目标MAC地址格式错误');
  }
  return parts.map((item) => Number.parseInt(item, 16));
}

function defaultGooseMulticastMac(appId: number): string {
  const normalized = Number(appId || 0) & 0xffff;
  const high = ((normalized >> 8) & 0xff).toString(16).toUpperCase().padStart(2, '0');
  const low = (normalized & 0xff).toString(16).toUpperCase().padStart(2, '0');
  return `01:0C:CD:01:${high}:${low}`;
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
  if (!props.channelId || block?.kind !== 'publisher' || !block.publisher) return;
  applying.value = true;
  const publisherId = block.publisher.id;
  try {
    if (block.publisher.is_running) await stopGoosePublisher(props.channelId, publisherId);
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
    if (form.enabled) await startGoosePublisher(props.channelId, publisherId);
    ElMessage.success(
      form.dst_mac
        ? 'GOOSE 发布配置已应用'
        : `GOOSE 发布配置已应用，目标地址留空，自动使用组播地址 ${defaultGooseMulticastMac(form.app_id)}`
    );
    await loadBlocks(false);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '发布配置应用失败');
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
  if (!props.channelId || block?.kind !== 'subscriber' || !block.subscription || !block.receiver_id) return;
  applying.value = true;
  try {
    const receiver = receivers.value.find((item) => item.id === block.receiver_id);
    if (receiver && form.interface && form.interface !== receiver.interface) {
      if (receiver.is_running) await stopGooseReceiver(props.channelId, receiver.id);
      await updateGooseReceiver(props.channelId, receiver.id, {
        interface: form.interface,
        name: receiver.name || 'default',
        description: receiver.description || '',
        auto_start: receiver.auto_start || false,
      });
    }
    await updateGooseSubscription(props.channelId, block.receiver_id, block.go_cb_ref, {
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
    });
    ElMessage.success('GOOSE 订阅配置已应用');
    await loadBlocks(false);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '订阅配置应用失败');
  } finally {
    applying.value = false;
  }
}

async function setBlockEnabled(block: GooseBlockItem, enabled: boolean) {
  if (!props.channelId) return;
  if (block.kind === 'publisher' && block.publisher) {
    if (enabled) await startGoosePublisher(props.channelId, block.publisher.id);
    else await stopGoosePublisher(props.channelId, block.publisher.id);
    return;
  }
  if (block.subscription && block.receiver_id) {
    await updateGooseSubscription(props.channelId, block.receiver_id, block.go_cb_ref, {
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
    });
  }
}

async function batchSetEnabled(enabled: boolean) {
  const targets = blocks.value.filter((item) => checkedKeys.value.includes(item.key));
  if (!targets.length) return;
  applying.value = true;
  try {
    for (const block of targets) await setBlockEnabled(block, enabled);
    ElMessage.success(`已${enabled ? '使能' : '禁用'} ${targets.length} 个 GOOSE 控制块`);
    await loadBlocks(false);
  } finally {
    applying.value = false;
  }
}

async function loadHistory(force = true) {
  const block = selected.value;
  if (!props.channelId || block?.kind !== 'subscriber' || !block.receiver_id) return;
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
  if (requestId !== historyRequestId || selected.value?.key !== requestedKey) return;

  historyKnownRevision = revision;
  history.value = items;
  const selectedReceivedAt = selectedHistory.value?.received_at;
  selectedHistory.value =
    items.find((item) => item.received_at === selectedReceivedAt) || items[0] || null;
}

function handleTabChange(tab: string | number) {
  if (tab === 'history') void loadHistory(true);
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
  background: #fff;
}
.manager-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #d8dde5;
  background: #fbfcfe;
}
.manager-header h3 {
  margin: 0;
  color: #263241;
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
  border: 1px solid #d8dde5;
  background: #f6f8fb;
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
@media (max-width: 900px) {
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
