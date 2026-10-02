<template>
  <div v-loading="loading" class="pubsub-workspace">
    <OpcUaPageHeading
      :title="t('opcua.pubsub')"
      :description="
        t(
          role === 'server'
            ? 'opcua.pubsubServerDescription'
            : 'opcua.pubsubClientDescription',
        )
      "
    >
      <el-tag :type="running ? 'success' : 'info'">{{
        t(running ? "opcua.running" : "opcua.stopped")
      }}</el-tag>
      <el-button
        v-if="role === 'server'"
        @click="
          publisherSettingsTab = 'publisher';
          publisherSettings = true;
        "
        >{{ t("opcua.publisherSettings") }}</el-button
      >
      <el-button v-else @click="subscriptionSettings = true">{{
        t("opcua.subscriptionSettings")
      }}</el-button>
    </OpcUaPageHeading>
    <el-tabs v-model="kind" class="data-tabs">
      <el-tab-pane :label="t('opcua.realtimeData')" name="realtime" />
      <el-tab-pane :label="t('opcua.history')" name="history" />
      <el-tab-pane :label="t('opcua.events')" name="events" />
    </el-tabs>
    <el-alert
      v-if="pageError"
      :title="pageError"
      type="error"
      :closable="false"
    />
    <div class="pubsub-columns">
      <OpcUaNodeTree
        :channel-id="channelId"
        :role="role"
        :running="running"
        :revision="revision"
        @add="addNodes"
      />
      <main class="pubsub-content">
        <div
          class="drop-zone"
          :class="{ over: dragging }"
          @dragover="dragOver"
          @dragleave="dragging = false"
          @drop="drop"
        >
          <span class="drop-symbol">＋</span>
          <div>
            <strong>{{
              t(
                `opcua.drop${kind === "realtime" ? "Variables" : kind === "history" ? "History" : "Events"}`,
              )
            }}</strong>
            <p>
              {{
                t(
                  kind === "history"
                    ? "opcua.dropHistoryHint"
                    : "opcua.dropDraftHint",
                )
              }}
            </p>
          </div>
          <el-tag v-if="adding">{{ t("opcua.checkingNodes") }}</el-tag>
        </div>
        <el-alert
          v-if="feedback.length"
          type="warning"
          :title="feedback.join('；')"
          closable
          @close="feedback = []"
        />

        <div v-show="kind === 'realtime'" class="workspace-pane">
          <section class="ua-section">
            <div class="ua-section-heading">
              <h3>
                {{
                  t(
                    role === "server"
                      ? "opcua.publishedFields"
                      : "opcua.monitoredItems",
                  )
                }}
              </h3>
              <el-radio-group v-model="realtimeView" size="small">
                <el-radio-button value="table">{{
                  t("opcua.tableView")
                }}</el-radio-button>
                <el-radio-button value="trend">{{
                  t("opcua.trend")
                }}</el-radio-button>
              </el-radio-group>
              <el-tag :type="realtimeRunning ? 'success' : 'info'">{{
                t(realtimeRunning ? "opcua.running" : "opcua.stopped")
              }}</el-tag>
            </div>
            <div class="ua-toolbar">
              <template v-if="role === 'client'"
                ><el-select
                  v-model="subscriptionIndex"
                  :disabled="adding || saving"
                  ><el-option
                    v-for="(subscription, index) in subscriptions"
                    :key="index"
                    :value="index"
                    :label="subscription.id" /></el-select
                ><el-button @click="newSubscription">{{
                  t("opcua.addSubscription")
                }}</el-button
                ><el-button
                  type="danger"
                  plain
                  :disabled="!currentSubscription || saving"
                  @click="deleteSubscription"
                  >{{ t("opcua.delete") }}</el-button
                ></template
              >
              <template v-else
                ><el-select
                  v-model="variableWriterId"
                  :disabled="adding || saving"
                  ><el-option
                    v-for="writer in variableWriters"
                    :key="writer.writer_id"
                    :value="writer.writer_id"
                    :label="writer.name" /></el-select
                ><el-button @click="openDatasetSettings">{{
                  t("opcua.datasetSettings")
                }}</el-button></template
              >
              <el-button
                :loading="saving"
                :disabled="!ready || adding"
                @click="saveRealtime()"
                >{{ t("opcua.saveConfig") }}</el-button
              >
              <el-button
                type="primary"
                :loading="saving"
                :disabled="
                  !running || !ready || adding || !realtimeNodes.length
                "
                @click="saveRealtime(true)"
                >{{
                  t(
                    role === "server"
                      ? "opcua.startPublishing"
                      : "opcua.startSubscription",
                  )
                }}</el-button
              >
              <el-button
                :loading="saving"
                :disabled="
                  !ready ||
                  !(role === 'server'
                    ? publisher.enabled
                    : currentSubscription?.enabled)
                "
                @click="saveRealtime(false)"
                >{{
                  t(
                    role === "server"
                      ? "opcua.stopPublishing"
                      : "opcua.stopSubscription",
                  )
                }}</el-button
              >
            </div>
            <el-alert
              v-if="dirty"
              type="info"
              :title="t('opcua.pendingDraft')"
              :closable="false"
            />
            <el-alert
              v-if="runtimeError"
              type="error"
              :title="runtimeError"
              :closable="false"
            />
            <p v-if="role === 'server'" class="ua-muted">
              {{ publisher.publisher_id }} · {{ publisher.broker_url }} ·
              {{
                t("opcua.publishedCount", {
                  count: publisherStatus.published_count || 0,
                })
              }}
            </p>
            <el-table
              v-if="realtimeView === 'table'"
              :data="realtimeRows"
              stripe
              max-height="420"
              :empty-text="t('opcua.dragEmpty')"
            >
              <el-table-column
                :label="t('opcua.name')"
                min-width="160"
                show-overflow-tooltip
                ><template #default="{ row }"
                  ><strong>{{ row.browse_name }}</strong>
                  <div class="ua-code ua-muted">
                    {{ row.node_id }}
                  </div></template
                ></el-table-column
              >
              <el-table-column
                v-if="role === 'server'"
                :label="t('opcua.fieldAlias')"
                min-width="140"
                ><template #default="{ row }"
                  ><el-input
                    v-model="row.field.alias"
                    maxlength="128"
                    @input="dirty = true" /></template
              ></el-table-column>
              <el-table-column
                :label="t('opcua.value')"
                min-width="120"
                show-overflow-tooltip
                ><template #default="{ row }">{{
                  displayUaValue(row.snapshot?.value)
                }}</template></el-table-column
              >
              <el-table-column :label="t('opcua.dataType')" width="110"
                ><template #default="{ row }">{{
                  row.snapshot?.variant_type || row.data_type || "—"
                }}</template></el-table-column
              >
              <el-table-column :label="t('opcua.quality')" min-width="150"
                ><template #default="{ row }"
                  ><el-tag
                    v-if="row.snapshot"
                    :type="
                      realtimeRunning &&
                      row.snapshot.status_code?.startsWith('Good')
                        ? 'success'
                        : 'warning'
                    "
                    >{{ row.snapshot.status_code }}</el-tag
                  ><span v-else>—</span>
                  <div v-if="row.error" class="item-error">
                    {{ row.error }}
                  </div></template
                ></el-table-column
              >
              <el-table-column
                :label="t('opcua.sourceTimestamp')"
                min-width="195"
                ><template #default="{ row }">{{
                  row.snapshot?.source_timestamp || "—"
                }}</template></el-table-column
              >
              <el-table-column
                :label="t('opcua.actions')"
                width="125"
                fixed="right"
                ><template #default="{ row }"
                  ><el-button
                    v-if="role === 'client'"
                    link
                    @click="editMonitor(row.node_id)"
                    >{{ t("opcua.settings") }}</el-button
                  ><el-button
                    link
                    type="danger"
                    @click="removeRealtime(row.node_id)"
                    >{{ t("opcua.remove") }}</el-button
                  ></template
                ></el-table-column
              >
            </el-table>
            <div
              v-if="role === 'client' && subscriptionState"
              class="revision-line"
            >
              {{ t("opcua.revisedParameters") }}: {{ t("opcua.publishingMs") }}
              {{ subscriptionState.publishing_interval_ms }} ·
              {{ t("opcua.keepaliveCount") }}
              {{ subscriptionState.keepalive_count }} ·
              {{ t("opcua.lifetimeCount") }}
              {{ subscriptionState.lifetime_count }}
            </div>
          </section>
          <section v-if="realtimeView === 'trend'" class="ua-section">
            <div class="ua-section-heading">
              <h3>{{ t("opcua.trend") }}</h3>
              <el-select v-model="chartNode"
                ><el-option
                  v-for="node in realtimeNodes"
                  :key="node.node_id"
                  :value="node.node_id"
                  :label="node.browse_name"
              /></el-select>
            </div>
            <el-alert
              v-if="gap"
              type="warning"
              :title="t('opcua.streamGap')"
              :closable="false"
            /><OpcUaTrendPlot :title="chartNode" :points="chartPoints" />
            <p class="ua-muted">{{ t("opcua.liveHint") }}</p>
          </section>
        </div>

        <div v-show="kind === 'history'" class="workspace-pane">
          <section class="ua-section selected-nodes">
            <strong>{{ t("opcua.queryNodes") }}</strong
            ><el-tag
              v-for="node in historyNodes"
              :key="node.node_id"
              closable
              @close="
                historyNodes = historyNodes.filter(
                  (n) => n.node_id !== node.node_id,
                )
              "
              >{{ node.browse_name }}</el-tag
            ><span v-if="!historyNodes.length" class="ua-muted">{{
              t("opcua.dragEmpty")
            }}</span>
          </section>
          <OpcUaHistoryWorkspace
            :channel-id="channelId"
            :role="role"
            :running="running"
            :nodes="historyNodes"
            :revision="revision"
            @restore-nodes="restoreHistory"
          />
        </div>

        <div v-show="kind === 'events'" class="workspace-pane">
          <section class="ua-section">
            <div class="ua-section-heading">
              <h3>{{ t("opcua.eventSettings") }}</h3>
              <el-tag
                :type="
                  eventStatus.enabled && running && !eventStatus.error
                    ? 'success'
                    : 'info'
                "
                >{{
                  t(
                    eventStatus.enabled && running
                      ? "opcua.enabled"
                      : "opcua.disabled",
                  )
                }}</el-tag
              >
            </div>
            <div v-if="role === 'server'" class="ua-toolbar">
              <el-select v-model="eventWriterId" :disabled="adding || saving"
                ><el-option
                  v-for="writer in eventWriters"
                  :key="writer.writer_id"
                  :value="writer.writer_id"
                  :label="writer.name" /></el-select
              ><el-button @click="openDatasetSettings">{{
                t("opcua.datasetSettings")
              }}</el-button>
            </div>
            <div class="selected-nodes">
              <strong>{{ t("opcua.eventSources") }}</strong
              ><el-tag
                v-for="node in eventNodes"
                :key="node.node_id"
                closable
                @close="removeEventSource(node.node_id)"
                >{{ node.browse_name }}</el-tag
              >
            </div>
            <el-form label-position="top" class="event-options">
              <el-form-item :label="t('opcua.eventType')"
                ><el-input
                  v-model="eventsConfig.event_type"
                  placeholder="i=2041"
                  @input="eventsDirty = true"
              /></el-form-item>
              <el-form-item :label="t('opcua.minimumSeverity')"
                ><el-input-number
                  v-model="eventsConfig.minimum_severity"
                  :min="0"
                  :max="1000"
                  @change="eventsDirty = true"
              /></el-form-item>
              <el-form-item :label="t('opcua.keyword')"
                ><el-input
                  v-model="eventsConfig.message_filter"
                  clearable
                  maxlength="256"
                  @input="eventsDirty = true"
              /></el-form-item>
            </el-form>
            <h4>{{ t("opcua.returnedFields") }}</h4>
            <el-checkbox-group
              v-model="eventsConfig.returned_fields"
              @change="eventsDirty = true"
              ><el-checkbox
                v-for="field in EVENT_FIELDS"
                :key="field"
                :value="field"
                >{{ field }}</el-checkbox
              ></el-checkbox-group
            >
            <div class="ua-toolbar event-actions">
              <el-button
                :loading="saving"
                :disabled="!ready"
                @click="saveEvents()"
                >{{ t("opcua.saveConfig") }}</el-button
              ><el-button
                type="primary"
                :loading="saving"
                :disabled="!running || !ready || !eventNodes.length || adding"
                @click="saveEvents(true)"
                >{{
                  t(
                    role === "server"
                      ? "opcua.startPublishing"
                      : "opcua.startSubscription",
                  )
                }}</el-button
              ><el-button
                :loading="saving"
                :disabled="!ready || !eventsConfig.enabled"
                @click="saveEvents(false)"
                >{{ t("opcua.stop") }}</el-button
              >
            </div>
            <el-alert
              v-if="eventsDirty"
              type="info"
              :title="t('opcua.pendingDraft')"
              :closable="false"
            />
            <el-alert
              v-if="eventStatus.error"
              type="error"
              :title="String(eventStatus.error)"
              :closable="false"
            />
            <el-alert
              v-if="role === 'server' && eventPublisherError"
              type="error"
              :title="eventPublisherError"
              :closable="false"
            />
            <div v-if="role === 'server'" class="ua-toolbar emit-toolbar">
              <el-select v-model="emitSource"
                ><el-option
                  v-for="node in eventNodes"
                  :key="node.node_id"
                  :value="node.node_id"
                  :label="node.browse_name" /></el-select
              ><el-input
                v-model="eventMessage"
                :placeholder="t('opcua.eventMessage')"
                maxlength="1024"
              /><el-input-number
                v-model="emitSeverity"
                :min="0"
                :max="1000"
                :aria-label="t('opcua.severity')"
              /><el-button
                :loading="emitting"
                :disabled="
                  !running ||
                  !eventsConfig.enabled ||
                  !eventMessage.trim() ||
                  !emitSource
                "
                @click="triggerEvent"
                >{{ t("opcua.emitEvent") }}</el-button
              >
            </div>
          </section>
          <section class="ua-section">
            <div class="ua-section-heading">
              <h3>
                {{ t("opcua.receivedEvents") }} ({{ visibleEvents.length }})
              </h3>
              <el-button
                :disabled="!visibleEvents.length"
                @click="exportEvents"
                >{{ t("opcua.exportCsv") }}</el-button
              >
            </div>
            <div class="ua-toolbar">
              <el-input
                v-model="eventSearch"
                :placeholder="t('opcua.eventSearch')"
                clearable
              /><el-button @click="clearEvents">{{
                t("opcua.clear")
              }}</el-button>
            </div>
            <el-alert
              v-if="gap"
              type="warning"
              :title="t('opcua.streamGap')"
              :closable="false"
            />
            <el-table
              :data="visibleEvents"
              stripe
              max-height="400"
              highlight-current-row
              @row-click="eventDetail = $event"
            >
              <el-table-column
                v-for="field in eventsConfig.returned_fields"
                :key="field"
                :label="field"
                min-width="155"
                show-overflow-tooltip
                ><template #default="{ row }">{{
                  displayUaValue(row[field])
                }}</template></el-table-column
              >
            </el-table>
            <p class="ua-muted">{{ t("opcua.eventBufferHint") }}</p>
            <template v-if="eventDetail"
              ><h4>{{ t("opcua.eventDetails") }}</h4>
              <el-descriptions :column="1" border
                ><el-descriptions-item
                  v-for="(value, field) in eventDetail"
                  :key="field"
                  :label="String(field)"
                  >{{ displayUaValue(value) }}</el-descriptions-item
                ></el-descriptions
              ></template
            >
          </section>
        </div>
      </main>
    </div>

    <el-dialog
      v-model="subscriptionSettings"
      :title="t('opcua.subscriptionSettings')"
      width="min(600px,95vw)"
    >
      <el-form
        v-if="currentSubscription"
        label-position="top"
        class="subscription-options"
      >
        <el-form-item :label="t('opcua.subscriptionName')"
          ><el-input
            v-model="currentSubscription.id"
            maxlength="64"
            @input="dirty = true"
        /></el-form-item>
        <el-form-item :label="t('opcua.publishingMs')"
          ><el-input-number
            v-model="currentSubscription.publishing_interval_ms"
            :min="50"
            :max="3600000"
            @change="dirty = true"
        /></el-form-item>
        <el-form-item :label="t('opcua.keepaliveCount')"
          ><el-input-number
            v-model="currentSubscription.keepalive_count"
            :min="1"
            :max="10000"
            @change="dirty = true"
        /></el-form-item>
        <el-form-item :label="t('opcua.lifetimeCount')"
          ><el-input-number
            v-model="currentSubscription.lifetime_count"
            :min="3"
            :max="100000"
            @change="dirty = true"
        /></el-form-item>
        <el-form-item :label="t('opcua.reconnect')"
          ><el-switch
            v-model="subscriptionOptions.reconnect"
            @change="dirty = true"
        /></el-form-item>
      </el-form>
      <p class="ua-muted">{{ t("opcua.subscriptionHint") }}</p>
      <template #footer
        ><el-button @click="subscriptionSettings = false">{{
          t("opcua.applyDraft")
        }}</el-button></template
      >
    </el-dialog>
    <el-dialog
      v-model="monitorSettings"
      :title="t('opcua.itemSettings')"
      width="min(580px,95vw)"
    >
      <el-form
        v-if="editingMonitor"
        label-position="top"
        class="subscription-options"
      >
        <el-form-item label="NodeId"
          ><span class="ua-code">{{
            editingMonitor.node_id
          }}</span></el-form-item
        >
        <el-form-item :label="t('opcua.samplingMs')"
          ><el-input-number
            v-model="editingMonitor.sampling_interval_ms"
            :min="0"
            :max="3600000"
            @change="dirty = true"
        /></el-form-item>
        <el-form-item :label="t('opcua.queueSize')"
          ><el-input-number
            v-model="editingMonitor.queue_size"
            :min="1"
            :max="10000"
            @change="dirty = true"
        /></el-form-item>
        <el-form-item :label="t('opcua.monitoringMode')"
          ><el-select v-model="editingMonitor.mode" @change="dirty = true"
            ><el-option
              v-for="mode in ['Reporting', 'Sampling', 'Disabled']"
              :key="mode"
              :label="mode"
              :value="mode" /></el-select
        ></el-form-item>
        <el-form-item :label="t('opcua.deadband')"
          ><el-input-number
            v-model="editingMonitor.deadband"
            :min="0"
            @change="dirty = true"
        /></el-form-item> </el-form
      ><template #footer
        ><el-button @click="monitorSettings = false">{{
          t("opcua.applyDraft")
        }}</el-button></template
      >
    </el-dialog>
    <OpcUaPublisherSettings
      :visible="publisherSettings"
      :config="publisher"
      :initial-tab="publisherSettingsTab"
      :writer-id="kind === 'events' ? eventWriterId : variableWriterId"
      @close="publisherSettings = false"
      @apply="applyPublisher"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { showError } from "@/api/http";
