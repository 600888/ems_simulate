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
        <el-button @click="batchMode = !batchMode">{{ batchMode ? '退出批量' : '批量模式' }}</el-button>
        <template v-if="batchMode">
          <el-button type="success" :disabled="!checkedKeys.length" @click="batchSetEnabled(true)">批量使能</el-button>
          <el-button type="warning" :disabled="!checkedKeys.length" @click="batchSetEnabled(false)">批量禁用</el-button>
        </template>
      </div>
    </header>

    <main class="manager-body" v-loading="loading && !blocks.length">
      <el-empty v-if="!loading && !blocks.length" description="没有 GOOSE 发布或订阅控制块" />
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
          <el-tabs v-else v-model="activeTab" class="workspace-tabs" @tab-change="handleTabChange">
            <el-tab-pane label="属性配置" name="attributes">
              <GoosePublisherControlPanel
                v-if="selected.kind === 'publisher'"
                :block="selected"
                :loading="applying"
                :interfaces="networkInterfaces"
                @apply="applyPublisherConfig"
              />
              <GooseControlPanel
                v-else
                :block="selected"
                :loading="applying"
                :interfaces="networkInterfaces"
                @apply="applySubscriptionConfig"
              />
            </el-tab-pane>

            <el-tab-pane :label="selected.kind === 'publisher' ? '当前发布数据' : '最近 GOOSE 报文'" name="latest">
              <div class="latest-pane">
                <div class="summary">
                  <el-tag :type="selected.kind === 'publisher' ? 'primary' : 'success'">
                    {{ selected.kind === 'publisher' ? '发布器' : '订阅器' }}
                  </el-tag>
                  <span v-if="selected.kind === 'subscriber'">时间：{{ formatGooseTime(selected.last_update) }}</span>
                  <span>状态号：{{ selected.st_num }}</span>
                  <span>顺序号：{{ selected.sq_num }}</span>
                  <span>数据集：{{ selected.data_set_ref || '-' }}</span>
                  <span>值：{{ selected.data_values.length }}</span>
                </div>
                <GooseDataSetTable :values="selected.data_values" />
              </div>
            </el-tab-pane>

            <el-tab-pane v-if="selected.kind === 'subscriber'" :label="`GOOSE 报文数据 (${history.length})`" name="history">
              <div class="history-pane">
                <el-table
                  :data="history"
                  size="small"
                  border
                  height="100%"
                  highlight-current-row
                  @current-change="selectedHistory = $event"
                >
                  <el-table-column prop="st_num" label="状态号" width="75" />
                  <el-table-column prop="sq_num" label="顺序号" width="75" />
                  <el-table-column label="时间" min-width="165">
                    <template #default="{ row }">{{ formatGooseTime(row.received_at) }}</template>
                  </el-table-column>
                  <el-table-column prop="value_count" label="值" width="55" />
                  <el-table-column prop="changed_count" label="变化" width="60" />
                </el-table>
                <div class="history-detail">
                  <div v-if="selectedHistory" class="summary">
                    <span>状态号：{{ selectedHistory.st_num }}</span>
                    <span>顺序号：{{ selectedHistory.sq_num }}</span>
                    <span>变化：{{ selectedHistory.changed_count }}</span>
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
import { ElMessage } from 'element-plus';
import { Refresh } from '@element-plus/icons-vue';
import {
  getGoosePublishers,
  getGooseReceivers,
  getGooseNetworkInterfaces,
  getGooseSubscriptionHistory,
  startGoosePublisher,
  stopGoosePublisher,
  stopGooseReceiver,
  updateGoosePublisher,
  updateGooseReceiver,
  updateGooseSubscription,
  type GooseMessageHistoryItem,
} from '@/api/gooseApi';
import GooseBlockTreePanel from './GooseBlockTreePanel.vue';
import GooseControlPanel from './GooseControlPanel.vue';
import GooseDataSetTable from './GooseDataSetTable.vue';
import GoosePublisherControlPanel from './GoosePublisherControlPanel.vue';
import { flattenGooseBlocks, formatGooseTime, type GooseBlockItem } from './gooseWorkbench';

