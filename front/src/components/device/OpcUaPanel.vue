<template>
  <section class="opcua-panel">
    <el-tabs v-model="activeTab">
      <el-tab-pane
        :label="
          t(role === 'server' ? 'opcua.serverPoints' : 'opcua.localPoints')
        "
        name="points"
      >
        <OpcUaPageHeading
          :title="
            t(role === 'server' ? 'opcua.serverPoints' : 'opcua.localPoints')
          "
          :description="t('opcua.pointsDescription')"
        >
          <el-tag :type="running ? 'success' : 'info'" effect="light">{{
            t(running ? "opcua.running" : "opcua.stopped")
          }}</el-tag>
        </OpcUaPageHeading>
        <div class="toolbar">
          <el-input
            v-model="search"
            :placeholder="t('opcua.pointSearch')"
            clearable
            @keyup.enter="queryPoints"
          />
          <el-select
            v-model="pointType"
            style="width: 130px"
            @change="queryPoints"
          >
            <el-option :label="t('opcua.allTypes')" :value="-1" />
            <el-option
              v-for="(label, index) in pointTypes"
              :key="index"
              :label="label"
              :value="index"
            />
          </el-select>
          <el-button @click="queryPoints">{{ t("opcua.query") }}</el-button>
          <el-button
            type="primary"
            :disabled="role === 'server' && running"
            @click="selectFile"
          >
            {{ t("opcua.importPoints") }}
          </el-button>
          <el-button :loading="exportingPoints" @click="exportPoints">{{
            t("opcua.exportPoints")
          }}</el-button>
          <el-button
            type="danger"
            :disabled="!total || (role === 'server' && running)"
            @click="clearPoints"
            >{{ t("opcua.clearPoints") }}</el-button
          >
          <input
            ref="fileInput"
            type="file"
            accept=".xlsx"
            hidden
            @change="onFileSelected"
          />
        </div>
        <el-alert
          v-if="role === 'client'"
          type="info"
          :closable="false"
          class="hint"
          :title="t('opcua.clientPointsHint')"
        />
        <el-alert
          v-if="role === 'server' && running"
          type="warning"
          :closable="false"
          class="hint"
          :title="t('opcua.serverPointsHint')"
        />
        <el-table
          v-loading="loading"
          :data="points"
          stripe
          row-key="id"
          :empty-text="t('opcua.noPoints')"
        >
          <el-table-column
            prop="point_type"
            :label="t('opcua.type')"
            width="100"
          >
            <template #default="{ row }">{{
              pointTypes[row.point_type]
            }}</template>
          </el-table-column>
          <el-table-column
            prop="point_code"
            :label="t('opcua.code')"
            min-width="150"
            show-overflow-tooltip
          />
          <el-table-column
            prop="point_name"
            :label="t('opcua.name')"
            min-width="150"
            show-overflow-tooltip
          />
          <el-table-column
            prop="node_id"
            label="NodeId"
            min-width="230"
            show-overflow-tooltip
          />
          <el-table-column
            prop="data_type"
            :label="t('opcua.dataType')"
            width="100"
          />
          <el-table-column
            prop="initial_value"
            :label="t('opcua.initialValue')"
            width="100"
          />
          <el-table-column :label="t('opcua.lastValue')" width="120">
            <template #default="{ row }">{{
              pointValues[row.point_code]?.value ?? "-"
            }}</template>
          </el-table-column>
          <el-table-column :label="t('opcua.quality')" width="150">
            <template #default="{ row }">{{
              pointValues[row.point_code]?.status_code || "-"
            }}</template>
          </el-table-column>
          <el-table-column
            :label="t('opcua.actions')"
            width="150"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                link
                :disabled="!running"
                @click="readLocalPoint(row)"
                >{{ t("opcua.read") }}</el-button
              >
              <el-button
                link
                type="danger"
                :disabled="role === 'server' && running"
                @click="removePoint(row)"
                >{{ t("opcua.delete") }}</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          class="pager"
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="changePage"
        />
      </el-tab-pane>

      <el-tab-pane
        v-if="role === 'server'"
        :label="t('opcua.addressSpace')"
        name="model"
      >
        <OpcUaAddressSpace
          :channel-id="channelId"
          :running="running"
          :revision="modelRevision"
          @changed="onModelChanged"
        />
      </el-tab-pane>

      <el-tab-pane :label="t('opcua.runtime')" name="status">
        <OpcUaRuntime :channel-id="channelId" :running="running" />
      </el-tab-pane>

      <el-tab-pane
        v-if="role === 'client'"
        :label="t('opcua.remoteBrowse')"
        name="browse"
      >
        <OpcUaPageHeading
          :title="t('opcua.remoteBrowse')"
          :description="t('opcua.browseDescription')"
        >
          <el-tag :type="running ? 'success' : 'info'" effect="light">{{
            t(running ? "opcua.running" : "opcua.stopped")
          }}</el-tag>
        </OpcUaPageHeading>
        <div class="toolbar">
          <el-input
            v-model="browseRoot"
            :placeholder="t('opcua.browseRoot')"
            @keyup.enter="browse"
          />
          <el-button
            type="primary"
            :disabled="!running"
            :loading="browsing"
            @click="browse"
            >{{ t("opcua.browseChildren") }}</el-button
          >
        </div>
        <el-alert
          v-if="!running"
          type="info"
          :closable="false"
          class="hint"
          :title="t('opcua.connectHint')"
        />
        <el-table
          :data="remoteNodes"
          stripe
          :empty-text="t('opcua.noBrowseResults')"
        >
          <el-table-column prop="node_id" label="NodeId" min-width="230" />
          <el-table-column
            prop="browse_name"
            label="BrowseName"
            min-width="180"
          />
          <el-table-column
            prop="node_class"
            :label="t('opcua.nodeClass')"
            width="130"
          />
          <el-table-column :label="t('opcua.actions')" width="160">
            <template #default="{ row }">
              <el-button
                link
                :disabled="!running"
                @click="openNode(row.node_id)"
                >{{ t("opcua.expand") }}</el-button
              >
              <el-button
                link
                :disabled="!running"
                @click="readNode(row.node_id)"
                >{{ t("opcua.read") }}</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          class="pager"
          layout="total, prev, pager, next"
          :total="remoteTotal"
          :page-size="100"
          :current-page="remotePage"
          @current-change="changeRemotePage"
        />
        <div class="toolbar node-action">
          <el-input v-model="targetNode" :placeholder="t('opcua.targetNode')" />
          <el-button
            :disabled="!running || !targetNode"
            @click="readNode(targetNode)"
            >{{ t("opcua.read") }}</el-button
          >
          <el-select v-model="valueType" style="width: 115px">
            <el-option
              v-for="type in OPCUA_SCALAR_TYPES"
              :key="type"
              :label="type"
              :value="type"
            />
          </el-select>
          <el-input v-model="writeText" :placeholder="t('opcua.writeValue')" />
          <el-button
            type="primary"
            :disabled="!running || !targetNode"
            @click="writeNode"
            >{{ t("opcua.write") }}</el-button
          >
        </div>
        <el-descriptions v-if="nodeResult" :column="2" border>
          <el-descriptions-item label="NodeId">{{
            nodeResult.node_id
          }}</el-descriptions-item>
          <el-descriptions-item :label="t('opcua.dataType')">{{
            nodeResult.variant_type || "-"
          }}</el-descriptions-item>
          <el-descriptions-item :label="t('opcua.value')">{{
            formatValue(nodeResult.value)
          }}</el-descriptions-item>
          <el-descriptions-item :label="t('opcua.quality')">{{
            nodeResult.status_code
          }}</el-descriptions-item>
          <el-descriptions-item :label="t('opcua.sourceTimestamp')">{{
            nodeResult.source_timestamp || "-"
          }}</el-descriptions-item>
          <el-descriptions-item :label="t('opcua.serverTimestamp')">{{
            nodeResult.server_timestamp || "-"
          }}</el-descriptions-item>
        </el-descriptions>
      </el-tab-pane>

      <el-tab-pane :label="t('opcua.endpointConfig')" name="config">
        <OpcUaPageHeading
          :title="t('opcua.endpointConfig')"
          :description="t('opcua.endpointDescription')"
        >
          <el-tag :type="running ? 'success' : 'info'" effect="light">{{
            t(running ? "opcua.running" : "opcua.stopped")
          }}</el-tag>
        </OpcUaPageHeading>
        <el-form
          v-if="config"
          label-width="140px"
          class="config-form ua-section"
        >
          <el-form-item :label="t('opcua.currentEndpoint')"
            ><span>{{ config.endpoint_url }}</span></el-form-item
          >
          <el-form-item
            v-if="role === 'client'"
            :label="t('opcua.clientEndpoint')"
          >
            <el-input
              v-model="endpointUrl"
              placeholder="opc.tcp://127.0.0.1:4840/ems/"
            />
          </el-form-item>
          <template v-else>
            <el-form-item :label="t('opcua.endpointPath')"
              ><el-input v-model="endpointPath"
            /></el-form-item>
            <el-form-item :label="t('opcua.namespaceUri')"
              ><el-input v-model="namespaceUri"
            /></el-form-item>
          </template>
          <el-form-item>
            <el-button
              type="primary"
              :disabled="running"
              :loading="savingConfig"
              @click="saveConfig"
              >{{ t("opcua.saveConfig") }}</el-button
            >
            <span v-if="running" class="form-hint">{{
              t("opcua.stopFirst")
            }}</span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane
        :label="
          t(role === 'server' ? 'opcua.simulation' : 'opcua.subscriptions')
        "
        name="acquisition"
        lazy
      >
        <OpcUaAcquisition
          :channel-id="channelId"
          :role="role"
          :running="running"
        />
      </el-tab-pane>
      <el-tab-pane
        v-if="role === 'client'"
        :label="t('opcua.trend')"
        name="trend"
        lazy
      >
        <OpcUaPageHeading
          :title="t('opcua.trend')"
          :description="t('opcua.trendDescription')"
        />
        <OpcUaLive :channel-id="channelId" mode="trend" />
      </el-tab-pane>
      <el-tab-pane :label="t('opcua.history')" name="history" lazy>
        <OpcUaHistory :channel-id="channelId" :role="role" :running="running" />
      </el-tab-pane>
      <el-tab-pane :label="t('opcua.events')" name="events" lazy>
        <OpcUaEvents :channel-id="channelId" :role="role" :running="running" />
      </el-tab-pane>
      <el-tab-pane :label="t('opcua.security')" name="security" lazy>
        <OpcUaSecurity
          :channel-id="channelId"
          :role="role"
          :running="running"
        />
      </el-tab-pane>
      <el-tab-pane :label="t('opcua.diagnostics')" name="diagnostics" lazy>
        <OpcUaDiagnostics :channel-id="channelId" />
      </el-tab-pane>
    </el-tabs>

    <OpcUaPointImportDialog
      ref="pointImportRef"
      :disabled="role === 'server' && running"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { showError } from "@/api/http";