import {
  getOpcUaFeatures,
  getOpcUaCapabilities,
  getOpcUaNodeCapabilities,
  listOpcUaVariables,
  saveOpcUaFeature,
  readOpcUaStream,
  emitOpcUaEvent,
  type OpcUaCapability,
  type OpcUaStreamEvent,
} from "@/api/opcuaApi";
import {
  DRAG_MIME,
  decodeUaDrag,
  defaultMonitor,
  defaultPublisher,
  defaultSubscription,
  defaultWriter,
  displayUaValue,
  downloadCsv,
  EVENT_FIELDS,
  nodeKey,
  rejectionReason,
  uniqueSelections,
  type DataKind,
  type MonitorItem,
  type UaPublisher,
  type UaSelection,
  type UaSubscription,
} from "@/utils/opcuaPubSub";
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import OpcUaNodeTree from "./OpcUaNodeTree.vue";
import OpcUaHistoryWorkspace from "./OpcUaHistoryWorkspace.vue";
import OpcUaPublisherSettings from "./OpcUaPublisherSettings.vue";
import OpcUaTrendPlot from "./OpcUaTrendPlot.vue";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
  active: boolean;
  revision?: number;
}>();
const { t } = useI18n();
const realtimeView = ref("table");
const publisherSettingsTab = ref<"publisher" | "datasets">("publisher");
function openDatasetSettings() {
  publisherSettingsTab.value = "datasets";
  publisherSettings.value = true;
}
const kind = ref<DataKind>("realtime"),
  loading = ref(false),
  saving = ref(false),
  adding = ref(false),
  ready = ref(false),
  dragging = ref(false);