const props = defineProps<{ channelId?: number }>();
const publishers = ref<Awaited<ReturnType<typeof getGoosePublishers>>>([]);
const receivers = ref<Awaited<ReturnType<typeof getGooseReceivers>>>([]);
const networkInterfaces = ref<Awaited<ReturnType<typeof getGooseNetworkInterfaces>>>([]);
const blocks = computed(() => flattenGooseBlocks(publishers.value, receivers.value));
const selectedKey = ref('');
const selected = computed(() => blocks.value.find((item) => item.key === selectedKey.value) || null);
const activeTab = ref('attributes');
const history = ref<GooseMessageHistoryItem[]>([]);
const selectedHistory = ref<GooseMessageHistoryItem | null>(null);
const loading = ref(false);
const applying = ref(false);
const autoRefresh = ref(true);
const pollInterval = ref(2000);
const batchMode = ref(false);
const checkedKeys = ref<string[]>([]);
let timer: ReturnType<typeof setTimeout> | null = null;
let active = true;

watch(
  () => props.channelId,
  async () => {
    selectedKey.value = '';
    history.value = [];
    await Promise.all([loadBlocks(), loadNetworkInterfaces()]);
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
    if (activeTab.value === 'history' && selected.value?.kind === 'subscriber') await loadHistory();
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

function selectBlock(block: GooseBlockItem) {
  selectedKey.value = block.key;
  history.value = [];
  selectedHistory.value = null;
  if (block.kind === 'publisher' && activeTab.value === 'history') activeTab.value = 'attributes';
  if (activeTab.value === 'history') void loadHistory();
}

function parseMac(value: string): number[] | null {
  if (!value.trim()) return null;
  const parts = value.split(/[:-]/);
  if (parts.length !== 6 || parts.some((item) => !/^[0-9a-fA-F]{2}$/.test(item))) {
    throw new Error('目标MAC地址格式错误');
  }
  return parts.map((item) => Number.parseInt(item, 16));
}

async function applyPublisherConfig(form: {
  enabled: boolean;
  interface: string;
  go_id: string;
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
      dst_mac: block.publisher.dst_mac ? parseMac(block.publisher.dst_mac) : null,
      vlan_id: form.vlan_id,
      vlan_prio: form.vlan_prio,
      simulation: form.simulation,
    });
    if (form.enabled) await startGoosePublisher(props.channelId, publisherId);
    ElMessage.success('GOOSE 发布配置已应用');
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
      dst_mac: block.subscription.dst_mac ? parseMac(block.subscription.dst_mac) : null,
      description: form.description,
      data_set_ref: form.data_set_ref,
      conf_rev: form.conf_rev,
      ied_name: block.ied_name,
      ld_inst: block.ld_inst,
      ln_name: block.ln_name,
      dataset_entries: block.subscription.dataset_entries,
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

async function loadHistory() {
  const block = selected.value;
  if (!props.channelId || block?.kind !== 'subscriber' || !block.receiver_id) return;
  history.value = await getGooseSubscriptionHistory(
    props.channelId,
    block.receiver_id,
    block.go_cb_ref,
  );
  selectedHistory.value = history.value[0] || null;
}

function handleTabChange(tab: string | number) {
  if (tab === 'history') void loadHistory();
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
.goose-workbench { display: flex; flex-direction: column; height: 100%; overflow: hidden; border-radius: 4px; background: #fff; }
.manager-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid #d8dde5; background: #fbfcfe; }
.manager-header h3 { margin: 0; color: #263241; font-size: 16px; font-weight: 700; }
.header-actions { display: flex; align-items: center; gap: 9px; color: #5d6876; font-size: 13px; }
.manager-body { display: flex; flex: 1; min-height: 0; overflow: hidden; }
.manager-body > .el-empty { width: 100%; }
.workspace { flex: 1; min-width: 0; min-height: 0; padding: 12px; overflow: hidden; }
.workspace-tabs { display: flex; flex-direction: column; height: 100%; }
:deep(.el-tabs__content) { flex: 1; min-height: 0; overflow: hidden; }
:deep(.el-tab-pane) { height: 100%; overflow: auto; }
.latest-pane { display: flex; flex-direction: column; gap: 10px; height: 100%; }
.summary { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; padding: 9px 11px; border: 1px solid #d8dde5; background: #f6f8fb; font-size: 13px; }
.history-pane { display: grid; grid-template-columns: 390px minmax(0, 1fr); height: 100%; min-height: 0; }
.history-detail { display: flex; flex-direction: column; gap: 9px; min-width: 0; padding-left: 10px; }
@media (max-width: 900px) { .manager-header { align-items: flex-start; flex-direction: column; gap: 10px; } .header-actions { flex-wrap: wrap; } .manager-body { flex-direction: column; overflow: auto; } .history-pane { grid-template-columns: 1fr; grid-template-rows: 240px minmax(300px, 1fr); } }
</style>
