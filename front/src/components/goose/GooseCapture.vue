<template>
  <div class="goose-capture">
    <!-- 控制栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="interfaceName"
          placeholder="Network Interface (empty=auto)"
          style="width: 180px"
          size="small"
          :disabled="captureRunning"
        />
        <el-input-number
          v-model="maxPackets"
          :min="100"
          :max="10000"
          :step="100"
          size="small"
          style="width: 140px"
          :disabled="captureRunning"
        >
          <template #prefix>
            <span style="font-size: 12px; color: #909399;">缓存:</span>
          </template>
        </el-input-number>
        <el-input-number
          v-model="filterAppId"
          :min="0"
          :max="65535"
          size="small"
          style="width: 140px"
          placeholder="APPID 过滤"
          :disabled="captureRunning"
        >
          <template #prefix>
            <span style="font-size: 12px; color: #909399;">APPID:</span>
          </template>
        </el-input-number>
      </div>
      <div class="toolbar-right">
        <el-button
          v-if="!captureRunning"
          type="success"
          :icon="VideoPlay"
          size="small"
          @click="startCapture"
          :loading="starting"
        >
          {{ $t('goose.startCapture') }}
        </el-button>
        <el-button
          v-else
          type="danger"
          :icon="VideoPause"
          size="small"
          @click="stopCapture"
          :loading="stopping"
        >
          {{ $t('goose.stopCapture') }}
        </el-button>
        <el-button
          :icon="Refresh"
          size="small"
          @click="refreshPackets"
          :disabled="!captureRunning"
          :loading="loading"
        >
          {{ $t('goose.refresh') }}
        </el-button>
        <el-button
          :icon="Delete"
          size="small"
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
      :data="packets"
      stripe
      border
      style="width: 100%"
      v-loading="loading"
      height="calc(100vh - 340px)"
      size="small"
      @row-click="showPacketDetail"
    >
      <el-table-column type="index" label="#" width="50" />
      <el-table-column label="时间" width="165" sortable>
        <template #default="{ row }">
          {{ row.time }}
        </template>
      </el-table-column>
      <el-table-column prop="src_mac" label="源MAC" width="140" />
      <el-table-column prop="dst_mac" label="目标MAC" width="140" />
      <el-table-column label="APPID" width="80" sortable>
        <template #default="{ row }">
          <el-tag size="small">{{ row.app_id_hex }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="go_cb_ref" label="GoCBRef" min-width="200" show-overflow-tooltip />
      <el-table-column prop="go_id" label="GoID" width="100" show-overflow-tooltip />
      <el-table-column label="stNum" width="65" sortable align="center" prop="st_num" />
      <el-table-column label="sqNum" width="65" align="center" prop="sq_num" />
      <el-table-column label="TAL(ms)" width="75" align="right" prop="time_allowed_to_live" />
      <el-table-column label="长度" width="65" align="right" prop="length" />
      <el-table-column label="仿真" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.simulation" type="warning" size="small">是</el-tag>
          <span v-else class="text-muted">否</span>
        </template>
      </el-table-column>
      <el-table-column label="VLAN" width="100">
        <template #default="{ row }">
          <span v-if="row.has_vlan" class="text-muted">
            ID={{ row.vlan_id }} P={{ row.vlan_prio }}
          </span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="数据集" min-width="200">
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
      :title="`GOOSE 报文详情 - ${detailPacket?.app_id_hex || ''}`"
      width="900px"
      top="5vh"
      destroy-on-close
    >
      <template v-if="detailPacket">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="时间" :span="2">{{ detailPacket.time }}</el-descriptions-item>
          <el-descriptions-item label="长度">{{ detailPacket.length }} 字节</el-descriptions-item>
          <el-descriptions-item label="源MAC">{{ detailPacket.src_mac }}</el-descriptions-item>
          <el-descriptions-item label="目标MAC">{{ detailPacket.dst_mac }}</el-descriptions-item>
          <el-descriptions-item label="APPID">
            <el-tag size="small">{{ detailPacket.app_id_hex }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="GoCBRef" :span="3">{{ detailPacket.go_cb_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item label="GoID">{{ detailPacket.go_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="数据集引用">{{ detailPacket.data_set_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item label="VLAN">
            {{ detailPacket.has_vlan ? `ID=${detailPacket.vlan_id}, P=${detailPacket.vlan_prio}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="stNum">{{ detailPacket.st_num }}</el-descriptions-item>
          <el-descriptions-item label="sqNum">{{ detailPacket.sq_num }}</el-descriptions-item>
          <el-descriptions-item label="confRev">{{ detailPacket.conf_rev }}</el-descriptions-item>
          <el-descriptions-item label="TAL(ms)">{{ detailPacket.time_allowed_to_live }}</el-descriptions-item>
          <el-descriptions-item label="仿真">
            <el-tag v-if="detailPacket.simulation" type="warning" size="small">是</el-tag>
            <span v-else>否</span>
          </el-descriptions-item>
          <el-descriptions-item label="ndsCom">
            <span>{{ detailPacket.nds_com ? '是' : '否' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="数据集条目数">{{ detailPacket.num_dat_set_entries }}</el-descriptions-item>
        </el-descriptions>

        <!-- 数据集值 -->
        <h4 style="margin: 16px 0 8px">数据集值 ({{ detailPacket.data_values?.length || 0 }})</h4>
        <el-table :data="detailPacket.data_values || []" border size="small" max-height="200">
          <el-table-column type="index" label="序号" width="60" />
          <el-table-column label="类型" width="120" prop="type" />
          <el-table-column label="值" prop="value" />
        </el-table>

        <!-- 十六进制转储 -->
        <h4 style="margin: 16px 0 8px">原始十六进制</h4>
        <el-tabs type="border-card" size="small">
          <el-tab-pane label="HEX Dump">
            <pre class="hex-dump">{{ detailPacket.hex_string }}</pre>
          </el-tab-pane>
          <el-tab-pane label="Hex String">
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
import { VideoPlay, VideoPause, Refresh, Delete } from '@element-plus/icons-vue'
import { GooseCaptureWebSocket, WsEventType } from '@/services/GooseCaptureWebSocket'
import type {
  GooseCapturedPacket,
  GooseCaptureStatistics,
} from '@/api/gooseApi'

const ws = GooseCaptureWebSocket.getInstance()
const { t } = useI18n()

// ===== 状态 =====
const loading = ref(false)
const starting = ref(false)
const stopping = ref(false)
const captureRunning = ref(false)
const interfaceName = ref('')
const maxPackets = ref(500)
const filterAppId = ref<number | null>(null)

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
  captureRunning.value = true
  cmdSeq++

  ws.start({
    interface: interfaceName.value || undefined,
    max_packets: maxPackets.value,
    filter_app_id: filterAppId.value,
  })
}

let stopTimeoutId: ReturnType<typeof setTimeout> | null = null

function stopCapture() {
  if (!captureRunning.value || stopping.value) return

  stopping.value = true    // 停止按钮显示 loading
  cmdSeq++

  ws.stop()

  // ⏱ 兜底超时：3秒后如果还没收到 response，强制清除 loading
  if (stopTimeoutId) clearTimeout(stopTimeoutId)
  stopTimeoutId = setTimeout(() => {
    if (stopping.value) {
      stopping.value = false
      // 再发一次 status 查询真实状态
      ws.status()
    }
  }, 3000)
}

function refreshPackets() {
  if (ws.isConnected) {
    loading.value = true
    ws.list()
  }
}

function clearPackets() {
  ElMessageBox.confirm(t('goose.clearConfirm'), t('common.confirm'), { type: 'warning' })
    .then(() => {
      ws.clear()
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
        ElMessage.success(t('goose.captureStarted'))
        lastListSeq = curSeq
        ws.list()
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
          ws.list()
        }
      }
    }
  }),
)

/** 连接建立后自动检查抓包状态 */
cleanups.push(
  ws.on(WsEventType.CONNECTED, () => {
    ws.status()
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
    ElMessage.error(err.message || 'WebSocket 错误')
  }),
)

// ===== 生命周期 =====

onMounted(() => {
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