const dirty = ref(false),
  eventsDirty = ref(false),
  pageError = ref(""),
  feedback = ref<string[]>([]);
const subscriptions = ref<UaSubscription[]>([defaultSubscription()]),
  subscriptionIndex = ref(0);
const subscriptionOptions = ref({
  reconnect: true,
  retry_min_s: 1,
  retry_max_s: 30,
});
const currentSubscription = computed(
  () => subscriptions.value[subscriptionIndex.value],
);
const publisher = ref<UaPublisher>(defaultPublisher(props.channelId)),
  variableWriterId = ref(1),
  eventWriterId = ref(2);
const variableWriters = computed(() =>
    publisher.value.writers.filter((w) => w.kind === "variables"),
  ),
  eventWriters = computed(() =>
    publisher.value.writers.filter((w) => w.kind === "events"),
  );
const variableWriter = computed(() =>
  variableWriters.value.find((w) => w.writer_id === variableWriterId.value),
);
const eventWriter = computed(() =>
  eventWriters.value.find((w) => w.writer_id === eventWriterId.value),
);
const nodeCache = ref<Record<string, UaSelection>>({}),
  historyNodes = ref<UaSelection[]>([]);
const eventsConfig = ref({
  enabled: false,
  source_node: "i=2253",
  source_nodes: [] as string[],
  event_type: "i=2041",
  minimum_severity: 0,
  message_filter: "",
  returned_fields: [
    "EventId",
    "SourceNode",
    "SourceName",
    "Time",
    "Severity",
    "Message",
  ],
});
const lookup = (id: string, nodeClass = "Variable"): UaSelection =>
  nodeCache.value[nodeKey(id)] || {
    node_id: id,
    browse_name: id,
    node_class: nodeClass,
  };
