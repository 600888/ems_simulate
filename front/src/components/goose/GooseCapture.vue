<template>
  <div class="goose-capture">
    <!-- 控制栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <div class="toolbar-item">
          <span class="toolbar-label">{{ $t('goose.iface') }}</span>
          <el-select
            v-model="interfaceName"
            :placeholder="$t('goose.interfacePlaceholder')"
            class="capture-control interface-control"
            :disabled="captureRunning"
            :title="interfaceName"
          >
            <el-option v-for="item in networkInterfaces" :key="item.id" :value="item.id" class="network-option-item">
              <div class="network-option">
                <el-icon class="network-option-icon"><Monitor /></el-icon>
                <div class="network-option-body">
                  <span class="network-option-name">{{ item.display_name }}</span>
                  <span class="network-option-mac">MAC: {{ (item.mac || "-").replace(/-/g, ":") }}</span>
                </div>
              </div>
            </el-option>
          </el-select>
        </div>
        <div class="toolbar-item">
          <span class="toolbar-label">{{ $t('goose.cache') }}</span>
          <el-input-number
            v-model="maxPackets"
            :min="100"
            :max="10000"
            :step="100"
            :controls="true"
            class="capture-control number-control"
            :disabled="captureRunning"
          />
        </div>
        <div class="toolbar-item">
          <span class="toolbar-label">{{ $t('goose.appIdLabel') }}</span>
          <el-input-number
            v-model="filterAppId"
            :min="0"
            :max="65535"
            :controls="true"
            class="capture-control number-control appid-control"
            :placeholder="$t('goose.filterAppId')"
            :disabled="captureRunning"
          />
        </div>
      </div>
      <div class="toolbar-right">
        <el-button
          v-if="!captureRunning"
          type="success"
          :icon="VideoPlay"
          @click="startCapture"
          :loading="starting"
        >
          {{ $t('goose.startCapture') }}
        </el-button>
        <el-button
          v-else
          type="danger"
          :icon="VideoPause"
          @click="stopCapture"
          :loading="stopping"
        >
          {{ $t('goose.stopCapture') }}
        </el-button>
        <el-button
          :icon="Refresh"
          @click="refreshPackets"
          :disabled="!captureRunning"
          :loading="loading"
        >
          {{ $t('goose.refresh') }}
        </el-button>
        <el-button
          :icon="Delete"
          @click="clearPackets"
          :disabled="!hasData"
        >
          {{ $t('goose.clear') }}
        </el-button>
      </div>
    </div>

    <!-- 统计信息 -->
    <div v-if="statistics" class="capture-stats">
      <div class="stat-item">
        <span class="stat-label">{{ $t('goose.totalCaptured') }}</span>
        <span class="stat-value">{{ statistics.total_captured }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">{{ $t('goose.buffer') }}</span>
        <span class="stat-value">{{ statistics.buffer_size }} / {{ statistics.max_buffer_size }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">{{ $t('goose.appIdDist') }}</span>
        <span class="stat-value">
          <el-tag
            v-for="app in (statistics.app_ids || [])"
            :key="app.app_id"
            size="small"
            style="margin: 0 2px"
          >
            {{ app.app_id_hex }} ({{ app.count }})
          </el-tag>
          <span v-if="!statistics.app_ids?.length" class="text-muted">-</span>
        </span>
      </div>
    </div>

    <!-- 报文列表 -->
    <el-table
      class="capture-table"
      :data="packets"
      stripe
      border
      style="width: 100%"
      v-loading="loading"
      size="small"
      @row-click="showPacketDetail"
    >
      <el-table-column type="index" :label="$t('goose.seqNum')" width="50" />
      <el-table-column :label="$t('goose.time')" width="165" sortable>
        <template #default="{ row }">
          {{ row.time }}
        </template>
      </el-table-column>
      <el-table-column prop="src_mac" :label="$t('goose.srcMac')" width="140" />
      <el-table-column prop="dst_mac" :label="$t('goose.dstMacLabel')" width="140" />
      <el-table-column :label="$t('goose.appId')" width="90" sortable>
        <template #default="{ row }">
          <el-tag size="small">{{ row.app_id_hex }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="go_cb_ref" :label="$t('goose.goCbRef')" min-width="200" show-overflow-tooltip />
      <el-table-column prop="go_id" :label="$t('goose.goId')" width="100" show-overflow-tooltip />
      <el-table-column :label="$t('goose.stNum')" width="85" sortable align="center" prop="st_num" />
      <el-table-column :label="$t('goose.sqNum')" width="80" align="center" prop="sq_num" />
      <el-table-column :label="$t('goose.tal')" width="95" align="right" prop="time_allowed_to_live" />
      <el-table-column :label="$t('goose.length')" width="75" align="right" prop="length" />
      <el-table-column :label="$t('goose.simulationLabel')" width="75" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.simulation" type="warning" size="small">{{ $t('goose.yes') }}</el-tag>
          <span v-else class="text-muted">{{ $t('goose.no') }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('goose.vlan')" width="100">
        <template #default="{ row }">
          <span v-if="row.has_vlan" class="text-muted">
            ID={{ row.vlan_id }} P={{ row.vlan_prio }}
          </span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('goose.dataSet')" min-width="200">
        <template #default="{ row }">
          <div v-if="row.data_values?.length" class="data-values">
            <el-tooltip
              v-for="(dv, idx) in row.data_values.slice(0, 5)"
              :key="idx"
              :content="`[${idx}] ${dv.type}: ${dv.value}`"
              placement="top"
            >
              <span class="data-value-item">{{ dv.value }}</span>
            </el-tooltip>
            <span v-if="row.data_values.length > 5" class="text-muted">+{{ row.data_values.length - 5 }}</span>
          </div>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 报文详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      :title="$t('goose.packetDetailTitle', { appId: detailPacket?.app_id_hex || '' })"
      width="900px"
      top="5vh"
      destroy-on-close
    >
      <template v-if="detailPacket">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item :label="$t('goose.time')" :span="2">{{ detailPacket.time }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.length')">{{ $t('goose.bytes', { count: detailPacket.length }) }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.srcMac')">{{ detailPacket.src_mac }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.dstMacLabel')">{{ detailPacket.dst_mac }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.appId')">
            <el-tag size="small">{{ detailPacket.app_id_hex }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('goose.goCbRef')" :span="3">{{ detailPacket.go_cb_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.goId')">{{ detailPacket.go_id || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.dataSetRef')">{{ detailPacket.data_set_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.vlan')">
            {{ detailPacket.has_vlan ? `ID=${detailPacket.vlan_id}, P=${detailPacket.vlan_prio}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('goose.stNum')">{{ detailPacket.st_num }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.sqNum')">{{ detailPacket.sq_num }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.confRev')">{{ detailPacket.conf_rev }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.tal')">{{ detailPacket.time_allowed_to_live }}</el-descriptions-item>
          <el-descriptions-item :label="$t('goose.simulationLabel')">
            <el-tag v-if="detailPacket.simulation" type="warning" size="small">{{ $t('goose.yes') }}</el-tag>
            <span v-else>{{ $t('goose.no') }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('goose.ndsCom')">
            <span>{{ detailPacket.nds_com ? $t('goose.yes') : $t('goose.no') }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('goose.numEntries')">{{ detailPacket.num_dat_set_entries }}</el-descriptions-item>
        </el-descriptions>

        <!-- 数据集值 -->
        <h4 style="margin: 16px 0 8px">{{ $t('goose.dataValues') }} ({{ detailPacket.data_values?.length || 0 }})</h4>
        <el-table :data="detailPacket.data_values || []" border size="small" max-height="200">
          <el-table-column type="index" :label="$t('goose.seqNum')" width="60" />
          <el-table-column :label="$t('goose.entryType')" width="120" prop="type" />
          <el-table-column :label="$t('goose.entryValue')" prop="value" />
        </el-table>

        <!-- 十六进制转储 -->
        <h4 style="margin: 16px 0 8px">{{ $t('goose.rawHex') }}</h4>
        <el-tabs type="border-card" size="small">
          <el-tab-pane :label="$t('goose.hexDumpLabel')">
            <pre class="hex-dump">{{ detailPacket.hex_string }}</pre>
          </el-tab-pane>
          <el-tab-pane :label="$t('goose.hexStringLabel')">
            <el-input
              type="textarea"
              :model-value="detailPacket.hex_data"
              :rows="6"
              readonly
              style="font-family: monospace;"
            />
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay, VideoPause, Refresh, Delete, Monitor } from '@element-plus/icons-vue'
import { GooseCaptureWebSocket, WsEventType } from '@/services/GooseCaptureWebSocket'
import type {
  GooseCapturedPacket,
  GooseCaptureStatistics,
  NetworkInterfaceInfo,
} from '@/api/gooseApi'
import { getGooseNetworkInterfaces } from '@/api/gooseApi'

const props = defineProps<{ channelId: number }>()

const ws = GooseCaptureWebSocket.getInstance()
const { t } = useI18n()

// ===== 状态 =====
const loading = ref(false)
const starting = ref(false)
const stopping = ref(false)
const captureRunning = ref(false)
const interfaceName = ref('')
const networkInterfaces = ref<NetworkInterfaceInfo[]>([])
const maxPackets = ref(100)
const filterAppId = ref<number | null>(1)

const packets = ref<GooseCapturedPacket[]>([])
const statistics = ref<GooseCaptureStatistics | null>(null)
const hasData = computed(() => packets.value.length > 0)

// 详情对话框
const detailVisible = ref(false)
const detailPacket = ref<GooseCapturedPacket | null>(null)

// 请求序列号，用于匹配 response，过滤过期响应
let cmdSeq = 0

// 事件取消函数列表
const cleanups: Array<() => void> = []

// ===== 操作 =====

function startCapture() {
  if (captureRunning.value || starting.value) return

  starting.value = true
  cmdSeq++

  ws.start({
    channel_id: props.channelId,
    interface: interfaceName.value || undefined,
    max_packets: maxPackets.value,
    filter_app_id: filterAppId.value,
  })
}

let stopTimeoutId: ReturnType<typeof setTimeout> | null = null

function stopCapture() {
  if ((!captureRunning.value && !starting.value) || stopping.value) return

  stopping.value = true    // 停止按钮显示 loading
  starting.value = false
  cmdSeq++

  ws.stop(props.channelId)

  // ⏱ 兜底超时：3秒后如果还没收到 response，强制清除 loading
  if (stopTimeoutId) clearTimeout(stopTimeoutId)
  stopTimeoutId = setTimeout(() => {
    if (stopping.value) {
      stopping.value = false
      // 再发一次 status 查询真实状态
      ws.status(props.channelId)
    }
  }, 3000)
}

function refreshPackets() {
  if (ws.isConnected) {
    loading.value = true
    ws.list({ channel_id: props.channelId })
  }
}

function clearPackets() {
  ElMessageBox.confirm(t('goose.clearConfirm'), t('common.confirm'), { type: 'warning' })
    .then(() => {
      ws.clear(props.channelId)
    })
    .catch(() => {})
}

function showPacketDetail(row: GooseCapturedPacket) {
  detailPacket.value = row
  detailVisible.value = true
}

// ===== WebSocket 事件绑定 (Observer) =====

/** 收到实时报文推送 */
cleanups.push(
  ws.on(WsEventType.PACKET, (pkt: GooseCapturedPacket) => {
    // 新报文从尾部追加
    packets.value = [...packets.value, pkt]
  }),
)

/** 收到指令响应 — 使用 seq 机制过滤过期响应 */
let lastListSeq = 0
cleanups.push(
  ws.on(WsEventType.RESPONSE, (res: { command: string; success: boolean; data?: any; message?: string }) => {
    const curSeq = cmdSeq

    if (res.command === 'start') {
      starting.value = false
      if (res.success) {
        captureRunning.value = true
        ElMessage.success(t('goose.captureStarted'))
        lastListSeq = curSeq
        ws.list({ channel_id: props.channelId })
      } else {
        captureRunning.value = false
        ElMessage.error(res.message || t('goose.createFailed'))
      }
    } else if (res.command === 'stop') {
      // 清除兜底超时
      if (stopTimeoutId) {
        clearTimeout(stopTimeoutId)
        stopTimeoutId = null
      }
      // ⚠️ 只有 seq 未变更时才处理，防止过期 stop 响应把状态改错
      stopping.value = false
      if (curSeq !== cmdSeq) return
      if (res.success) {
        captureRunning.value = false
        ElMessage.success(t('goose.captureStopped'))
      } else {
        captureRunning.value = true
        ElMessage.error(res.message || t('goose.publishFailed'))
      }
    } else if (res.command === 'list') {
      loading.value = false
      if (curSeq !== cmdSeq && lastListSeq !== curSeq) return
      lastListSeq = curSeq
      if (res.success && res.data) {
        packets.value = res.data.packets || []
        statistics.value = res.data.statistics || null
      }
    } else if (res.command === 'clear') {
      if (res.success) {
        packets.value = []
        statistics.value = null
        ElMessage.success(t('goose.clearSuccess'))
      }
    } else if (res.command === 'status') {
      if (res.success && res.data?.captures?.length > 0) {
        const c = res.data.captures[0]
        const wasRunning = captureRunning.value
        captureRunning.value = c.is_running
        stopping.value = false
        starting.value = false
        // 重连后发现抓包在运行，拉取最新数据
        if (c.is_running && !wasRunning) {
          ws.list({ channel_id: props.channelId })
        }
      }
    }
  }),
)

/** 连接建立后自动检查抓包状态 */
cleanups.push(
  ws.on(WsEventType.CONNECTED, () => {
    ws.status(props.channelId)
  }),
)

/** 连接断开 — 只清 loading，不重置 running，等重连后 status 查询 */
cleanups.push(
  ws.on(WsEventType.DISCONNECTED, () => {
    stopping.value = false
    starting.value = false
  }),
)

/** 错误消息 */
cleanups.push(
  ws.on(WsEventType.ERROR, (err: { message: string }) => {
    loading.value = false
    starting.value = false
    stopping.value = false
    ElMessage.error(err.message || t('goose.websocketError'))
  }),
)

// ===== 生命周期 =====

onMounted(async () => {
  networkInterfaces.value = (await getGooseNetworkInterfaces()).filter(item => item.supports_raw_ethernet)
  if (!interfaceName.value && networkInterfaces.value.length) interfaceName.value = networkInterfaces.value[0].id
  // 自动建立 WebSocket 连接，连接后会检查抓包状态
  ws.connect()
})

onUnmounted(() => {
  // 清理所有事件订阅 (Observer 解绑)
  cleanups.forEach((fn) => fn())
  cleanups.length = 0
  if (stopTimeoutId) {
    clearTimeout(stopTimeoutId)
    stopTimeoutId = null
  }
})
</script>

<style scoped lang="scss">
.goose-capture {
  padding: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.capture-table {
  flex: 1;
  min-height: 0;
}

/* 表头文字不换行 */
:deep(.el-table thead th .cell) {
  white-space: nowrap;
}

/* 表格所有列居中 */
:deep(.el-table .cell) {
  text-align: center;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;

  .toolbar-left,
  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .toolbar-left {
    flex: 1 1 620px;
    flex-wrap: wrap;
    min-width: 0;
  }

  .toolbar-right {
    flex: 0 0 auto;
    margin-left: auto;
  }
}

.toolbar-item {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  min-width: 0;
}

.toolbar-label {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  white-space: nowrap;
}

.capture-control {
  height: 32px;
}

.interface-control {
  width: 280px;
}

.number-control {
  width: 156px;
}

.appid-control {
  width: 180px;
}

:deep(.capture-control .el-select__wrapper),
:deep(.capture-control.el-input-number .el-input__wrapper) {
  min-height: 32px;
}

:deep(.number-control .el-input__inner) {
  text-align: center;
}

@media (max-width: 900px) {
  .toolbar-right {
    width: 100%;
    justify-content: flex-end;
  }

  .interface-control {
    width: min(280px, calc(100vw - 150px));
  }
}

.capture-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  flex-wrap: wrap;

  .stat-item {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .stat-label {
    font-size: 12px;
    color: #909399;
    white-space: nowrap;
  }

  .stat-value {
    font-size: 13px;
    font-weight: 500;
  }
}

.data-values {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.data-value-item {
  display: inline-block;
  padding: 1px 5px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 3px;
  font-size: 11px;
  font-family: monospace;
  cursor: default;
}

.text-muted {
  color: #909399;
  font-size: 12px;
}

.hex-dump {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 400px;
  white-space: pre;
}
</style>

<style lang="scss">
.el-select-dropdown__item.network-option-item {
  height: auto;
  min-height: auto;
  padding: 4px 12px;
}
.el-select-dropdown__item.network-option-item:first-child { padding-top: 0; }
.el-select-dropdown__item.network-option-item:last-child { padding-bottom: 0; }
.network-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  .network-option-icon { font-size: 16px; color: #409eff; flex-shrink: 0; }
  .network-option-body { display: flex; flex-direction: column; min-width: 0; }
  .network-option-name { font-size: 13px; color: #303133; line-height: 1.3; }
  .network-option-mac { font-family: "Cascadia Code","Fira Code","JetBrains Mono",Consolas,monospace; font-size: 11px; color: #909399; line-height: 1.2; }
}
</style>
