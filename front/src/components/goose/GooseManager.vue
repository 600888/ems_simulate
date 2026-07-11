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
          <el-table-column :label="$t('common.operation')" width="340" fixed="right">
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
                <el-button size="small" :disabled="row.is_running" @click="showEditPublisherDialog(row)">
                  {{ $t('common.edit') }}
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
                <el-button size="small" :disabled="row.is_running" @click="showEditReceiverDialog(row)">
                  {{ $t('common.edit') }}
                </el-button>
                <el-button type="danger" size="small" @click="deleteReceiver(row.id)">
                  {{ $t('common.delete') }}
                </el-button>
              </el-button-group>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 已发现的远端控制块 -->
      <el-tab-pane :label="$t('goose.discovered')" name="discovered">
        <div class="tab-header">
          <el-button type="primary" :disabled="!discovered.length" @click="importDiscoveredSubscriptions">
            {{ $t('goose.subscribe') }}
          </el-button>
          <el-button :icon="Refresh" @click="refreshDiscovered" :loading="loading">
            {{ $t('goose.refresh') }}
          </el-button>
        </div>
        <el-table :data="discovered" stripe border style="width: 100%">
          <el-table-column prop="go_cb_ref" label="GoCBRef" min-width="240" show-overflow-tooltip />
          <el-table-column prop="go_id" label="GoID" width="120" show-overflow-tooltip />
          <el-table-column prop="app_id" label="APPID" width="90">
            <template #default="{ row }">
              {{ row.app_id != null ? '0x' + row.app_id.toString(16).toUpperCase().padStart(4, '0') : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="data_set_ref" label="DataSet" min-width="200" show-overflow-tooltip />
          <el-table-column prop="conf_rev" label="confRev" width="90" align="center" />
          <el-table-column :label="$t('common.operation')" width="160" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="createPublisherFromDiscovered(row)">
                {{ $t('goose.newPublisher') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- GOOSE 抓包 -->
      <el-tab-pane :label="$t('goose.captureTitle')" name="capture">
        <GooseCapture :channel-id="props.channelId || 0" />
      </el-tab-pane>
    </el-tabs>

    <!-- 创建 Publisher 对话框 -->
    <el-dialog v-model="createPublisherVisible" :title="configEditingId ? $t('common.edit') : $t('goose.newPublisher')" width="600px" destroy-on-close>
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
        <el-form-item label="Destination MAC">
          <el-input v-model="publisherForm.dst_mac" placeholder="01-0C-CD-01-00-01" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="$t('goose.appId')" prop="app_id">
              <el-input-number v-model="publisherForm.app_id" :min="0" :max="65535" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('goose.interface')" prop="interface">
              <el-select v-model="publisherForm.interface" :placeholder="$t('goose.interfacePlaceholder')" style="width: 100%">
                <el-option v-for="item in networkInterfaces" :key="item.id" :value="item.id"
                  :label="`${item.display_name}${item.ipv4?.[0] ? ` (${item.ipv4[0]})` : ''}`" />
              </el-select>
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
        <el-button type="primary" @click="savePublisherConfig" :loading="creating">{{ configEditingId ? $t('common.save') : $t('goose.create') }}</el-button>
      </template>
    </el-dialog>

    <!-- 创建 Receiver 对话框 -->
    <el-dialog v-model="createReceiverVisible" :title="receiverEditingId ? $t('common.edit') : $t('goose.newReceiver')" width="500px" destroy-on-close>
      <el-form :model="receiverForm" label-width="100px">
        <el-form-item label="Name" required>
          <el-input v-model="receiverForm.name" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="receiverForm.description" />
        </el-form-item>
        <el-form-item :label="$t('goose.iface')" required>
          <el-select v-model="receiverForm.interface" :placeholder="$t('goose.interfacePlaceholder')" style="width: 100%">
            <el-option v-for="item in networkInterfaces" :key="item.id" :value="item.id"
              :label="`${item.display_name}${item.ipv4?.[0] ? ` (${item.ipv4[0]})` : ''}`" />
          </el-select>
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
        <el-form-item label="Auto Start">
          <el-switch v-model="receiverForm.auto_start" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createReceiverVisible = false">{{ $t('goose.cancel') }}</el-button>
        <el-button type="primary" @click="saveReceiverConfig" :loading="creating">{{ receiverEditingId ? $t('common.save') : $t('goose.create') }}</el-button>
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
            <el-input v-model="row.name" size="small" :disabled="editingPublisher?.is_running" :placeholder="$t('goose.entryNamePlaceholder')" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('goose.entryType')" width="130">
          <template #default="{ row }">
            <el-select v-model="row.iec_type" size="small" :disabled="editingPublisher?.is_running">
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
              <el-button type="danger" :icon="Delete" circle size="small" :disabled="editingPublisher?.is_running" @click="removeEntry($index)" />
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 12px; display: flex; gap: 8px">
        <el-button :icon="Plus" size="small" :disabled="editingPublisher?.is_running" @click="addEntryToEditor">{{ $t('goose.addEntry') }}</el-button>
      </div>
      <template #footer>
        <el-button @click="entryEditorVisible = false">{{ $t('goose.close') }}</el-button>
        <el-button type="primary" :disabled="editingPublisher?.is_running" @click="saveNewEntries" :loading="savingEntries">{{ $t('goose.saveEntries') }}</el-button>
      </template>
    </el-dialog>

    <!-- 订阅管理对话框 -->
    <el-dialog v-model="subManagerVisible" :title="$t('goose.subscriptionManager') + ' - ' + (editingReceiver?.interface || '')" width="700px" destroy-on-close>
      <div class="tab-header">
        <el-button type="primary" :icon="Plus" @click="showAddSubscriptionForm = true" v-if="!editingReceiver?.is_running">
          {{ $t('goose.addSub') }}
        </el-button>
        <el-alert v-else type="warning" :closable="false" style="margin-bottom: 12px">
          {{ $t('goose.receiverRunning') }}
        </el-alert>
      </div>

      <div v-if="showAddSubscriptionForm" style="margin-bottom: 14px; padding: 16px 20px; border: 1px solid #DCDFE6; border-radius: 4px;">
        <el-form :inline="true">
          <el-form-item :label="$t('goose.subGoCbRef')">
            <el-input v-model="newSubForm.go_cb_ref" :placeholder="$t('goose.subGoCbRefPlaceholder')" style="width: 280px" />
          </el-form-item>
          <el-form-item :label="$t('goose.subAppId')">
            <el-input-number v-model="newSubForm.app_id" :min="0" :max="65535" :style="{width:'140px'}" controls-position="right" />
          </el-form-item>
          <el-form-item :label="$t('goose.subDescription')">
            <el-input v-model="newSubForm.description" style="width: 180px" />
          </el-form-item>
          <el-form-item label="Destination MAC">
            <el-input v-model="newSubForm.dst_mac" placeholder="01-0C-CD-01-00-01" style="width: 190px" />
          </el-form-item>
          <el-form-item :label="$t('goose.dataSetRef')">
            <el-input v-model="newSubForm.data_set_ref" style="width: 220px" />
          </el-form-item>
          <el-form-item :label="$t('goose.confRev')">
            <el-input-number v-model="newSubForm.conf_rev" :min="0" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="addSubscription">{{ $t('goose.confirm') }}</el-button>
            <el-button @click="showAddSubscriptionForm = false">{{ $t('goose.cancel') }}</el-button>
          </el-form-item>
        </el-form>
      </div>

      <template v-if="editingReceiver?.subscriptions?.length">
        <div v-for="sub in editingReceiver.subscriptions" :key="sub.go_cb_ref" class="sub-card">
          <div class="sub-card__row">
            <span class="sub-card__label">{{ $t('goose.subGoCbRef') }}:</span>
            <span class="sub-card__value cell-wrap">{{ sub.go_cb_ref }}</span>
          </div>
          <div class="sub-card__row">
            <span class="sub-card__label">{{ $t('goose.subAppId') }}:</span>
            <span class="sub-card__value">{{ sub.app_id != null ? '0x' + sub.app_id.toString(16).toUpperCase().padStart(4, '0') : '-' }}</span>
            <span class="sub-card__label" style="margin-left:16px">{{ $t('goose.goId') }}:</span>
            <span class="sub-card__value">{{ sub.go_id || '-' }}</span>
            <span class="sub-card__label" style="margin-left:16px">状态号:</span>
            <span class="sub-card__value">{{ sub.st_num }}</span>
            <span class="sub-card__label" style="margin-left:16px">顺序号:</span>
            <span class="sub-card__value">{{ sub.sq_num }}</span>
          </div>
          <div class="sub-card__row">
            <span class="sub-card__label">{{ $t('goose.subState') }}:</span>
            <el-tag :color="GOOSE_STATE_COLOR[sub.state] || '#909399'" style="color: #fff">
              {{ GOOSE_STATE_LABEL[sub.state] || sub.state }}
            </el-tag>
            <span class="sub-card__label" style="margin-left:20px">{{ $t('goose.subDataValue') }}:</span>
            <span class="sub-card__value">
              <template v-if="sub.data_values?.length">
                <span v-for="dv in sub.data_values" :key="dv.index" class="data-value-item">{{ dv.value }}</span>
              </template>
              <span v-else class="text-muted">-</span>
            </span>
            <el-button v-if="!editingReceiver?.is_running" type="danger" :icon="Delete" circle
              style="margin-left:auto; flex-shrink:0"
              @click="removeSubscription(sub.go_cb_ref)" />
            <el-button v-if="!editingReceiver?.is_running" size="small" @click="editSubscription(sub)">
              {{ $t('common.edit') }}
            </el-button>
          </div>
        </div>
      </template>
      <span v-else class="text-muted" style="display:block;text-align:center;padding:24px">{{ $t('goose.noSubscription') }}</span>
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
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Delete } from '@element-plus/icons-vue'
import GooseCapture from './GooseCapture.vue'
import {
  getGoosePublishers, getGooseReceivers, getDiscoveredGoose, importDiscoveredGoose,
  createGoosePublisher, deleteGoosePublisher,
  startGoosePublisher, stopGoosePublisher, publishGooseNow,
  createGooseReceiver, deleteGooseReceiver,
  startGooseReceiver, stopGooseReceiver,
  addGooseSubscription, removeGooseSubscription,
  updateGoosePublisherEntry, deleteGoosePublisherEntry,
  getGooseNetworkInterfaces, updateGoosePublisher,
  replaceGoosePublisherEntries,
  replaceGooseSubscriptions,
  updateGooseReceiver,
} from '@/api/gooseApi'
import {
  GOOSE_STATE_COLOR, GOOSE_STATE_LABEL, GOOSE_IEC_TYPE_OPTIONS,
} from '@/constants/protocol'
import type {
  GoosePublisherStatus, GooseReceiverStatus, GooseSubscriptionStatus,
  DiscoveredGooseItem, NetworkInterfaceInfo,
} from '@/api/gooseApi'

const { t } = useI18n()

// ===== Props =====
const props = defineProps<{
  channelId?: number
}>()

// ===== 通用状态 =====
const loading = ref(false)
const networkInterfaces = ref<NetworkInterfaceInfo[]>([])
const creating = ref(false)
const activeTab = ref('publisher')
let refreshTimer: ReturnType<typeof setInterval> | null = null

// ===== Publisher 状态 =====
const publishers = ref<GoosePublisherStatus[]>([])

// ===== 发现的远端控制块 =====
const discovered = ref<DiscoveredGooseItem[]>([])
const createPublisherVisible = ref(false)
const configEditingId = ref<string | null>(null)
const publisherFormRef = ref()
const publisherForm = reactive({
  interface: 'eth0',
  go_cb_ref: '',
  go_id: '',
  data_set_ref: '',
  dst_mac: '',
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
const receiverEditingId = ref<string | null>(null)
const receiverForm = reactive({
  interface: 'eth0',
  name: 'default',
  description: '',
  auto_start: false,
  subscriptions: [] as { go_cb_ref: string; app_id: number | null; description: string }[],
})

// ===== 数据集编辑 =====
const entryEditorVisible = ref(false)
const editingPublisher = ref<GoosePublisherStatus | null>(null)
const editingEntries = ref<{ name: string; value: any; iec_type: string; _new?: boolean }[]>([])
const savingEntries = ref(false)

// ===== 订阅管理 =====
const subManagerVisible = ref(false)
const editingReceiver = ref<GooseReceiverStatus | null>(null)
const showAddSubscriptionForm = ref(false)
const newSubForm = reactive({
  go_cb_ref: '',
  app_id: null as number | null,
  description: '',
  dst_mac: '',
  data_set_ref: '',
  conf_rev: 0,
})
const editingSubRef = ref<string | null>(null)

// ===== 订阅详情 =====
const subDetailVisible = ref(false)
const selectedSubscription = ref<GooseSubscriptionStatus | null>(null)

// ===== 刷新数据 =====
async function refreshPublishers() {
  loading.value = true
  try {
    if (!props.channelId) return
    publishers.value = await getGoosePublishers(props.channelId)
  } catch (e) {
    console.error('刷新 GOOSE Publisher 失败:', e)
  } finally {
    loading.value = false
  }
}

async function refreshReceivers() {
  loading.value = true
  try {
    if (!props.channelId) return
    receivers.value = await getGooseReceivers(props.channelId)
  } catch (e) {
    console.error('刷新 GOOSE Receiver 失败:', e)
  } finally {
    loading.value = false
  }
}

async function refreshDiscovered() {
  if (!props.channelId) {
    discovered.value = []
    return
  }
  try {
    discovered.value = await getDiscoveredGoose(props.channelId)
  } catch (e) {
    console.error('刷新发现的 GOOSE 控制块失败:', e)
  }
}

async function refreshAll() {
  await Promise.all([refreshPublishers(), refreshReceivers(), refreshDiscovered()])
}

// channelId 变化时只刷新当前设备；导入必须由用户显式确认。
watch(
  () => props.channelId,
  async (id) => {
    if (!id) return
    await refreshAll()
  },
  { immediate: true },
)

/** 基于发现的控制块快速创建 Publisher */
function createPublisherFromDiscovered(item: DiscoveredGooseItem) {
  configEditingId.value = null
  Object.assign(publisherForm, {
    interface: networkInterfaces.value[0]?.id || '',
    go_cb_ref: item.go_cb_ref,
    go_id: item.go_id || '',
    data_set_ref: item.data_set_ref || '',
    dst_mac: '',
    app_id: item.app_id ?? 0x0001,
    conf_rev: item.conf_rev || 1,
    time_allowed_to_live: 1000,
    vlan_id: 0,
    vlan_prio: 4,
    simulation: true,
    entries: [],
  })
  createPublisherVisible.value = true
}

// ===== Publisher 操作 =====
function showCreatePublisherDialog() {
  configEditingId.value = null
  Object.assign(publisherForm, {
    interface: networkInterfaces.value[0]?.id || '',
    go_cb_ref: '',
    go_id: '',
    data_set_ref: '',
    dst_mac: '',
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

async function importDiscoveredSubscriptions() {
  if (!props.channelId || !discovered.value.length) return
  try {
    await ElMessageBox.confirm(`将 ${discovered.value.length} 个控制块导入当前设备订阅？`, t('common.confirm'))
    const interfaceId = receiverForm.interface || networkInterfaces.value[0]?.id
    if (!interfaceId) throw new Error(t('goose.interfaceRequired'))
    await importDiscoveredGoose(props.channelId, interfaceId)
    ElMessage.success(t('goose.createSuccess'))
    await refreshReceivers()
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close' && e?.message) ElMessage.error(e.message)
  }
}

function showEditPublisherDialog(pub: GoosePublisherStatus) {
  configEditingId.value = pub.id
  Object.assign(publisherForm, {
    interface: pub.interface,
    go_cb_ref: pub.go_cb_ref,
    go_id: pub.go_id,
    data_set_ref: pub.data_set_ref,
    dst_mac: pub.dst_mac || '',
    app_id: pub.app_id,
    conf_rev: pub.conf_rev,
    time_allowed_to_live: pub.time_allowed_to_live,
    vlan_id: pub.vlan_id,
    vlan_prio: pub.vlan_prio,
    simulation: pub.simulation,
    entries: [],
  })
  createPublisherVisible.value = true
}

function parseMac(value: string): number[] | null {
  if (!value.trim()) return null
  const parts = value.trim().split(/[:-]/)
  if (parts.length !== 6 || parts.some(part => !/^[0-9a-fA-F]{2}$/.test(part))) {
    throw new Error('Destination MAC 格式应为 01-0C-CD-01-00-01')
  }
  return parts.map(part => Number.parseInt(part, 16))
}

async function savePublisherConfig() {
  if (!props.channelId) return
  if (!configEditingId.value) {
    await createPublisher()
    return
  }
  creating.value = true
  try {
    await updateGoosePublisher(configEditingId.value, {
      channel_id: props.channelId,
      interface: publisherForm.interface,
      go_cb_ref: publisherForm.go_cb_ref,
      go_id: publisherForm.go_id,
      data_set_ref: publisherForm.data_set_ref,
      dst_mac: parseMac(publisherForm.dst_mac),
      app_id: publisherForm.app_id,
      conf_rev: publisherForm.conf_rev,
      time_allowed_to_live: publisherForm.time_allowed_to_live,
      vlan_id: publisherForm.vlan_id,
      vlan_prio: publisherForm.vlan_prio,
      simulation: publisherForm.simulation,
    })
    ElMessage.success(t('common.success'))
    createPublisherVisible.value = false
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.createFailed'))
  } finally {
    creating.value = false
  }
}

function addPublisherEntry() {
  publisherForm.entries.push({ name: '', value: false, iec_type: 'boolean' })
}

async function createPublisher() {
  creating.value = true
  try {
    await createGoosePublisher({
      interface: publisherForm.interface,
      go_cb_ref: publisherForm.go_cb_ref,
      go_id: publisherForm.go_id,
      data_set_ref: publisherForm.data_set_ref,
      app_id: publisherForm.app_id,
      conf_rev: publisherForm.conf_rev,
      time_allowed_to_live: publisherForm.time_allowed_to_live,
      vlan_id: publisherForm.vlan_id,
      vlan_prio: publisherForm.vlan_prio,
      simulation: publisherForm.simulation,
      entries: publisherForm.entries,
      channel_id: props.channelId || 0,
      dst_mac: parseMac(publisherForm.dst_mac),
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
    const ok = await startGoosePublisher(props.channelId || 0, id)
    if (ok) ElMessage.success(t('goose.startSuccess'))
    else ElMessage.error(t('goose.publishFailed'))
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.publishFailed'))
  }
}

async function stopPublisher(id: string) {
  try {
    const ok = await stopGoosePublisher(props.channelId || 0, id)
    if (ok) ElMessage.success(t('goose.stopSuccess'))
    await refreshPublishers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.publishFailed'))
  }
}

async function publishNow(id: string) {
  try {
    const ok = await publishGooseNow(props.channelId || 0, id)
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
    await deleteGoosePublisher(props.channelId || 0, id)
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
  if (editingEntries.value.some(entry => !entry.name.trim())) {
    ElMessage.warning(t('goose.addEntryNameRequired'))
    return
  }
  if (new Set(editingEntries.value.map(entry => entry.name)).size !== editingEntries.value.length) {
    ElMessage.warning(t('goose.entryNameExists', { name: '' }))
    return
  }
  savingEntries.value = true
  try {
    await replaceGoosePublisherEntries(
      props.channelId || 0,
      editingPublisher.value.id,
      editingEntries.value.map(({ name, value, iec_type }) => ({ name, value, iec_type })),
    )
    ElMessage.success(t('goose.entriesSaved', { count: editingEntries.value.length }))
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
  receiverEditingId.value = null
  Object.assign(receiverForm, {
    interface: networkInterfaces.value[0]?.id || '',
    name: 'default',
    description: '',
    auto_start: false,
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
      channel_id: props.channelId || 0,
      interface: receiverForm.interface,
      name: receiverForm.name,
      description: receiverForm.description,
      auto_start: receiverForm.auto_start,
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
    const ok = await startGooseReceiver(props.channelId || 0, id)
    if (ok) ElMessage.success(t('goose.startSuccess'))
    else ElMessage.error(t('goose.createFailed'))
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.createFailed'))
  }
}

async function stopReceiver(id: string) {
  try {
    const ok = await stopGooseReceiver(props.channelId || 0, id)
    if (ok) ElMessage.success(t('goose.stopSuccess'))
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.publishFailed'))
  }
}

async function deleteReceiver(id: string) {
  try {
    await ElMessageBox.confirm(t('goose.receiverDeleteConfirm'), t('common.confirm'), { type: 'warning' })
    await deleteGooseReceiver(props.channelId || 0, id)
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

function showEditReceiverDialog(receiver: GooseReceiverStatus) {
  receiverEditingId.value = receiver.id
  Object.assign(receiverForm, {
    interface: receiver.interface,
    name: receiver.name || 'default',
    description: receiver.description || '',
    auto_start: receiver.auto_start || false,
    subscriptions: [],
  })
  createReceiverVisible.value = true
}

async function saveReceiverConfig() {
  if (!receiverEditingId.value) {
    await createReceiver()
    return
  }
  creating.value = true
  try {
    await updateGooseReceiver(props.channelId || 0, receiverEditingId.value, {
      interface: receiverForm.interface,
      name: receiverForm.name,
      description: receiverForm.description,
      auto_start: receiverForm.auto_start,
    })
    ElMessage.success(t('common.success'))
    createReceiverVisible.value = false
    await refreshReceivers()
  } catch (e: any) {
    ElMessage.error(e?.message || t('goose.createFailed'))
  } finally {
    creating.value = false
  }
}

function editSubscription(sub: GooseSubscriptionStatus) {
  editingSubRef.value = sub.go_cb_ref
  Object.assign(newSubForm, {
    go_cb_ref: sub.go_cb_ref,
    app_id: sub.app_id,
    description: sub.description || '',
    dst_mac: sub.dst_mac || '',
    data_set_ref: sub.data_set_ref || '',
    conf_rev: sub.conf_rev || 0,
  })
  showAddSubscriptionForm.value = true
}

async function addSubscription() {
  if (!editingReceiver.value || !newSubForm.go_cb_ref) return
  try {
    if (editingSubRef.value) {
      const subscriptions = editingReceiver.value.subscriptions.map(sub => sub.go_cb_ref === editingSubRef.value ? {
        go_cb_ref: newSubForm.go_cb_ref,
        app_id: newSubForm.app_id,
        dst_mac: parseMac(newSubForm.dst_mac),
        description: newSubForm.description,
        data_set_ref: newSubForm.data_set_ref,
        conf_rev: newSubForm.conf_rev,
      } : {
        go_cb_ref: sub.go_cb_ref,
        app_id: sub.app_id,
        dst_mac: parseMac(sub.dst_mac || ''),
        description: sub.description,
        data_set_ref: sub.data_set_ref,
        conf_rev: sub.conf_rev,
      })
      await replaceGooseSubscriptions(props.channelId || 0, editingReceiver.value.id, subscriptions)
      editingSubRef.value = null
      await refreshReceivers()
      editingReceiver.value = receivers.value.find(r => r.id === editingReceiver.value?.id) || editingReceiver.value
      showAddSubscriptionForm.value = false
      return
    }
    await addGooseSubscription(editingReceiver.value.id, {
      go_cb_ref: newSubForm.go_cb_ref,
      app_id: newSubForm.app_id,
      dst_mac: parseMac(newSubForm.dst_mac),
      description: newSubForm.description,
      data_set_ref: newSubForm.data_set_ref,
      conf_rev: newSubForm.conf_rev,
    })
    ElMessage.success(t('goose.subscriptionAdded'))
    showAddSubscriptionForm.value = false
    Object.assign(newSubForm, { go_cb_ref: '', app_id: null, description: '', dst_mac: '', data_set_ref: '', conf_rev: 0 })
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
onMounted(async () => {
  networkInterfaces.value = (await getGooseNetworkInterfaces()).filter(item => item.supports_raw_ethernet)
  const firstInterface = networkInterfaces.value[0]?.id
  if (firstInterface) {
    publisherForm.interface = firstInterface
    receiverForm.interface = firstInterface
  }
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

.sub-card {
  border: 1px solid #DCDFE6;
  border-radius: 4px;
  padding: 16px 20px;
  margin-bottom: 14px;
}

.sub-card__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.sub-card__row:last-child {
  margin-bottom: 0;
}

.sub-card__label {
  font-size: 14px;
  color: #909399;
  white-space: nowrap;
  flex-shrink: 0;
}

.sub-card__value {
  font-size: 14px;
  color: #303133;
}

.cell-wrap {
  word-break: break-all;
  white-space: normal;
  line-height: 1.4;
}

.data-value-item {
  display: inline-block;
  padding: 3px 10px;
  background: #f0f2f5;
  border-radius: 4px;
  font-size: 14px;
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