import "@/styles/opcua.scss";
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import OpcUaAddressSpace from "./OpcUaAddressSpace.vue";
import OpcUaRuntime from "./OpcUaRuntime.vue";
import OpcUaPointImportDialog from "./OpcUaPointImportDialog.vue";
import OpcUaAcquisition from "./OpcUaAcquisition.vue";
import OpcUaLive from "./OpcUaLive.vue";
import OpcUaHistory from "./OpcUaHistory.vue";
import OpcUaEvents from "./OpcUaEvents.vue";
import OpcUaSecurity from "./OpcUaSecurity.vue";
import OpcUaDiagnostics from "./OpcUaDiagnostics.vue";
import {
  OPCUA_SCALAR_TYPES,
  OpcUaScalarError,
  parseOpcUaScalar,
} from "@/utils/opcuaValue";
import {
  browseOpcUaNodes,
  clearOpcUaPoints,
  deleteOpcUaPoint,
  exportOpcUaPoints,
  getOpcUaConfig,
  listOpcUaPoints,
  readOpcUaNode,
  readOpcUaPoint,
  saveOpcUaClientEndpoint,
  saveOpcUaServerModel,
  writeOpcUaNode,
} from "@/api/opcuaApi";
import type {
  OpcUaConfig,
  OpcUaPoint,
  OpcUaValueSnapshot,
} from "@/api/opcuaApi";

