<template>
  <div class="goose-manager">
    <el-tabs v-model="activeTab" class="goose-tabs">
      <!-- Publisher 面板 -->
      <el-tab-pane label="GOOSE 发布" name="publisher">
        <div class="tab-header">
          <el-button type="primary" :icon="Plus" @click="showCreatePublisherDialog">
            新建 Publisher
          </el-button>
          <el-button :icon="Refresh" @click="refreshPublishers" :loading="loading">
            刷新
          </el-button>
        </div>

        <el-table :data="publishers" stripe border style="width: 100%" v-loading="loading">
          <el-table-column prop="go_cb_ref" label="GoCBRef" min-width="220" show-overflow-tooltip />
          <el-table-column prop="go_id" label="GoID" width="120" />
          <el-table-column prop="app_id" label="APPID" width="80">
            <template #default="{ row }">
              0x{{ (row.app_id ?? 0).toString(16).toUpperCase().padStart(4, '0') }}
            </template>
          </el-table-column>
          <el-table-column prop="interface" label="接口" width="100" />
          <el-table-column prop="dst_mac" label="目标MAC" width="140" />
          <el-table-column label="数据集" width="80" align="center">
            <template #default="{ row }">
              {{ row.entry_count }}
            </template>
          </el-table-column>
          <el-table-column label="stNum/sqNum" width="120" align="center">
            <template #default="{ row }">
              {{ row.st_num }}/{{ row.sq_num }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_running ? 'success' : 'info'" size="small">
                {{ row.is_running ? '运行中' : '已停止' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="仿真" width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="row.simulation ? 'warning' : ''" size="small">
                {{ row.simulation ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button-group>
                <el-button
                  v-if="!row.is_running"
                  type="success"
                  size="small"
                  @click="startPublisher(row.id)"
                >
                  启动
                </el-button>
                <el-button
                  v-else
                  type="warning"
                  size="small"
                  @click="stopPublisher(row.id)"
                >
                  停止
                </el-button>
                <el-button
                  type="primary"
                  size="small"
                  :disabled="!row.is_running"
                  @click="publishNow(row.id)"
                >
                  发布
                </el-button>
                <el-button
                  size="small"
                  @click="editPublisherEntries(row)"
                >
                  数据集
                </el-button>
                <el-button
                  type="danger"
                  size="small"
                  @click="deletePublisher(row.id)"
                >
                  删除
                </el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Receiver 面板 -->
      <el-tab-pane label="GOOSE 订阅" name="receiver">
        <div class="tab-header">
          <el-button type="primary" :icon="Plus" @click="showCreateReceiverDialog">
            新建 Receiver
          </el-button>
          <el-button :icon="Refresh" @click="refreshReceivers" :loading="loading">
            刷新
          </el-button>
        </div>

        <el-table :data="receivers" stripe border style="width: 100%" v-loading="loading">
          <el-table-column prop="interface" label="网络接口" width="140" />
          <el-table-column label="订阅数" width="90" align="center">
            <template #default="{ row }">
              {{ row.subscription_count }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_running ? 'success' : 'info'" size="small">
                {{ row.is_running ? '运行中' : '已停止' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="订阅详情" min-width="400">
            <template #default="{ row }">
              <div class="subscription-list">
                <el-tag
                  v-for="sub in row.subscriptions"
                  :key="sub.go_cb_ref"
                  :color="GOOSE_STATE_COLOR[sub.state] || '#909399'"
                  style="color: #fff; margin: 2px 4px 2px 0"
                  size="small"
                  @click="showSubscriptionDetail(sub)"
                  class="subscription-tag"
                >
                  {{ sub.go_cb_ref?.split('$').pop() || sub.go_cb_ref }}
                  ({{ GOOSE_STATE_LABEL[sub.state] || sub.state }})
                </el-tag>
                <span v-if="!row.subscriptions?.length" class="text-muted">暂无订阅</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button-group>
                <el-button
                  v-if="!row.is_running"
                  type="success"
                  size="small"
                  @click="startReceiver(row.id)"
                >
                  启动
                </el-button>
                <el-button
                  v-else
                  type="warning"
                  size="small"
                  @click="stopReceiver(row.id)"
                >
                  停止
                </el-button>
                <el-button size="small" @click="editReceiverSubscriptions(row)">
                  订阅管理
                </el-button>
                <el-button type="danger" size="small" @click="deleteReceiver(row.id)">
                  删除
                </el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- GOOSE 抓包 -->
      <el-tab-pane label="GOOSE 抓包" name="capture">
        <GooseCapture />
      </el-tab-pane>
    </el-tabs>

    <!-- 创建 Publisher 对话框 -->
    <el-dialog v-model="createPublisherVisible" title="新建 GOOSE Publisher" width="600px" destroy-on-close>
      <el-form :model="publisherForm" label-width="130px" :rules="publisherRules" ref="publisherFormRef">
        <el-form-item label="GoCBRef" prop="go_cb_ref">
          <el-input v-model="publisherForm.go_cb_ref" placeholder="如: LD0/LLN0$GO$gcb1" />
        </el-form-item>
        <el-form-item label="GoID" prop="go_id">
          <el-input v-model="publisherForm.go_id" placeholder="GOOSE 标识符" />
        </el-form-item>
        <el-form-item label="数据集引用" prop="data_set_ref">
          <el-input v-model="publisherForm.data_set_ref" placeholder="如: LD0/LLN0$dsGOOSE1" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="APPID" prop="app_id">
              <el-input-number v-model="publisherForm.app_id" :min="0" :max="65535" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="网络接口" prop="interface">
              <el-input v-model="publisherForm.interface" placeholder="如: eth0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="存活时间(ms)" prop="time_allowed_to_live">
              <el-input-number v-model="publisherForm.time_allowed_to_live" :min="100" :max="60000" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="配置修订号" prop="conf_rev">
              <el-input-number v-model="publisherForm.conf_rev" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="VLAN ID">
              <el-input-number v-model="publisherForm.vlan_id" :min="0" :max="4095" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="VLAN优先级">
              <el-input-number v-model="publisherForm.vlan_prio" :min="0" :max="7" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="仿真模式">
              <el-switch v-model="publisherForm.simulation" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="数据集条目">
          <div class="entry-list">
            <div v-for="(entry, idx) in publisherForm.entries" :key="idx" class="entry-row">
              <el-input v-model="entry.name" placeholder="名称" style="width: 120px" />
              <el-select v-model="entry.iec_type" style="width: 130px">
                <el-option v-for="opt in GOOSE_IEC_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-switch v-if="entry.iec_type === 'boolean'" v-model="entry.value" />
              <el-input-number v-else-if="entry.iec_type === 'integer'" v-model="entry.value" :controls="false" style="width: 100px" />
              <el-input-number v-else-if="entry.iec_type === 'float'" v-model="entry.value" :controls="false" :precision="2" style="width: 100px" />
              <el-input v-else v-model="entry.value" style="width: 100px" />
              <el-button type="danger" :icon="Delete" circle size="small" @click="publisherForm.entries.splice(idx, 1)" />
            </div>
            <el-button :icon="Plus" size="small" @click="addPublisherEntry">添加条目</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createPublisherVisible = false">取消</el-button>
        <el-button type="primary" @click="createPublisher" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <!-- 创建 Receiver 对话框 -->
    <el-dialog v-model="createReceiverVisible" title="新建 GOOSE Receiver" width="500px" destroy-on-close>
      <el-form :model="receiverForm" label-width="100px">
        <el-form-item label="网络接口" required>
          <el-input v-model="receiverForm.interface" placeholder="如: eth0" />
        </el-form-item>
        <el-form-item label="订阅列表">
          <div class="entry-list">
            <div v-for="(sub, idx) in receiverForm.subscriptions" :key="idx" class="entry-row">
              <el-input v-model="sub.go_cb_ref" placeholder="GoCBRef (如 LD0/LLN0$GO$gcb1)" style="flex: 1" />
              <el-input-number v-model="sub.app_id" :min="0" :max="65535" placeholder="APPID" style="width: 120px" />
              <el-button type="danger" :icon="Delete" circle size="small" @click="receiverForm.subscriptions.splice(idx, 1)" />
            </div>
            <el-button :icon="Plus" size="small" @click="addReceiverSubscription">添加订阅</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createReceiverVisible = false">取消</el-button>
        <el-button type="primary" @click="createReceiver" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <!-- 数据集编辑对话框 -->
    <el-dialog v-model="entryEditorVisible" :title="`数据集编辑 - ${editingPublisher?.go_cb_ref || ''}`" width="700px" destroy-on-close>
      <el-table :data="editingEntries" border size="small">
        <el-table-column label="序号" width="60" align="center">
          <template #default="{ $index }">{{ $index }}</template>
        </el-table-column>
        <el-table-column label="名称" width="150">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" :disabled="row._new !== true" placeholder="条目名称" />
          </template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-select v-model="row.iec_type" size="small" :disabled="row._new !== true">
              <el-option v-for="opt in GOOSE_IEC_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="值" min-width="150">
          <template #default="{ row }">
            <el-switch v-if="row.iec_type === 'boolean'" v-model="row.value" @change="onEntryValueChange(row)" />
            <el-input-number v-else-if="row.iec_type === 'integer'" v-model="row.value" size="small" @change="onEntryValueChange(row)" />
            <el-input-number v-else-if="row.iec_type === 'float'" v-model="row.value" :precision="2" size="small" @change="onEntryValueChange(row)" />
            <el-input v-else v-model="row.value" size="small" @change="onEntryValueChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button type="danger" :icon="Delete" circle size="small" @click="removeEntry($index)" />
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 12px; display: flex; gap: 8px">
        <el-button :icon="Plus" size="small" @click="addEntryToEditor">添加条目</el-button>
      </div>
      <template #footer>
        <el-button @click="entryEditorVisible = false">关闭</el-button>
        <el-button type="primary" @click="saveNewEntries" :loading="savingEntries">保存新增条目</el-button>
      </template>
    </el-dialog>

    <!-- 订阅管理对话框 -->
    <el-dialog v-model="subManagerVisible" :title="`订阅管理 - ${editingReceiver?.interface || ''}`" width="700px" destroy-on-close>
      <div class="tab-header">
        <el-button type="primary" :icon="Plus" size="small" @click="showAddSubscriptionForm = true" v-if="!editingReceiver?.is_running">
          添加订阅
        </el-button>
        <el-alert v-else type="warning" :closable="false" style="margin-bottom: 12px">
          Receiver 运行中，无法修改订阅。请先停止 Receiver。
        </el-alert>
      </div>

      <div v-if="showAddSubscriptionForm" style="margin-bottom: 12px; padding: 12px; border: 1px solid #EBEEF5; border-radius: 4px;">
        <el-form :inline="true" size="small">
          <el-form-item label="GoCBRef">
            <el-input v-model="newSubForm.go_cb_ref" placeholder="如: LD0/LLN0$GO$gcb1" style="width: 250px" />
          </el-form-item>
          <el-form-item label="APPID">
            <el-input-number v-model="newSubForm.app_id" :min="0" :max="65535" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="newSubForm.description" style="width: 150px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="addSubscription">确认</el-button>
            <el-button @click="showAddSubscriptionForm = false">取消</el-button>
          </el-form-item>
        </el-form>
      </div>

      <el-table :data="editingReceiver?.subscriptions || []" border size="small">
        <el-table-column prop="go_cb_ref" label="GoCBRef" min-width="250" show-overflow-tooltip />
        <el-table-column label="APPID" width="80">
          <template #default="{ row }">
            {{ row.app_id != null ? '0x' + row.app_id.toString(16).toUpperCase().padStart(4, '0') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="GoID" width="100" prop="go_id" />
        <el-table-column label="stNum" width="70" align="center" prop="st_num" />
        <el-table-column label="sqNum" width="70" align="center" prop="sq_num" />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :color="GOOSE_STATE_COLOR[row.state] || '#909399'" style="color: #fff" size="small">
              {{ GOOSE_STATE_LABEL[row.state] || row.state }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据值" min-width="200">
          <template #default="{ row }">
            <div v-if="row.data_values?.length" class="data-values">
              <span v-for="dv in row.data_values" :key="dv.index" class="data-value-item">
                {{ dv.value }}
              </span>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center" v-if="!editingReceiver?.is_running">
          <template #default="{ row }">
            <el-button type="danger" :icon="Delete" circle size="small" @click="removeSubscription(row.go_cb_ref)" />
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 订阅详情对话框 -->
    <el-dialog v-model="subDetailVisible" title="GOOSE 订阅详情" width="500px">
      <el-descriptions :column="2" border v-if="selectedSubscription">
        <el-descriptions-item label="GoCBRef" :span="2">{{ selectedSubscription.go_cb_ref }}</el-descriptions-item>
        <el-descriptions-item label="GoID">{{ selectedSubscription.go_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="APPID">
          {{ selectedSubscription.app_id != null ? '0x' + selectedSubscription.app_id.toString(16).toUpperCase().padStart(4, '0') : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="数据集引用" :span="2">{{ selectedSubscription.data_set_ref || '-' }}</el-descriptions-item>
        <el-descriptions-item label="stNum">{{ selectedSubscription.st_num }}</el-descriptions-item>
        <el-descriptions-item label="sqNum">{{ selectedSubscription.sq_num }}</el-descriptions-item>
        <el-descriptions-item label="confRev">{{ selectedSubscription.conf_rev }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :color="GOOSE_STATE_COLOR[selectedSubscription.state]" style="color: #fff" size="small">
            {{ GOOSE_STATE_LABEL[selectedSubscription.state] || selectedSubscription.state }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="存活时间(ms)">{{ selectedSubscription.time_allowed_to_live }}</el-descriptions-item>
        <el-descriptions-item label="目标MAC">{{ selectedSubscription.dst_mac || '-' }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ selectedSubscription.description || '-' }}</el-descriptions-item>
      </el-descriptions>
      <h4 style="margin: 16px 0 8px">数据集值</h4>
      <el-table :data="selectedSubscription?.data_values || []" border size="small">
        <el-table-column label="序号" width="60" align="center" prop="index" />
        <el-table-column label="类型" width="100" prop="type" />
        <el-table-column label="值" prop="value" />
      </el-table>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Delete } from '@element-plus/icons-vue'
import GooseCapture from './GooseCapture.vue'
import {
  getGoosePublishers, getGooseReceivers,
  createGoosePublisher, deleteGoosePublisher,
  startGoosePublisher, stopGoosePublisher, publishGooseNow,
  createGooseReceiver, deleteGooseReceiver,
  startGooseReceiver, stopGooseReceiver,
  addGooseSubscription, removeGooseSubscription,
  addGoosePublisherEntry, updateGoosePublisherEntry, deleteGoosePublisherEntry,
} from '@/api/gooseApi'
import {
  GOOSE_STATE_COLOR, GOOSE_STATE_LABEL, GOOSE_IEC_TYPE_OPTIONS,
} from '@/constants/protocol'
import type {
  GoosePublisherStatus, GooseReceiverStatus, GooseSubscriptionStatus,
} from '@/api/gooseApi'

// ===== 通用状态 =====
const loading = ref(false)
const creating = ref(false)
const activeTab = ref('publisher')
let refreshTimer: ReturnType<typeof setInterval> | null = null

// ===== Publisher 状态 =====
const publishers = ref<GoosePublisherStatus[]>([])
const createPublisherVisible = ref(false)
const publisherFormRef = ref()
const publisherForm = reactive({
  interface: 'eth0',
  go_cb_ref: '',
  go_id: '',
  data_set_ref: '',
  app_id: 0x0001,
  conf_rev: 1,
  time_allowed_to_live: 1000,
  vlan_id: 0,
  vlan_prio: 4,
  simulation: true,
  entries: [] as { name: string; value: any; iec_type: string }[],
})
const publisherRules = {
  go_cb_ref: [{ required: true, message: '请输入 GoCBRef', trigger: 'blur' }],
  interface: [{ required: true, message: '请输入网络接口', trigger: 'blur' }],
}

// ===== Receiver 状态 =====
const receivers = ref<GooseReceiverStatus[]>([])
const createReceiverVisible = ref(false)
const receiverForm = reactive({
  interface: 'eth0',
  subscriptions: [] as { go_cb_ref: string; app_id: number | null; description: string }[],
})

// ===== 数据集编辑 =====
const entryEditorVisible = ref(false)
const editingPublisher = ref<GoosePublisherStatus | null>(null)
const editingEntries = ref<{ name: string; value: any; iec_type: string; _new?: boolean }[]>([])
const savingEntries = ref(false)

/** 检查名称是否已存在于条目列表中 */
function hasDuplicateName(name: string, excludeIndex?: number): boolean {
  return editingEntries.value.some((e, i) => e.name === name && i !== excludeIndex)
}

// ===== 订阅管理 =====
const subManagerVisible = ref(false)
const editingReceiver = ref<GooseReceiverStatus | null>(null)
const showAddSubscriptionForm = ref(false)
const newSubForm = reactive({
  go_cb_ref: '',
  app_id: null as number | null,
  description: '',
})

// ===== 订阅详情 =====
const subDetailVisible = ref(false)
const selectedSubscription = ref<GooseSubscriptionStatus | null>(null)

// ===== 刷新数据 =====
async function refreshPublishers() {
  loading.value = true
  try {
    publishers.value = await getGoosePublishers()
  } catch (e) {
    console.error('刷新 GOOSE Publisher 失败:', e)
  } finally {
    loading.value = false
  }
}

async function refreshReceivers() {
  loading.value = true
  try {
    receivers.value = await getGooseReceivers()
  } catch (e) {
    console.error('刷新 GOOSE Receiver 失败:', e)
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await Promise.all([refreshPublishers(), refreshReceivers()])
}

// ===== Publisher 操作 =====
function showCreatePublisherDialog() {
  Object.assign(publisherForm, {
    interface: 'eth0',
    go_cb_ref: '',
    go_id: '',
    data_set_ref: '',
    app_id: 0x0001,
    conf_rev: 1,
    time_allowed_to_live: 1000,
    vlan_id: 0,
    vlan_prio: 4,
    simulation: true,
    entries: [],
  })
  createPublisherVisible.value = true
}

function addPublisherEntry() {
  publisherForm.entries.push({ name: '', value: false, iec_type: 'boolean' })
}

async function createPublisher() {
  creating.value = true
  try {
    await createGoosePublisher({
      ...publisherForm,
      dst_mac: null,
    })
    ElMessage.success('GOOSE Publisher 创建成功')
    createPublisherVisible.value = false
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function startPublisher(id: string) {
  try {
    const ok = await startGoosePublisher(id)
    if (ok) ElMessage.success('启动成功')
    else ElMessage.error('启动失败')
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || '启动失败')
  }
}

async function stopPublisher(id: string) {
  try {
    const ok = await stopGoosePublisher(id)
    if (ok) ElMessage.success('已停止')
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || '停止失败')
  }
}

async function publishNow(id: string) {
  try {
    const ok = await publishGooseNow(id)
    if (ok) ElMessage.success('GOOSE 报文已发布')
    else ElMessage.error('发布失败')
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || '发布失败')
  }
}

async function deletePublisher(id: string) {
  try {
    await ElMessageBox.confirm('确定删除此 GOOSE Publisher?', '确认', { type: 'warning' })
    await deleteGoosePublisher(id)
    ElMessage.success('已删除')
    await refreshPublishers()
  } catch { /* cancelled */ }
}

// ===== 数据集编辑 =====
function editPublisherEntries(pub: GoosePublisherStatus) {
  editingPublisher.value = pub
  editingEntries.value = (pub.entries || []).map(e => ({ ...e, _new: false }))
  entryEditorVisible.value = true
}

function addEntryToEditor() {
  // 去重检查：新条目名称不能为空，也不能与现有条目重名
  const existingNames = editingEntries.value.map(e => e.name).filter(Boolean)
  // 空条目检查：如果已有未填名称的新条目，不允许再添加
  const hasBlank = editingEntries.value.some(e => e._new && !e.name)
  if (hasBlank) {
    ElMessage.warning('请先填写新增条目的名称')
    return
  }
  editingEntries.value.push({ name: '', value: false, iec_type: 'boolean', _new: true })
}

async function removeEntry(index: number) {
  if (editingPublisher.value) {
    const entry = editingEntries.value[index]
    if (entry._new) {
      // 本地新增未保存的条目，直接移除即可
      editingEntries.value.splice(index, 1)
      return
    }
    try {
      await deleteGoosePublisherEntry(editingPublisher.value.id, index)
      editingEntries.value.splice(index, 1)
      await refreshPublishers()
    } catch (e: any) {
      ElMessage.error(e?.message || '删除条目失败')
    }
  }
}

async function onEntryValueChange(row: any) {
  if (editingPublisher.value && row._new !== true && row.index !== undefined) {
    try {
      await updateGoosePublisherEntry(editingPublisher.value.id, row.index, row.value)
    } catch (e: any) {
      ElMessage.error(e?.message || '更新值失败')
    }
  }
}

async function saveNewEntries() {
  if (!editingPublisher.value) return
  const newEntries = editingEntries.value.filter(e => e._new && e.name)
  if (newEntries.length === 0) {
    ElMessage.info('没有新增条目需要保存')
    return
  }
  // 去重检查
  for (const entry of newEntries) {
    if (hasDuplicateName(entry.name)) {
      ElMessage.warning(`条目名称 "${entry.name}" 已存在，请修改后重试`)
      return
    }
  }
  savingEntries.value = true
  try {
    for (const entry of newEntries) {
      await addGoosePublisherEntry(editingPublisher.value.id, entry.name, entry.value, entry.iec_type)
    }
    ElMessage.success(`已保存 ${newEntries.length} 个新条目`)
    await refreshPublishers()
    // 重新打开编辑器刷新数据
    const pub = publishers.value.find(p => p.id === editingPublisher.value?.id)
    if (pub) {
      editingEntries.value = (pub.entries || []).map(e => ({ ...e, _new: false }))
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '保存新增条目失败')
  } finally {
    savingEntries.value = false
  }
}

// ===== Receiver 操作 =====
function showCreateReceiverDialog() {
  Object.assign(receiverForm, {
    interface: 'eth0',
    subscriptions: [],
  })
  createReceiverVisible.value = true
}

function addReceiverSubscription() {
  receiverForm.subscriptions.push({ go_cb_ref: '', app_id: null, description: '' })
}

async function createReceiver() {
  creating.value = true
  try {
    await createGooseReceiver({
      interface: receiverForm.interface,
      subscriptions: receiverForm.subscriptions.map(s => ({
        go_cb_ref: s.go_cb_ref,
        app_id: s.app_id,
        dst_mac: null,
        description: s.description,
      })),
    })
    ElMessage.success('GOOSE Receiver 创建成功')
    createReceiverVisible.value = false
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function startReceiver(id: string) {
  try {
    const ok = await startGooseReceiver(id)
    if (ok) ElMessage.success('启动成功')
    else ElMessage.error('启动失败')
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || '启动失败')
  }
}

async function stopReceiver(id: string) {
  try {
    const ok = await stopGooseReceiver(id)
    if (ok) ElMessage.success('已停止')
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || '停止失败')
  }
}

async function deleteReceiver(id: string) {
  try {
    await ElMessageBox.confirm('确定删除此 GOOSE Receiver?', '确认', { type: 'warning' })
    await deleteGooseReceiver(id)
    ElMessage.success('已删除')
    await refreshReceivers()
  } catch { /* cancelled */ }
}

// ===== 订阅管理 =====
function editReceiverSubscriptions(recv: GooseReceiverStatus) {
  editingReceiver.value = recv
  showAddSubscriptionForm.value = false
  subManagerVisible.value = true
}

async function addSubscription() {
  if (!editingReceiver.value || !newSubForm.go_cb_ref) return
  try {
    await addGooseSubscription(editingReceiver.value.id, {
      go_cb_ref: newSubForm.go_cb_ref,
      app_id: newSubForm.app_id,
      dst_mac: null,
      description: newSubForm.description,
    })
    ElMessage.success('订阅添加成功')
    showAddSubscriptionForm.value = false
    Object.assign(newSubForm, { go_cb_ref: '', app_id: null, description: '' })
    await refreshReceivers()
    // 更新编辑中的 receiver
    editingReceiver.value = receivers.value.find(r => r.id === editingReceiver.value?.id) || editingReceiver.value
  } catch (e: any) {
    ElMessage.error(e?.message || '添加订阅失败')
  }
}

async function removeSubscription(goCbRef: string) {
  if (!editingReceiver.value) return
  try {
    await removeGooseSubscription(editingReceiver.value.id, goCbRef)
    ElMessage.success('订阅已移除')
    await refreshReceivers()
    editingReceiver.value = receivers.value.find(r => r.id === editingReceiver.value?.id) || editingReceiver.value
  } catch (e: any) {
    ElMessage.error(e?.message || '移除订阅失败')
  }
}

function showSubscriptionDetail(sub: GooseSubscriptionStatus) {
  selectedSubscription.value = sub
  subDetailVisible.value = true
}


// ===== 生命周期 =====
onMounted(() => {
  refreshAll()
  // 每5秒自动刷新
  refreshTimer = setInterval(refreshAll, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped lang="scss">
.goose-manager {
  padding: 16px;

  @include bp.respond-to('medium-down') {
    padding: 12px;
  }

  @include bp.respond-to('small') {
    padding: 10px;
  }
}

.tab-header {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 12px;

  @include bp.respond-to('small') {
    flex-wrap: wrap;
    justify-content: flex-start;
  }
}

.entry-list {
  width: 100%;
}

.entry-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;

  @include bp.respond-to('small') {
    flex-wrap: wrap;
  }
}

.subscription-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.subscription-tag {
  cursor: pointer;
}

.data-values {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.data-value-item {
  display: inline-block;
  padding: 2px 6px;
  background: #f5f7fa;
  border-radius: 3px;
  font-size: 12px;
  font-family: monospace;
}

.text-muted {
  color: #909399;
  font-size: 12px;
}

/* 在 small 断点下表格操作列按钮组换行 */
@include bp.respond-to('small') {
  .el-button-group {
    flex-wrap: wrap;
    gap: 2px;

    .el-button {
      margin: 0;
    }
  }
}
</style>