const realtimeNodes = computed(
  () =>
    (props.role === "server"
      ? variableWriter.value?.fields.map((f) => f.node_id)
      : currentSubscription.value?.items.map((i) => i.node_id) || []
    )?.map((id) => lookup(id)) || [],
);
const eventNodes = computed(() =>
  (props.role === "server"
    ? eventWriter.value?.source_nodes || []
    : eventsConfig.value.source_nodes
  ).map((id) => lookup(id, "Object")),
);
const publisherSettings = ref(false),
  subscriptionSettings = ref(false),
  monitorSettings = ref(false),
  editingMonitor = ref<MonitorItem>();
const caps = ref<OpcUaCapability[]>([]),
  records = ref<OpcUaStreamEvent[]>([]),
  gap = ref(false),
  connection = ref("");
const subscriptionStatus = computed(
  () => caps.value.find((c) => c.name === "subscriptions")?.details || {},
);
const subscriptionState = computed(() =>
  (
    subscriptionStatus.value.subscriptions as Record<string, any>[] | undefined
  )?.find((s) => s.id === currentSubscription.value?.id),
);
const publisherStatus = computed(
  () => caps.value.find((c) => c.name === "pubsub")?.details || {},
);
const eventStatus = computed(
  () => caps.value.find((c) => c.name === "events")?.details || {},
);
const eventPublisherError = computed(() =>
  String(
    publisherStatus.value.error ||
      (
        publisherStatus.value.writers as
          Record<string, { error?: string }> | undefined
      )?.[String(eventWriterId.value)]?.error ||
      caps.value.find((c) => c.name === "pubsub")?.reason ||
      "",
  ),
);
const realtimeRunning = computed(() => {
  const writerState = (
    publisherStatus.value.writers as
      Record<string, { error?: string; last_publish?: string }> | undefined
  )?.[String(variableWriterId.value)];
  return (
    props.running &&
    (props.role === "server"
      ? !!publisherStatus.value.connected &&
        !!writerState?.last_publish &&
        !writerState.error
      : !!subscriptionState.value?.running &&
        connection.value !== "disconnected")
  );
});
const runtimeError = computed(() => {
  if (props.role === "server") {
    const writers = publisherStatus.value.writers as
      Record<string, { error?: string }> | undefined;
    return String(
      publisherStatus.value.error ||
        writers?.[String(variableWriterId.value)]?.error ||
        caps.value.find((c) => c.name === "pubsub")?.reason ||
        "",
    );
  }
  return String(
    subscriptionState.value?.error || subscriptionStatus.value.error || "",
  );
});
const realtimeRecords = computed(() =>
  records.value.filter(
    (e) =>
      e.kind === "value" &&
      (props.role === "server"
        ? e.source === "pubsub" && e.writer_id === variableWriterId.value
        : e.subscription === currentSubscription.value?.id),
  ),
);
const realtimeRows = computed(() => {
  const latest = new Map<string, OpcUaStreamEvent>();
  realtimeRecords.value.forEach((e) => {
    if (e.node_id) latest.set(nodeKey(e.node_id), e);
  });
  return realtimeNodes.value.map((node) => {
    const state = (
      subscriptionState.value?.items as Record<string, any>[] | undefined
    )?.find((i) => nodeKey(i.node_id) === nodeKey(node.node_id));
    return {
      ...node,
      snapshot: latest.get(nodeKey(node.node_id)),
      field: variableWriter.value?.fields.find(
        (f) => f.node_id === node.node_id,
      ),
      error:
        state?.status_code && !state.status_code.startsWith("Good")
          ? state.status_code
          : "",
    };
  });
});
const chartNode = ref("");
const chartPoints = computed(() => {
  let interrupted = false;
  return records.value.flatMap((e) => {
    if (e.streamGap) interrupted = true;
    if (e.kind === "connection" && e.state === "disconnected") {
      interrupted = true;
      return [];
    }
    if (
      e.kind !== "value" ||
      e.node_id !== chartNode.value ||
      (props.role === "client" &&
        e.subscription !== currentSubscription.value?.id) ||
      (props.role === "server" && e.writer_id !== variableWriterId.value)
    )
      return [];
    const point = {
      timestamp: e.source_timestamp || e.server_timestamp || e.timestamp,
      value: e.value,
      status: e.status_code,
      breakBefore: interrupted,
    };
    interrupted = false;
    return [point];
  });
});
const eventSearch = ref(""),
  eventDetail = ref<OpcUaStreamEvent>(),
  eventMessage = ref(""),
  emitSeverity = ref(500),
  emitSource = ref(""),
  emitting = ref(false);
