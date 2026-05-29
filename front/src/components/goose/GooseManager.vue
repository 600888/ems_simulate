<template>
  <div class="goose-manager">
    <el-tabs v-model="activeTab" class="goose-tabs">
      <!-- Publisher 面板 -->
      <el-tab-pane :label="$t('goose.publish')" name="publisher">
        <div class="tab-header">
          <el-button type="primary" :icon="Plus" @click="showCreatePublisherDialog">
            {{ $t('goose.newPublisher') }}
          </el-button>
          <el-button :icon="Refresh" @click="refreshPublishers" :loading="loading">
            {{ $t('goose.refresh') }}
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
          <el-table-column prop="interface" label="Interface" width="100" />
          <el-table-column prop="dst_mac" label="Dest MAC" width="140" />
          <el-table-column :label="$t('goose.dataSet')" width="95" align="center">
            <template #default="{ row }">
              {{ row.entry_count }}
            </template>
          </el-table-column>
          <el-table-column label="stNum/sqNum" width="140" align="center">
            <template #default="{ row }">
              {{ row.st_num }}/{{ row.sq_num }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('goose.running')" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_running ? 'success' : 'info'" size="small">
                {{ row.is_running ? $t('goose.running') : $t('goose.stopped') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('goose.yes')" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.simulation ? 'warning' : ''" size="small">
                {{ row.simulation ? $t('goose.yes') : $t('goose.no') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.operation')" width="280" fixed="right">
            <template #default="{ row }">
              <el-button-group>
                <el-button
                  v-if="!row.is_running"
                  type="success"
                  size="small"
                  @click="startPublisher(row.id)"
                >
                  {{ $t('goose.start') }}
                </el-button>
                <el-button
                  v-else
                  type="warning"
                  size="small"
                  @click="stopPublisher(row.id)"
                >
                  {{ $t('goose.stop') }}
                </el-button>
                <el-button
                  type="primary"
                  size="small"
                  :disabled="!row.is_running"
                  @click="publishNow(row.id)"
                >
                  {{ $t('goose.publishAction') }}
                </el-button>
                <el-button
                  size="small"
                  @click="editPublisherEntries(row)"
                >
                  {{ $t('goose.dataSet') }}
                </el-button>
                <el-button
                  type="danger"
                  size="small"
                  @click="deletePublisher(row.id)"
                >
                  {{ $t('common.delete') }}
                </el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Receiver 面板 -->
      <el-tab-pane :label="$t('goose.subscribe')" name="receiver">
        <div class="tab-header">
          <el-button type="primary" :icon="Plus" @click="showCreateReceiverDialog">
            {{ $t('goose.newReceiver') }}
          </el-button>
          <el-button :icon="Refresh" @click="refreshReceivers" :loading="loading">
            {{ $t('goose.refresh') }}
          </el-button>
        </div>

        <el-table :data="receivers" stripe border style="width: 100%" v-loading="loading">
          <el-table-column prop="interface" :label="$t('goose.iface')" width="140" />
          <el-table-column label="Subscriptions" width="130" align="center">
            <template #default="{ row }">
              {{ row.subscription_count }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('goose.running')" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_running ? 'success' : 'info'" size="small">
                {{ row.is_running ? $t('goose.running') : $t('goose.stopped') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('device.subscribeNow')" min-width="400">
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
                <span v-if="!row.subscriptions?.length" class="text-muted">{{ $t('goose.noSubscription') }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.operation')" width="260" fixed="right">
            <template #default="{ row }">
              <el-button-group>
                <el-button
                  v-if="!row.is_running"
                  type="success"
                  size="small"
                  @click="startReceiver(row.id)"
                >
                  {{ $t('goose.start') }}
                </el-button>
                <el-button
                  v-else
                  type="warning"
                  size="small"
                  @click="stopReceiver(row.id)"
                >
                  {{ $t('goose.stop') }}
                </el-button>
                <el-button size="small" @click="editReceiverSubscriptions(row)">
                  {{ $t('goose.subscriptionManager') }}
                </el-button>
                <el-button type="danger" size="small" @click="deleteReceiver(row.id)">
                  {{ $t('common.delete') }}
                </el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- GOOSE 抓包 -->
      <el-tab-pane :label="$t('goose.captureTitle')" name="capture">
        <GooseCapture />
      </el-tab-pane>
    </el-tabs>

    <!-- 创建 Publisher 对话框 -->
    <el-dialog v-model="createPublisherVisible" :title="$t('goose.newPublisher')" width="600px" destroy-on-close>
      <el-form :model="publisherForm" label-width="130px" :rules="publisherRules" ref="publisherFormRef">
        <el-form-item :label="$t('goose.goCbRef')" prop="go_cb_ref">
          <el-input v-model="publisherForm.go_cb_ref" :placeholder="$t('goose.createPublisherPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('goose.goId')" prop="go_id">
          <el-input v-model="publisherForm.go_id" :placeholder="$t('goose.goIdPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('goose.dataSetRef')" prop="data_set_ref">
          <el-input v-model="publisherForm.data_set_ref" :placeholder="$t('goose.dataSetRefPlaceholder')" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('goose.appId')" prop="app_id">
              <el-input-number v-model="publisherForm.app_id" :min="0" :max="65535" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('goose.interface')" prop="interface">
              <el-input v-model="publisherForm.interface" :placeholder="$t('goose.interfacePlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('goose.timeAllowedToLive')" prop="time_allowed_to_live">
              <el-input-number v-model="publisherForm.time_allowed_to_live" :min="100" :max="60000" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('goose.confRev')" prop="conf_rev">
              <el-input-number v-model="publisherForm.conf_rev" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item :label="$t('goose.vlanId')">
              <el-input-number v-model="publisherForm.vlan_id" :min="0" :max="4095" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('goose.vlanPrio')">
              <el-input-number v-model="publisherForm.vlan_prio" :min="0" :max="7" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('goose.simulation')">
              <el-switch v-model="publisherForm.simulation" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="$t('goose.entryList')">
          <div class="entry-list">
            <div v-for="(entry, idx) in publisherForm.entries" :key="idx" class="entry-row">
              <el-input v-model="entry.name" :placeholder="$t('goose.entryNamePlaceholder')" style="width: 120px" />
              <el-select v-model="entry.iec_type" style="width: 130px">
                <el-option v-for="opt in GOOSE_IEC_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <el-switch v-if="entry.iec_type === 'boolean'" v-model="entry.value" />
              <el-input-number v-else-if="entry.iec_type === 'integer'" v-model="entry.value" :controls="false" style="width: 100px" />
              <el-input-number v-else-if="entry.iec_type === 'float'" v-model="entry.value" :controls="false" :precision="2" style="width: 100px" />
              <el-input v-else v-model="entry.value" style="width: 100px" />
              <el-button type="danger" :icon="Delete" circle size="small" @click="publisherForm.entries.splice(idx, 1)" />
            </div>
            <el-button :icon="Plus" size="small" @click="addPublisherEntry">{{ $t('goose.addEntry') }}</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createPublisherVisible = false">{{ $t('goose.cancel') }}</el-button>
        <el-button type="primary" @click="createPublisher" :loading="creating">{{ $t('goose.create') }}</el-button>
      </template>
    </el-dialog>

    <!-- 创建 Receiver 对话框 -->
    <el-dialog v-model="createReceiverVisible" :title="$t('goose.newReceiver')" width="500px" destroy-on-close>
      <el-form :model="receiverForm" label-width="100px">
        <el-form-item :label="$t('goose.iface')" required>
          <el-input v-model="receiverForm.interface" :placeholder="$t('goose.interfacePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('goose.subscriptions')">
          <div class="entry-list">
            <div v-for="(sub, idx) in receiverForm.subscriptions" :key="idx" class="entry-row">
              <el-input v-model="sub.go_cb_ref" :placeholder="$t('goose.subPlaceholder')" style="flex: 1" />
              <el-input-number v-model="sub.app_id" :min="0" :max="65535" :placeholder="$t('goose.appIdPlaceholder')" style="width: 120px" />
              <el-button type="danger" :icon="Delete" circle size="small" @click="receiverForm.subscriptions.splice(idx, 1)" />
            </div>
            <el-button :icon="Plus" size="small" @click="addReceiverSubscription">{{ $t('goose.addSub') }}</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createReceiverVisible = false">{{ $t('goose.cancel') }}</el-button>
        <el-button type="primary" @click="createReceiver" :loading="creating">{{ $t('goose.create') }}</el-button>
      </template>
    </el-dialog>

    <!-- 数据集编辑对话框 -->
    <el-dialog v-model="entryEditorVisible" :title="$t('goose.dataSet') + ' - ' + (editingPublisher?.go_cb_ref || '')" width="700px" destroy-on-close>
      <el-table :data="editingEntries" border size="small">
        <el-table-column :label="$t('goose.seqNum')" width="75" align="center">
          <template #default="{ $index }">{{ $index }}</template>
        </el-table-column>
        <el-table-column :label="$t('goose.entryName')" width="150">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" :disabled="row._new !== true" :placeholder="$t('goose.entryNamePlaceholder')" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('goose.entryType')" width="130">
          <template #default="{ row }">
            <el-select v-model="row.iec_type" size="small" :disabled="row._new !== true">
              <el-option v-for="opt in GOOSE_IEC_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="$t('goose.entryValue')" min-width="150">
          <template #default="{ row }">
            <el-switch v-if="row.iec_type === 'boolean'" v-model="row.value" @change="onEntryValueChange(row)" />
            <el-input-number v-else-if="row.iec_type === 'integer'" v-model="row.value" size="small" @change="onEntryValueChange(row)" />
            <el-input-number v-else-if="row.iec_type === 'float'" v-model="row.value" :precision="2" size="small" @change="onEntryValueChange(row)" />
            <el-input v-else v-model="row.value" size="small" @change="onEntryValueChange(row)" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('goose.entryOperation')" width="90" align="center">
          <template #default="{ $index }">
            <el-button type="danger" :icon="Delete" circle size="small" @click="removeEntry($index)" />
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 12px; display: flex; gap: 8px">
        <el-button :icon="Plus" size="small" @click="addEntryToEditor">{{ $t('goose.addEntry') }}</el-button>
      </div>
      <template #footer>
        <el-button @click="entryEditorVisible = false">{{ $t('goose.close') }}</el-button>
        <el-button type="primary" @click="saveNewEntries" :loading="savingEntries">{{ $t('goose.saveEntries') }}</el-button>
      </template>
    </el-dialog>

    <!-- 订阅管理对话框 -->
    <el-dialog v-model="subManagerVisible" :title="$t('goose.subscriptionManager') + ' - ' + (editingReceiver?.interface || '')" width="700px" destroy-on-close>
      <div class="tab-header">
        <el-button type="primary" :icon="Plus" size="small" @click="showAddSubscriptionForm = true" v-if="!editingReceiver?.is_running">
          {{ $t('goose.addSub') }}
        </el-button>
        <el-alert v-else type="warning" :closable="false" style="margin-bottom: 12px">
          {{ $t('goose.receiverRunning') }}
        </el-alert>
      </div>

      <div v-if="showAddSubscriptionForm" style="margin-bottom: 12px; padding: 12px; border: 1px solid #EBEEF5; border-radius: 4px;">
        <el-form :inline="true" size="small">
          <el-form-item :label="$t('goose.subGoCbRef')">
            <el-input v-model="newSubForm.go_cb_ref" :placeholder="$t('goose.subGoCbRefPlaceholder')" style="width: 250px" />
          </el-form-item>
          <el-form-item :label="$t('goose.subAppId')">
            <el-input-number v-model="newSubForm.app_id" :min="0" :max="65535" />
          </el-form-item>
          <el-form-item :label="$t('goose.subDescription')">
            <el-input v-model="newSubForm.description" style="width: 150px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="addSubscription">{{ $t('goose.confirm') }}</el-button>
            <el-button @click="showAddSubscriptionForm = false">{{ $t('goose.cancel') }}</el-button>
          </el-form-item>
        </el-form>
      </div>

      <el-table :data="editingReceiver?.subscriptions || []" border size="small">
        <el-table-column prop="go_cb_ref" :label="$t('goose.subGoCbRef')" min-width="250" show-overflow-tooltip />
        <el-table-column :label="$t('goose.subAppId')" width="100">
          <template #default="{ row }">
            {{ row.app_id != null ? '0x' + row.app_id.toString(16).toUpperCase().padStart(4, '0') : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('goose.goId')" width="110" prop="go_id" />
        <el-table-column :label="$t('goose.stNum')" width="85" align="center" prop="st_num" />
        <el-table-column :label="$t('goose.sqNum')" width="85" align="center" prop="sq_num" />
        <el-table-column :label="$t('goose.subState')" width="95" align="center">
          <template #default="{ row }">
            <el-tag :color="GOOSE_STATE_COLOR[row.state] || '#909399'" style="color: #fff" size="small">
              {{ GOOSE_STATE_LABEL[row.state] || row.state }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('goose.subDataValue')" min-width="200">
          <template #default="{ row }">
            <div v-if="row.data_values?.length" class="data-values">
              <span v-for="dv in row.data_values" :key="dv.index" class="data-value-item">
                {{ dv.value }}
              </span>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('goose.subOperation')" width="90" align="center" v-if="!editingReceiver?.is_running">
          <template #default="{ row }">
            <el-button type="danger" :icon="Delete" circle size="small" @click="removeSubscription(row.go_cb_ref)" />
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 订阅详情对话框 -->
    <el-dialog v-model="subDetailVisible" :title="$t('goose.subscriptionDetail')" width="500px">
      <el-descriptions :column="2" border v-if="selectedSubscription">
        <el-descriptions-item :label="$t('goose.goCbRef')" :span="2">{{ selectedSubscription.go_cb_ref }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.goId')">{{ selectedSubscription.go_id || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.appId')">
          {{ selectedSubscription.app_id != null ? '0x' + selectedSubscription.app_id.toString(16).toUpperCase().padStart(4, '0') : '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('goose.dataSetRef')" :span="2">{{ selectedSubscription.data_set_ref || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.stNum')">{{ selectedSubscription.st_num }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.sqNum')">{{ selectedSubscription.sq_num }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.confRev')">{{ selectedSubscription.conf_rev }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.subState')">
          <el-tag :color="GOOSE_STATE_COLOR[selectedSubscription.state]" style="color: #fff" size="small">
            {{ GOOSE_STATE_LABEL[selectedSubscription.state] || selectedSubscription.state }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('goose.timeAllowedToLive')">{{ selectedSubscription.time_allowed_to_live }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.dstMac')">{{ selectedSubscription.dst_mac || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('goose.description')" :span="2">{{ selectedSubscription.description || '-' }}</el-descriptions-item>
      </el-descriptions>
      <h4 style="margin: 16px 0 8px">{{ $t('goose.dataSetValues') }}</h4>
      <el-table :data="selectedSubscription?.data_values || []" border size="small">
        <el-table-column :label="$t('goose.seqNum')" width="75" align="center" prop="index" />
        <el-table-column :label="$t('goose.entryType')" width="100" prop="type" />
        <el-table-column :label="$t('goose.entryValue')" prop="value" />
      </el-table>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
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

const { t } = useI18n()

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
  go_cb_ref: [{ required: true, message: t('goose.goCbRefRequired'), trigger: 'blur' }],
  interface: [{ required: true, message: t('goose.interfaceRequired'), trigger: 'blur' }],
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
    ElMessage.success(t('goose.createSuccess'))
    createPublisherVisible.value = false
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.createFailed'))
  } finally {
    creating.value = false
  }
}

async function startPublisher(id: string) {
  try {
    const ok = await startGoosePublisher(id)
    if (ok) ElMessage.success(t('goose.startSuccess'))
    else ElMessage.error(t('goose.publishFailed'))
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.publishFailed'))
  }
}

async function stopPublisher(id: string) {
  try {
    const ok = await stopGoosePublisher(id)
    if (ok) ElMessage.success(t('goose.stopSuccess'))
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.publishFailed'))
  }
}

async function publishNow(id: string) {
  try {
    const ok = await publishGooseNow(id)
    if (ok) ElMessage.success(t('goose.publishSuccess'))
    else ElMessage.error(t('goose.publishFailed'))
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.publishFailed'))
  }
}

async function deletePublisher(id: string) {
  try {
    await ElMessageBox.confirm(t('goose.deleteConfirm'), t('common.confirm'), { type: 'warning' })
    await deleteGoosePublisher(id)
    ElMessage.success(t('goose.deleted'))
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
    ElMessage.warning(t('goose.addEntryNameRequired'))
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
      ElMessage.error(e?.message || t('goose.deleteEntryFailed'))
    }
  }
}

async function onEntryValueChange(row: any) {
  if (editingPublisher.value && row._new !== true && row.index !== undefined) {
    try {
      await updateGoosePublisherEntry(editingPublisher.value.id, row.index, row.value)
    } catch (e: any) {
      ElMessage.error(e?.message || t('goose.updateValueFailed'))
    }
  }
}

async function saveNewEntries() {
  if (!editingPublisher.value) return
  const newEntries = editingEntries.value.filter(e => e._new && e.name)
  if (newEntries.length === 0) {
    ElMessage.info(t('goose.noNewEntries'))
    return
  }
  // 去重检查
  for (const entry of newEntries) {
    if (hasDuplicateName(entry.name)) {
      ElMessage.warning(t('goose.entryNameExists', { name: entry.name }))
      return
    }
  }
  savingEntries.value = true
  try {
    for (const entry of newEntries) {
      await addGoosePublisherEntry(editingPublisher.value.id, entry.name, entry.value, entry.iec_type)
    }
    ElMessage.success(t('goose.entriesSaved', { count: newEntries.length }))
    await refreshPublishers()
    // 重新打开编辑器刷新数据
    const pub = publishers.value.find(p => p.id === editingPublisher.value?.id)
    if (pub) {
      editingEntries.value = (pub.entries || []).map(e => ({ ...e, _new: false }))
    }
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.saveEntriesFailed'))
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
    ElMessage.success(t('goose.createSuccess'))
    createReceiverVisible.value = false
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.createFailed'))
  } finally {
    creating.value = false
  }
}

async function startReceiver(id: string) {
  try {
    const ok = await startGooseReceiver(id)
    if (ok) ElMessage.success(t('goose.startSuccess'))
    else ElMessage.error(t('goose.createFailed'))
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.createFailed'))
  }
}

async function stopReceiver(id: string) {
  try {
    const ok = await stopGooseReceiver(id)
    if (ok) ElMessage.success(t('goose.stopSuccess'))
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.publishFailed'))
  }
}

async function deleteReceiver(id: string) {
  try {
    await ElMessageBox.confirm(t('goose.receiverDeleteConfirm'), t('common.confirm'), { type: 'warning' })
    await deleteGooseReceiver(id)
    ElMessage.success(t('goose.deleted'))
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
    ElMessage.success(t('goose.subscriptionAdded'))
    showAddSubscriptionForm.value = false
    Object.assign(newSubForm, { go_cb_ref: '', app_id: null, description: '' })
    await refreshReceivers()
    // 更新编辑中的 receiver
    editingReceiver.value = receivers.value.find(r => r.id === editingReceiver.value?.id) || editingReceiver.value
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.createFailed'))
  }
}

async function removeSubscription(goCbRef: string) {
  if (!editingReceiver.value) return
  try {
    await removeGooseSubscription(editingReceiver.value.id, goCbRef)
    ElMessage.success(t('goose.subscriptionRemoved'))
    await refreshReceivers()
    editingReceiver.value = receivers.value.find(r => r.id === editingReceiver.value?.id) || editingReceiver.value
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.removeSubscriptionFailed'))
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

:deep(.el-table thead th .cell) {
  white-space: nowrap;
}

/* 表格所有列居中 */
:deep(.el-table .cell) {
  text-align: center;
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