const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
}>();
const { t } = useI18n();
const emit = defineEmits<{ "config-changed": [] }>();
const modelRevision = ref(0);
const exportingPoints = ref(false);
const pointTypes = computed(() => [
  t("opcua.telemetry"),
  t("opcua.signal"),
  t("opcua.control"),
  t("opcua.adjustment"),
]);
const activeTab = ref("points");
const points = ref<OpcUaPoint[]>([]);
const pointValues = ref<Record<string, OpcUaValueSnapshot>>({});
const search = ref("");
const pointType = ref(-1);
const page = ref(1);
const pageSize = 100;
const total = ref(0);
const loading = ref(false);
const config = ref<OpcUaConfig | null>(null);
const endpointUrl = ref("");
const endpointPath = ref("");
const namespaceUri = ref("");
const savingConfig = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const pointImportRef = ref<InstanceType<typeof OpcUaPointImportDialog> | null>(
  null,
);
const browseRoot = ref("i=85");
const remoteNodes = ref<
  { node_id: string; browse_name: string; node_class: string }[]
>([]);
const remoteTotal = ref(0);
const remotePage = ref(1);
const browsing = ref(false);
const targetNode = ref("");
const valueType = ref<import("@/utils/opcuaValue").OpcUaScalarType>("Double");
const writeText = ref("");
const nodeResult = ref<OpcUaValueSnapshot | null>(null);