const visibleEvents = computed(() =>
  records.value
    .filter(
      (e) =>
        e.kind === "event" &&
        eventNodes.value.some(
          (n) => nodeKey(n.node_id) === nodeKey(String(e.SourceNode || "")),
        ) &&
        (e.Severity || 0) >= eventsConfig.value.minimum_severity &&
        String(e.Message || "")
          .toLowerCase()
          .includes(eventsConfig.value.message_filter.toLowerCase()) &&
        `${e.Message} ${e.SourceName} ${displayUaValue(e.EventId)}`
          .toLowerCase()
          .includes(eventSearch.value.toLowerCase()),
    )
    .slice()
    .reverse(),
);
let epoch = 0,
  pollEpoch = 0,
  cursor = 0,
  timer: ReturnType<typeof setTimeout> | undefined,
  statusTick = 0;
const draftKey = () => `ems.opcua.history.${props.channelId}`;
async function load() {
  const current = ++epoch;
  ready.value = false;
  loading.value = true;
  try {
    const features = await getOpcUaFeatures(props.channelId);
    if (current !== epoch) return;
    subscriptions.value = features.subscriptions?.subscriptions?.length
      ? features.subscriptions.subscriptions
      : [defaultSubscription()];
    subscriptionOptions.value = {
      reconnect: true,
      retry_min_s: 1,
      retry_max_s: 30,
      ...features.subscriptions,
    };
    delete (subscriptionOptions.value as Record<string, unknown>).subscriptions;
    publisher.value = {
      ...defaultPublisher(props.channelId),
      ...features.pubsub,
    };
    variableWriterId.value = variableWriters.value[0]?.writer_id || 1;
    eventWriterId.value = eventWriters.value[0]?.writer_id || 2;
    eventsConfig.value = {
      enabled: false,
      source_node: "i=2253",
      source_nodes: [],
      event_type: "i=2041",
      minimum_severity: 0,
      message_filter: "",
      returned_fields: [
        "EventId",
        "SourceNode",
        "SourceName",
        "Time",
        "Severity",
        "Message",
      ],
      ...features.events,
    };
    if (features.events && !eventsConfig.value.source_nodes.length)
      eventsConfig.value.source_nodes = [eventsConfig.value.source_node];
    if (props.role === "server") {
      const response = await listOpcUaVariables(props.channelId);
      if (current !== epoch) return;
      response.nodes.forEach((n) => {
        nodeCache.value[nodeKey(n.node_id)] = { ...n, node_class: "Variable" };
      });
      restoreHistory(features.history?.nodes || []);
    } else {
      try {
        const saved = JSON.parse(localStorage.getItem(draftKey()) || "[]");
        if (Array.isArray(saved))
          historyNodes.value = saved
            .filter(
              (n) =>
                typeof n?.node_id === "string" &&
                typeof n?.browse_name === "string",
            )
            .slice(0, 50);
      } catch {
        historyNodes.value = [];
      }
    }
    ready.value = true;
  } catch (e) {
    if (current === epoch) {
      pageError.value = e instanceof Error ? e.message : String(e);
      showError(e);
    }
  } finally {
    if (current === epoch) loading.value = false;
  }
}
async function addNodes(incoming: UaSelection[]) {
  if (adding.value || !ready.value || saving.value) return;
  const current = epoch,
    channel = props.channelId,
    target = kind.value;
  if (
    target === "realtime" &&
    props.role === "client" &&
    !currentSubscription.value
  )
    newSubscription();
  const subscription = currentSubscription.value;
  const writer = target === "events" ? eventWriter.value : variableWriter.value;
  if (props.role === "server" && target !== "history" && !writer) {
    ElMessage.warning(t("opcua.createDatasetFirst"));
    openDatasetSettings();
    return;
  }
  adding.value = true;
  const accepted: UaSelection[] = [],
    messages: string[] = [];
  try {
    for (let offset = 0; offset < incoming.length; offset += 5) {
      const checked = await Promise.allSettled(
        incoming.slice(offset, offset + 5).map(async (n) =>
          props.running
            ? {
                ...n,
                ...(await getOpcUaNodeCapabilities(channel, n.node_id)),
              }
            : n,
        ),
      );
      if (current !== epoch) return;
      checked.forEach((result, index) => {
        const original = incoming[offset + index];
        if (result.status === "rejected") {
          messages.push(
            `${original.browse_name}: ${result.reason instanceof Error ? result.reason.message : String(result.reason)}`,
          );
          return;
        }
        const node = {
          ...result.value,
          node_id: nodeKey(result.value.node_id),
        };
        if (!props.running && props.role === "client") {
          messages.push(t("opcua.connectHint"));
          return;
        }
        const reason = rejectionReason(node, target, props.role);
        if (reason)
          messages.push(`${node.browse_name}: ${t(`opcua.${reason}`)}`);
        else {
          nodeCache.value[node.node_id] = node;
          accepted.push(node);
        }
      });
    }
    // A tab or selected dataset can change while native capabilities are read.
    // Apply to the original draft only if it is still present.
    if (
      target !== "history" &&
      props.role === "server" &&
      !publisher.value.writers.includes(writer!)
    )
      return;
    if (
      target === "realtime" &&
      props.role === "client" &&
      !subscriptions.value.includes(subscription!)
    )
      return;
    const existing =
      target === "history"
        ? historyNodes.value
        : target === "events"
          ? (props.role === "server"
              ? writer!.source_nodes
              : eventsConfig.value.source_nodes
            ).map((id) => lookup(id, "Object"))
          : (props.role === "server"
              ? writer!.fields.map((f) => f.node_id)
              : subscription!.items.map((i) => i.node_id)
            ).map((id) => lookup(id));
    const combined = uniqueSelections(existing, accepted),
      limit = target === "history" ? 50 : target === "events" ? 100 : 1000;
    if (combined.length > limit)
      messages.push(t("opcua.nodeLimit", { count: limit }));
    const additions = combined
      .slice(0, limit)
      .filter(
        (n) => !existing.some((e) => nodeKey(e.node_id) === nodeKey(n.node_id)),
      );
    if (target === "history") historyNodes.value = combined.slice(0, limit);
    else if (target === "events") {
      if (props.role === "server" && writer)
        writer.source_nodes.push(...additions.map((n) => n.node_id));
      else
        eventsConfig.value.source_nodes.push(
          ...additions.map((n) => n.node_id),
        );
      eventsDirty.value = !!additions.length || eventsDirty.value;
    } else if (props.role === "server" && writer) {
      additions.forEach((node) => {
        const base = (node.browse_name || node.node_id).slice(0, 120);
        let alias = base,
          suffix = 1;
        while (writer.fields.some((f) => f.alias === alias))
          alias = `${base}_${suffix++}`;
        writer.fields.push({ node_id: node.node_id, alias });
      });
      dirty.value = !!additions.length || dirty.value;
    } else {
      (subscription || currentSubscription.value)?.items.push(
        ...additions.map((n) => defaultMonitor(n.node_id)),
      );
      dirty.value = !!additions.length || dirty.value;
    }
    if (accepted.length && !additions.length)
      messages.push(t("opcua.nodesAlreadyAdded"));
    feedback.value = messages.slice(0, 20);
    if (additions.length)
      ElMessage.success(t("opcua.nodesAdded", { count: additions.length }));
  } finally {
    if (current === epoch) adding.value = false;
  }
}
function dragOver(event: DragEvent) {
  if (event.dataTransfer?.types.includes(DRAG_MIME)) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    dragging.value = true;
  }
}
function drop(event: DragEvent) {
  event.preventDefault();
  dragging.value = false;
  try {
    void addNodes(
      decodeUaDrag(
        event.dataTransfer?.getData(DRAG_MIME) || "",
        props.channelId,
      ),
    );
  } catch (e) {
    const key = e instanceof Error ? e.message : "invalidDrag";
    ElMessage.warning(
      t(
        `opcua.${["crossChannelDrag", "invalidDrag"].includes(key) ? key : "invalidDrag"}`,
      ),
    );
  }
}
function newSubscription() {
  let id = 1;
  while (subscriptions.value.some((s) => s.id === `Subscription${id}`)) id++;
  subscriptions.value.push(defaultSubscription(`Subscription${id}`));
  subscriptionIndex.value = subscriptions.value.length - 1;
  dirty.value = true;
}
function deleteSubscription() {
  subscriptions.value.splice(subscriptionIndex.value, 1);
  subscriptionIndex.value = Math.max(0, subscriptionIndex.value - 1);
  dirty.value = true;
}
function removeRealtime(id: string) {
  if (props.role === "server" && variableWriter.value)
    variableWriter.value.fields = variableWriter.value.fields.filter(
      (f) => f.node_id !== id,
    );
  else if (currentSubscription.value)
    currentSubscription.value.items = currentSubscription.value.items.filter(
      (i) => i.node_id !== id,
    );
  dirty.value = true;
}
function removeEventSource(id: string) {
  if (props.role === "server" && eventWriter.value)
    eventWriter.value.source_nodes = eventWriter.value.source_nodes.filter(
      (n) => n !== id,
    );
  else
    eventsConfig.value.source_nodes = eventsConfig.value.source_nodes.filter(
      (n) => n !== id,
    );
  eventsDirty.value = true;
}
function editMonitor(id: string) {
  editingMonitor.value = currentSubscription.value?.items.find(
    (i) => i.node_id === id,
  );
  monitorSettings.value = true;
}
function applyPublisher(config: UaPublisher) {
  publisher.value = config;
  variableWriterId.value = variableWriters.value.some(
    (w) => w.writer_id === variableWriterId.value,
  )
    ? variableWriterId.value
    : variableWriters.value[0]?.writer_id || 1;
  eventWriterId.value = eventWriters.value.some(
    (w) => w.writer_id === eventWriterId.value,
  )
    ? eventWriterId.value
    : eventWriters.value[0]?.writer_id || 2;
  dirty.value = true;
  eventsDirty.value = true;
}
function restoreHistory(ids: string[]) {
  historyNodes.value = ids.map((id) => lookup(id));
}
async function refreshStatus(current = epoch) {
  const result = await getOpcUaCapabilities(props.channelId);
  if (current === epoch) caps.value = result.capabilities;
}
async function saveRealtime(enabled?: boolean) {
  if (saving.value) return;
  const current = epoch;
  saving.value = true;
  try {
    if (props.role === "server") {
      const config = JSON.parse(JSON.stringify(publisher.value)) as UaPublisher;
      if (enabled !== undefined) config.enabled = enabled;
      if (
        config.enabled &&
        config.writers.some(
          (w) => w.enabled && w.kind === "events" && w.source_nodes.length,
        )
      )
        await persistServerEvents(true);
      await saveOpcUaFeature(props.channelId, "pubsub", config);
      if (current !== epoch) return;
      publisher.value = config;
    } else {
      const config = JSON.parse(
        JSON.stringify(subscriptions.value),
      ) as UaSubscription[];
      if (enabled !== undefined && config[subscriptionIndex.value])
        config[subscriptionIndex.value].enabled = enabled;
      await saveOpcUaFeature(props.channelId, "subscriptions", {
        ...subscriptionOptions.value,
        subscriptions: config,
      });
      if (current !== epoch) return;
      subscriptions.value = config;
    }
    dirty.value = false;
    await refreshStatus(current);
    ElMessage.success(t("opcua.configSaved"));
  } catch (e) {
    if (current === epoch) showError(e);
  } finally {
    if (current === epoch) saving.value = false;
  }
}
async function persistServerEvents(enabled: boolean) {
  const sources = [
    ...new Set(
      eventWriters.value
        .filter((w) => w.enabled)
        .flatMap((w) => w.source_nodes),
    ),
  ];
  const config = {
    ...eventsConfig.value,
    enabled,
    source_nodes: sources,
    source_node: sources[0] || eventsConfig.value.source_node,
  };
  await saveOpcUaFeature(props.channelId, "events", config);
  eventsConfig.value = config;
}
async function saveEvents(enabled?: boolean) {
  if (saving.value) return;
  const current = epoch;
  saving.value = true;
  try {
    if (props.role === "server") {
      if (eventWriter.value) {
        eventWriter.value.event_fields = [
          ...eventsConfig.value.returned_fields,
        ];
        if (enabled !== undefined) eventWriter.value.enabled = enabled;
      }
      const eventEnabled =
        enabled === undefined
          ? eventsConfig.value.enabled
          : enabled ||
            eventWriters.value.some((w) => w.enabled && w.source_nodes.length);
      await persistServerEvents(eventEnabled);
      const config = JSON.parse(JSON.stringify(publisher.value)) as UaPublisher;
      if (enabled === true) config.enabled = true;
      else if (
        enabled === false &&
        !config.writers.some(
          (w) =>
            w.enabled &&
            (w.kind === "variables" ? w.fields.length : w.source_nodes.length),
        )
      )
        config.enabled = false;
      await saveOpcUaFeature(props.channelId, "pubsub", config);
      if (current !== epoch) return;
      publisher.value = config;
    } else {
      const config = {
        ...eventsConfig.value,
        source_node: eventsConfig.value.source_nodes[0] || "i=2253",
        enabled: enabled === undefined ? eventsConfig.value.enabled : enabled,
      };
      if (config.enabled && !config.source_nodes.length)
        throw new Error(t("opcua.requireEventSource"));
      await saveOpcUaFeature(props.channelId, "events", config);
      if (current !== epoch) return;
      eventsConfig.value = config;
    }
    eventsDirty.value = false;
    await refreshStatus(current);
    ElMessage.success(t("opcua.configSaved"));
  } catch (e) {
    if (current === epoch) showError(e);
  } finally {
    if (current === epoch) saving.value = false;
  }
}
async function triggerEvent() {
  const current = epoch;
  emitting.value = true;
  try {
    await emitOpcUaEvent(
      props.channelId,
      eventMessage.value,
      emitSeverity.value,
      emitSource.value,
    );
  } catch (e) {
    if (current === epoch) showError(e);
  } finally {
    if (current === epoch) emitting.value = false;
  }
}
function clearEvents() {
  records.value = records.value.filter((e) => e.kind !== "event");
  eventDetail.value = undefined;
}
function exportEvents() {
  const fields = eventsConfig.value.returned_fields;
  downloadCsv(
    "opcua-events.csv",
    fields,
    visibleEvents.value.map((e) => fields.map((f) => e[f])),
  );
}
async function poll(version: number) {
  if (version !== pollEpoch || !props.active || !props.running) return;
  try {
    const result = await readOpcUaStream(props.channelId, cursor);
    if (version !== pollEpoch) return;
    if (result.latest_sequence < cursor) {
      cursor = 0;
      records.value = [];
      connection.value = "";
    } else {
      if (result.gap) gap.value = true;
      const received = result.events.map((e, index) =>
        index === 0 && result.gap ? { ...e, streamGap: true } : e,
      );
      records.value = [...records.value, ...received].slice(-2000);
      result.events.forEach((e) => {
        if (e.kind === "connection") connection.value = e.state || "";
      });
      cursor = result.events.length
        ? result.events[result.events.length - 1].sequence
        : result.latest_sequence;
    }
    if (statusTick++ % 4 === 0) await refreshStatus();
    if (version === pollEpoch) pageError.value = "";
  } catch (e) {
    if (version === pollEpoch)
      pageError.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (version === pollEpoch && props.active && props.running)
      timer = setTimeout(() => void poll(version), 500);
  }
}
watch(
  () => [props.active, props.running],
  () => {
    pollEpoch++;
    if (timer) clearTimeout(timer);
    if (!props.running) connection.value = "disconnected";
    if (props.active && props.running) void poll(pollEpoch);
  },
  { immediate: true },
);
watch(
  () => props.channelId,
  () => {
    cursor = 0;
    records.value = [];
    nodeCache.value = {};
    historyNodes.value = [];
    caps.value = [];
    gap.value = false;
    dirty.value = false;
    eventsDirty.value = false;
    feedback.value = [];
    void load();
  },
  { immediate: true },
);
watch(
  () => props.revision,
  async () => {
    if (props.role !== "server") return;
    const current = epoch;
    try {
      const nodes = (await listOpcUaVariables(props.channelId)).nodes;
      if (current !== epoch) return;
      const existing = new Set(nodes.map((n) => n.node_id));
      nodes.forEach((n) => {
        nodeCache.value[nodeKey(n.node_id)] = { ...n, node_class: "Variable" };
      });
      publisher.value.writers.forEach((w) => {
        w.fields = w.fields.filter((f) => existing.has(f.node_id));
      });
      historyNodes.value = historyNodes.value.filter((n) =>
        existing.has(n.node_id),
      );
    } catch (e) {
      if (current === epoch) showError(e);
    }
  },
);
watch(realtimeNodes, (nodes) => {
  if (!nodes.some((n) => n.node_id === chartNode.value))
    chartNode.value = nodes[0]?.node_id || "";
});
watch(eventNodes, (nodes) => {
  if (!nodes.some((n) => n.node_id === emitSource.value))
    emitSource.value = nodes[0]?.node_id || "";
  eventDetail.value = undefined;
});
watch(eventWriter, (writer) => {
  if (props.role === "server" && writer)
    eventsConfig.value.returned_fields = [...writer.event_fields];
});
watch(
  historyNodes,
  (nodes) => {
    if (props.role === "client") {
      try {
        localStorage.setItem(draftKey(), JSON.stringify(nodes));
      } catch {
        /* Storage may be unavailable in restricted webviews. */
      }
    }
  },
  { deep: true },
);
onBeforeUnmount(() => {
  epoch++;
  pollEpoch++;
  if (timer) clearTimeout(timer);
});
</script>

