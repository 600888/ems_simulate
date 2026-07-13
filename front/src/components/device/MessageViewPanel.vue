<template>
  <div class="message-view-panel" :class="{ 'is-fill': fillWindow }">
    <div class="toolbar">
      <div class="left-actions">
        <el-button :type="autoRefresh ? 'warning' : 'success'" @click="toggleAutoRefresh" :icon="autoRefresh ? VideoPause : CaretRight">
          {{ autoRefresh ? $t('messageView.pauseRefresh') : $t('messageView.startRefresh') }}
        </el-button>
        <el-button type="danger" @click="handleClear" :icon="Delete">{{ $t('messageView.clearMessages') }}</el-button>
        <el-select v-model="searchMode" class="search-mode-select">
          <el-option :label="$t('messageView.byDescription')" value="description" />
          <el-option :label="$t('messageView.byData')" value="hex_data" />
        </el-select>
        <el-input
          v-model="searchKeyword"
          :placeholder="searchMode === 'description' ? $t('messageView.searchDesc') : $t('messageView.searchData')"
          :prefix-icon="Search"
          clearable
          class="search-input"
        />
      </div>
      <div class="right-info">
        <span class="msg-count">{{ $t('messageView.messageCount', { filtered: filteredMessages.length, total: messages.length }) }}</span>
        <el-tag v-if="avgStats && avgStats.pair_count > 0" type="warning" size="small">
          {{ $t('messageView.avgLatency', { ms: avgStats.avg_latency_ms, pairs: avgStats.pair_count }) }}
        </el-tag>
        <el-tag v-if="autoRefresh" type="success" size="small">{{ $t('messageView.autoRefreshing') }}</el-tag>
        <el-tag v-else type="info" size="small">{{ $t('messageView.paused') }}</el-tag>
      </div>
    </div>

    <el-table :data="filteredMessages" stripe :height="fillWindow ? '100%' : 400" class="message-table" :row-class-name="getRowClass">
      <el-table-column
        prop="timestamp"
        :label="$t('messageView.time')"
        width="180"
        header-align="center"
        sortable
        :sort-method="sortByTimestamp"
        :sort-orders="['descending', 'ascending', null]"
      >
        <template #default="{ row }">{{ row.formatted_time }}</template>
      </el-table-column>
      <el-table-column prop="direction" :label="$t('messageView.direction')" width="80" align="center" header-align="center">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'TX' ? 'primary' : 'success'" size="small">
            {{ row.direction === 'TX' ? $t('messageView.send') : $t('messageView.receive') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="length" :label="$t('messageView.length')" width="70" align="center" header-align="center">
        <template #default="{ row }"><span class="length-badge">{{ row.length }}</span></template>
      </el-table-column>
      <el-table-column prop="hex_data" :label="$t('messageView.dataHex')" min-width="350" align="center" header-align="center">
        <template #default="{ row }"><span class="hex-data" :title="row.hex_data">{{ row.hex_data }}</span></template>
      </el-table-column>
      <el-table-column prop="description" :label="$t('messageView.parsed')" min-width="280" header-align="center">
        <template #default="{ row }"><span class="desc-text" :title="row.description">{{ row.description }}</span></template>
      </el-table-column>
      <el-table-column label="详情" width="90" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="detailDrawer?.open(row.sequence_id)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>
    <MessageDetailDrawer ref="detailDrawer" :device-name="deviceName" />
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CaretRight, VideoPause, Delete, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showErrorOnce } from '@/api/http'
import { getMessages, clearMessages, getAvgTime, type MessageRecord, type AvgTimeStats } from '@/api/deviceApi'
import MessageDetailDrawer from './MessageDetailDrawer.vue'

const props = withDefaults(defineProps<{ deviceName: string; active?: boolean; fillWindow?: boolean }>(), {
  active: true,
  fillWindow: false,
})
const { t } = useI18n()
const messages = ref<MessageRecord[]>([])
const avgStats = ref<AvgTimeStats | null>(null)
const autoRefresh = ref(true)
const detailDrawer = ref<InstanceType<typeof MessageDetailDrawer> | null>(null)
const searchKeyword = ref('')
const searchMode = ref<'description' | 'hex_data'>('description')
let refreshTimer: ReturnType<typeof setInterval> | null = null

const filteredMessages = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) return messages.value
  return messages.value.filter((message) => {
    const field = searchMode.value === 'description' ? message.description : message.hex_data
    return field?.toLowerCase().includes(keyword)
  })
})

async function fetchMessages() {
  if (!props.deviceName || !props.active) return
  try {
    ;[messages.value, avgStats.value] = await Promise.all([
      getMessages(props.deviceName, 200),
      getAvgTime(props.deviceName),
    ])
  } catch (error) {
    console.error('Failed to fetch messages:', error)
  }
}

function stopAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = null
}

function startAutoRefresh() {
  if (!props.active || refreshTimer) return
  refreshTimer = setInterval(fetchMessages, 1000)
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  autoRefresh.value ? startAutoRefresh() : stopAutoRefresh()
}

async function handleClear() {
  try {
    await ElMessageBox.confirm(t('messageView.clearConfirm'), t('common.hint'), {
      confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel'), type: 'warning',
    })
    if (await clearMessages(props.deviceName)) {
      messages.value = []
      avgStats.value = null
      ElMessage.success(t('messageView.cleared'))
    } else {
      showErrorOnce(t('messageView.clearFailed'))
    }
  } catch { /* 用户取消 */ }
}

function getRowClass({ row }: { row: MessageRecord }) {
  return row.direction === 'TX' ? 'tx-row' : 'rx-row'
}

function sortByTimestamp(left: MessageRecord, right: MessageRecord) {
  return Number(left.timestamp || 0) - Number(right.timestamp || 0)
}

watch(() => props.active, (active) => {
  if (active) {
    fetchMessages()
    if (autoRefresh.value) startAutoRefresh()
  } else stopAutoRefresh()
})

onMounted(() => {
  if (props.active) {
    fetchMessages()
    if (autoRefresh.value) startAutoRefresh()
  }
})
onUnmounted(stopAutoRefresh)
</script>

<style lang="scss" scoped>
.message-view-panel { min-height: 0; display: flex; flex-direction: column; }
.message-view-panel.is-fill { height: 100%; }
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; padding: 10px 12px; background: var(--panel-bg, #f5f5f5); border-radius: 8px; flex-wrap: wrap; }
.left-actions, .right-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.right-info { gap: 12px; }
.search-mode-select { width: 100px; }
.search-input { width: 200px; }
.msg-count { color: var(--text-secondary, #666); font-size: 14px; }
.message-table { flex: 1; min-height: 0; border-radius: 8px; overflow: hidden; }
.message-table :deep(.tx-row) { background-color: rgba(59, 130, 246, 0.05); }
.message-table :deep(.rx-row) { background-color: rgba(16, 185, 129, 0.05); }
.hex-data {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-primary, #333);
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
  white-space: normal;
  text-align: left;
  text-overflow: ellipsis;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.length-badge { display: inline-block; min-width: 32px; padding: 2px 6px; background: var(--panel-bg, #f0f0f0); border-radius: 4px; text-align: center; font-size: 12px; font-weight: 500; }
.desc-text { font-size: 13px; color: var(--text-secondary, #555); word-break: break-all; }
</style>