function formatValue(value: unknown): string {
  return value === null || value === undefined
    ? "-"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
}

async function loadPoints() {
  loading.value = true;
  try {
    const result = await listOpcUaPoints(
      props.channelId,
      search.value,
      pointType.value < 0 ? null : pointType.value,
      (page.value - 1) * pageSize,
      pageSize,
    );
    points.value = result.points;
    total.value = result.total;
  } catch (error) {
    showError(error);
  } finally {
    loading.value = false;
  }
}

function changePage(value: number) {
  page.value = value;
  void loadPoints();
}
function queryPoints() {
  page.value = 1;
  void loadPoints();
}

async function onModelChanged() {
  await loadConfig();
  emit("config-changed");
}

async function loadConfig() {
  try {
    config.value = await getOpcUaConfig(props.channelId);
    endpointUrl.value = config.value.endpoint_url;
    endpointPath.value = config.value.endpoint_path;
    namespaceUri.value = config.value.namespace_uri;
  } catch (error) {
    showError(error);
  }
}

function selectFile() {
  fileInput.value?.click();
}

async function exportPoints() {
  exportingPoints.value = true;
  try {
    const blob = await exportOpcUaPoints(props.channelId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `opcua-points-${props.channelId}.xlsx`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    showError(error);
  } finally {
    exportingPoints.value = false;
  }
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !pointImportRef.value) return;
  const id = props.channelId;
  if ((await pointImportRef.value.open(id, file)) && id === props.channelId) {
    pointValues.value = {};
    page.value = 1;
    await loadPoints();
    await loadConfig();
    modelRevision.value++;
    emit("config-changed");
  }
}