<style scoped>
.pubsub-workspace {
  --ua-primary: #7453f8;
  --el-color-primary: var(--ua-primary);
  --el-color-primary-light-9: #f4f0ff;
  --el-color-primary-light-3: #9b85fb;
  --el-color-primary-light-5: #baaafa;
  --el-color-primary-light-7: #d9ceff;
  --el-color-primary-dark-2: #6241df;
  --ua-drop-bg: #f7f4ff;
  --ua-drop-active: #eae2ff;
}
:global(body.theme-dark) .pubsub-workspace {
  --ua-drop-bg: #302a47;
  --ua-drop-active: #413265;
}
.pubsub-columns {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.pubsub-content {
  min-width: 0;
  display: grid;
  gap: 14px;
}
.data-tabs {
  margin-bottom: 14px;
}
.drop-zone {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 78px;
  padding: 14px 18px;
  border: 1px dashed #bdaeff;
  border-radius: 8px;
  background: var(--ua-drop-bg);
  color: var(--ua-primary);
  transition: background 0.15s;
}
.drop-zone.over {
  background: var(--ua-drop-active);
  border: 2px solid var(--ua-primary);
}
.drop-zone strong {
  font-size: 13px;
}
.drop-zone p {
  margin: 5px 0 0;
  font-size: 12px;
  color: var(--ua-muted);
}
.drop-symbol {
  font-size: 27px;
}
.workspace-pane {
  min-width: 0;
}
.ua-section {
  margin-bottom: 14px;
}
.selected-nodes {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.event-options,
.subscription-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 0 16px;
  margin-top: 16px;
}
.event-actions,
.emit-toolbar {
  margin-top: 16px;
}
.ua-muted,
.revision-line {
  font-size: 12px;
  color: var(--ua-muted);
  line-height: 1.6;
}
.revision-line {
  padding-top: 12px;
}
.item-error {
  color: var(--el-color-danger);
  font-size: 12px;
}
.el-alert {
  margin-bottom: 12px;
}
@container (max-width:1050px) {
  .pubsub-columns {
    grid-template-columns: 235px minmax(0, 1fr);
    gap: 12px;
  }
}
@container (max-width:760px) {
  .pubsub-columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