async function removePoint(point: OpcUaPoint) {
  try {
    await ElMessageBox.confirm(
      t("opcua.deletePointConfirm", { code: point.point_code }),
      t("opcua.confirmDelete"),
      { type: "warning" },
    );
    await deleteOpcUaPoint(props.channelId, point.point_code);
    ElMessage.success(t("opcua.pointDeleted"));
    await loadPoints();
    modelRevision.value++;
  } catch (error) {
    if (error !== "cancel" && error !== "close") showError(error);
  }
}

async function clearPoints() {
  try {
    await ElMessageBox.confirm(
      t("opcua.clearPointsConfirm"),
      t("opcua.confirmDelete"),
      { type: "warning" },
    );
    const result = await clearOpcUaPoints(props.channelId);
    ElMessage.success(t("opcua.pointsCleared", result));
    pointValues.value = {};
    page.value = 1;
    await loadPoints();
    modelRevision.value++;
  } catch (error) {
    if (error !== "cancel" && error !== "close") showError(error);
  }
}

async function browse() {
  browsing.value = true;
  try {
    const result = await browseOpcUaNodes(
      props.channelId,
      browseRoot.value,
      (remotePage.value - 1) * 100,
    );
    remoteNodes.value = result.nodes;
    remoteTotal.value = result.total;
  } catch (error) {
    showError(error);
  } finally {
    browsing.value = false;
  }
}

function changeRemotePage(value: number) {
  remotePage.value = value;
  void browse();
}
function openNode(nodeId: string) {
  browseRoot.value = nodeId;
  remotePage.value = 1;
  void browse();
}

async function readNode(nodeId: string) {
  targetNode.value = nodeId;
  try {
    nodeResult.value = await readOpcUaNode(props.channelId, nodeId);
  } catch (error) {
    showError(error);
  }
}

async function readLocalPoint(point: OpcUaPoint) {
  try {
    pointValues.value[point.point_code] = await readOpcUaPoint(
      props.channelId,
      point.point_code,
    );
  } catch (error) {
    showError(error);
  }
}

async function writeNode() {
  try {
    const value = parseOpcUaScalar(writeText.value, valueType.value);
    nodeResult.value = await writeOpcUaNode(
      props.channelId,
      targetNode.value,
      value,
    );
    ElMessage.success(t("opcua.writeSucceeded"));
  } catch (error) {
    if (error instanceof OpcUaScalarError)
      showError(
        t(error.type === "Boolean" ? "opcua.badBoolean" : "opcua.badNumber", {
          type: error.type,
        }),
      );
    else showError(error);
  }
}

async function saveConfig() {
  savingConfig.value = true;
  try {
    if (props.role === "client")
      await saveOpcUaClientEndpoint(props.channelId, endpointUrl.value);
    else
      await saveOpcUaServerModel(
        props.channelId,
        endpointPath.value,
        namespaceUri.value,
      );
    await loadConfig();
    ElMessage.success(t("opcua.configSaved"));
    emit("config-changed");
  } catch (error) {
    showError(error);
  } finally {
    savingConfig.value = false;
  }
}

watch(
  () => props.channelId,
  () => {
    page.value = 1;
    pointValues.value = {};
    void loadPoints();
    void loadConfig();
  },
);
onMounted(() => {
  void loadPoints();
  void loadConfig();
});
</script>

<style scoped>
.opcua-panel {
  margin-top: 16px;
  padding: 16px;
  background: var(--panel-bg);
  border-radius: 8px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.toolbar > .el-input {
  max-width: 360px;
}
.hint {
  margin-bottom: 12px;
}
.pager {
  justify-content: flex-end;
  margin-top: 12px;
}
.node-action {
  margin-top: 18px;
}
.node-result {
  padding: 12px;
  max-height: 280px;
  overflow: auto;
  background: var(--el-fill-color-light);
}
.config-form {
  max-width: none;
  padding-top: 24px;
}
.form-hint {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
}
</style>
