<template>
  <div class="dlt698-panel" v-loading="loading">
    <el-alert
      v-if="preview"
      :title="
        l(
          '界面预览 · 示例值与浏览器草稿，仅用于检查界面；未连接真实设备。',
          'UI preview · example values and browser drafts only; no real device connection.',
        )
      "
      type="warning"
      show-icon
      :closable="false"
    />
    <el-alert
      v-else-if="!status.available"
      :title="
        loadError ||
        l(
          'DL/T 698 后端尚未接入，当前设备工作区不可操作。',
          'DL/T 698 backend is unavailable; device operations are disabled.',
        )
      "
      type="warning"
      show-icon
      :closable="false"
      ><template #default
        ><el-button size="small" @click="load">{{
          l("重新检查", "Check again")
        }}</el-button></template
      ></el-alert
    >
    <el-tabs v-model="tab" class="business-tabs">
      <el-tab-pane
        v-for="item in businessTabs"
        :key="item.name"
        :name="item.name"
        :label="item.label"
      >
        <section v-if="tab === item.name" class="workspace">
          <el-alert
            v-if="tab !== 'points' && tab !== 'config' && !can(tabFeature)"
            class="unavailable-hint"
            :title="
              status.features[tabFeature]?.reason ||
              l(
                '此业务能力等待后端接入；可查看和配置界面，执行操作暂不可用。',
                'This capability awaits backend integration. Forms are available; execution is disabled.',
              )
            "
            type="info"
            :closable="false"
            show-icon
          />
          <template v-if="tab === 'points'">
            <div class="heading">
              <div>
                <h3>
                  {{
                    roleValue === "client"
                      ? l("测点读取", "Point reads")
                      : l("测点管理", "Point management")
                  }}
                </h3>
                <p>
                  {{
                    l(
                      "按 OAD 展示精确 Data、标准单位与工程值",
                      "Typed Data, standard units and engineering values by OAD",
                    )
                  }}
                </p>
              </div>
              <div class="heading-status">
                <el-tag
                  :type="status.state === 'associated' ? 'success' : 'info'"
                  >{{ stateLabel }}</el-tag
                >
                <el-tooltip
                  :content="`SA ${config.server_address} · CA ${config.client_address}`"
                >
                  <span class="muted"
                    >{{ l("已关联会话", "Associated sessions") }}:
                    {{
                      status.sessions.filter((s) => s.associated).length
                    }}</span
                  >
                </el-tooltip>
              </div>
            </div>
            <div class="categories">
              <el-button
                v-for="item in categories"
                :key="item.key"
                :type="category === item.key ? 'primary' : 'default'"
                @click="category = item.key"
                >{{ l(item.zh, item.en) }}</el-button
              >
            </div>
            <div class="toolbar">
              <el-input
                v-model="search"
                clearable
                :placeholder="
                  l('搜索 OAD / 测点名称 / 编码', 'Search OAD / name / code')
                "
                :prefix-icon="Search"
                class="search"
              />
              <el-button
                :icon="List"
                :disabled="(!can('points') && !preview) || busy"
                @click="openCatalog"
                >{{ l("标准点表", "Standard catalog") }}</el-button
              >
              <el-button
                :icon="Plus"
                type="primary"
                plain
                :disabled="(!can('points') && !preview) || busy"
                @click="openPoint()"
                >{{ l("添加测点", "Add point") }}</el-button
              >
              <el-button
                :icon="Upload"
                :disabled="!can('import') || busy"
                @click="fileInput?.click()"
                >{{ l("导入点表", "Import points") }}</el-button
              >
              <input
                ref="fileInput"
                type="file"
                accept=".xlsx"
                hidden
                @change="importFile"
              />
              <template v-if="roleValue === 'client'"
                ><el-button
                  :icon="Download"
                  type="primary"
                  :disabled="!can('get') || !readTargets.length || busy"
                  :loading="busyKind === 'read-batch'"
                  @click="readPoints(readTargets, 'batch')"
                  >{{ l("批量读取", "Read batch") }}</el-button
                ><el-button
                  :disabled="
                    !can('auto_read') ||
                    busy ||
                    (!autoRunning && !readTargets.length)
                  "
                  @click="setAutoRead"
                  >{{
                    autoRunning
                      ? l("停止自动读取", "Stop auto read")
                      : l("自动读取", "Auto read")
                  }}</el-button
                ><el-input-number
                  v-model="interval"
                  :min="100"
                  :max="60000"
                  :step="100"
                  :disabled="autoRunning"
                  style="width: 145px"
                /><span class="muted">ms</span
                ><el-button
                  :disabled="(!preview && !can('action')) || busy"
                  @click="openOperation('action')"
                  >ACTION</el-button
                ></template
              >
              <el-button
                v-if="busyKind.startsWith('read-')"
                @click="cancelRead"
                >{{ l("取消读取", "Cancel read") }}</el-button
              >
              <el-button v-if="preview" @click="exportDraft">{{
                l("导出草稿", "Export draft")
              }}</el-button>
              <el-popconfirm
                v-if="preview"
                :title="
                  l(
                    '重置此角色的预览草稿？',
                    'Reset preview drafts for this role?',
                  )
                "
                @confirm="resetDraft"
                ><template #reference
                  ><el-button>{{
                    l("恢复示例", "Reset examples")
                  }}</el-button></template
                ></el-popconfirm
              >
            </div>
            <el-alert
              v-if="workspaceError"
              :title="workspaceError"
              type="error"
              :closable="false"
            />
            <el-alert
              v-if="notice"
              :title="notice"
              type="success"
              :closable="false"
            />
            <Dlt698PointTable
              :points="filteredPoints"
              :role="roleValue"
              :device-name="deviceName"
              :preview="preview"
              :busy="busy"
              :reading-code="busyKind === 'read-point' ? busyPointCode : ''"
              :saving-value-code="
                busyKind === 'point-value' ? busyPointCode : ''
              "
              :saving-point-code="
                busyKind === 'point-save' ? busyPointCode : ''
              "
              :can="can"
              :save-error="pointError"
              @save="saveInlinePoint"
              @set-value="setInlineValue"
              @selection="selected = $event"
              @edit="openPoint"
              @delete="deletePoint"
              @read="readPoints([$event], 'point')"
              @write="openOperation('set', $event)"
              @local-edit="openOperation('local_values', $event)"
            />
            <el-alert
              class="point-hint"
              :title="
                l(
                  '标准定义不代表设备支持。失败保留上次有效值；标准校验失败时保留收到的原始 Data。',
                  'Standard definitions do not prove device support. Failures retain the last good value; validation errors retain received raw Data.',
                )
              "
              type="info"
              :closable="false"
              show-icon
            />
            <el-table
              v-if="readResults.length"
              :data="readResults"
              border
              stripe
              class="result-table"
              ><el-table-column
                prop="index"
                :label="l('请求序号', 'Request index')"
                width="100" /><el-table-column
                prop="oad"
                label="OAD"
                width="120" /><el-table-column
                prop="kind"
                :label="l('逐项结果', 'Per-item result')" /><el-table-column
                prop="dar"
                label="DAR"
                width="80" /><el-table-column
                prop="message"
                :label="l('详情', 'Detail')"
            /></el-table>
          </template>
          <Dlt698Records
            v-else-if="tab === 'records'"
            :role="roleValue"
            :enabled="can('records')"
            :preview="preview"
            :busy="busy"
            :querying="busyKind === 'records'"
            :appending="busyKind === 'append'"
            :result="recordResult"
            :error="recordError"
            :append-error="recordError"
            :append-complete="appendComplete"
            @query="queryRecords"
            @cancel="cancelRead"
            @append="appendRecord"
          />
          <Dlt698Services
            v-else-if="tab === 'reports' || tab === 'proxy'"
            :key="`${roleValue}-${tab}`"
            :tab="tab"
            :role="roleValue"
            :can="can"
            :preview="preview"
            :sessions="status.sessions"
            :reports="reports"
            :routes="routes"
            :results="serviceResults"
            :error="serviceError"
            :busy="busy"
            @refresh-reports="refreshReports"
            @operation="performOperation"
            @route="saveRoute"
          />
          <template v-else-if="tab === 'config'">
            <div class="heading">
              <div>
                <h3>{{ l("连接配置", "Connection settings") }}</h3>
                <p>
                  SA <code>{{ config.server_address }}</code> · CA
                  {{ config.client_address }} · {{ stateLabel }}
                </p>
              </div>
              <el-button
                v-if="!preview"
                :disabled="!status.available || busy"
                @click="showDeviceEdit = true"
                >{{
                  l("编辑设备通信配置", "Edit device connection")
                }}</el-button
              >
            </div>
            <el-form v-if="preview" label-width="140px"
              ><DeviceFormConfig
                :model-value="previewChannel"
                v-model:media-type="previewMedia"
                :protocols="[
                  { value: 8, label: 'DL/T 698.45', conn_types: [0, 1, 2, 3] },
                ]"
                :serial-ports="[]"
            /></el-form>
            <Dlt698ProtocolConfig
              :model-value="config"
              :negotiated="status.negotiated"
              :security-backend="status.security_backend"
              :disabled="!preview && (!can('config') || busy)"
            />
            <el-alert
              v-if="configSaveError"
              :title="configSaveError"
              type="error"
              :closable="false"
            />
            <div class="toolbar">
              <el-button
                type="primary"
                :disabled="
                  !!configError(config) || busy || (!can('config') && !preview)
                "
                @click="saveConfig"
                >{{
                  preview
                    ? l("保存预览草稿", "Save preview draft")
                    : l("保存配置", "Save configuration")
                }}</el-button
              ><el-tag v-if="configSaved" type="success">{{
                configSaved
              }}</el-tag>
            </div>
          </template>
        </section>
      </el-tab-pane>
    </el-tabs>

    <Dlt698PointDialog
      v-model="showPoint"
      :point="editingPoint"
      :role="role"
      :busy="busy"
      :loading="busyKind === 'point-save'"
      :save-error="pointError"
      @save="savePoint"
    />
    <el-dialog
      v-model="showCatalog"
      :title="l('标准点表 · 选择与验证', 'Standard catalog · select and probe')"
      width="900px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-alert
        :title="
          preview
            ? l(
                '此处仅展示设计稿示例候选；完整目录由后端 standard.candidate_points 提供。',
                'Design example candidates only; full catalog comes from backend standard.candidate_points.',
              )
            : l(
                '候选默认未知；验证会显式 GET，不自动排除未知项。',
                'Candidates start unknown. Probe explicitly issues GET; unknown items remain selectable.',
              )
        "
        type="info"
        :closable="false"
      />
      <div class="toolbar">
        <el-input
          v-model="catalogSearch"
          :placeholder="l('搜索 OI / OAD / 名称', 'Search OI / OAD / name')"
          clearable
        /><el-button
          :disabled="!can('get') || !catalogSelected.length || busy"
          @click="probeCatalog"
          >{{ l("验证所选", "Probe selected") }}</el-button
        >
      </div>
      <el-table
        :data="catalogFiltered"
        row-key="oad"
        border
        stripe
        max-height="420"
        @selection-change="catalogSelected = $event"
        ><el-table-column
          type="selection"
          width="45"
          reserve-selection
        /><el-table-column prop="oad" label="OAD" width="130" /><el-table-column
          prop="name"
          :label="l('对象 / 属性', 'Object / attribute')"
          min-width="180"
        /><el-table-column
          prop="data_type"
          label="Data"
          width="100"
        /><el-table-column
          prop="unit"
          :label="l('单位', 'Unit')"
          width="70"
        /><el-table-column :label="l('元素选择', 'Element')" width="140"
          ><template #default="{ row }">{{
            row.oad.endsWith("00")
              ? l("完整属性", "Whole attribute")
              : `${l("元素", "Element")} ${parseInt(row.oad.slice(6), 16)}`
          }}</template></el-table-column
        ><el-table-column
          :label="l('能力 / 验证', 'Support / probe')"
          min-width="140"
          ><template #default="{ row }"
            ><el-tag :type="row.result?.kind === 'data' ? 'success' : 'info'">{{
              row.result
                ? row.result.kind === "dar"
                  ? `DAR = ${row.result.dar}`
                  : row.result.kind
                : l("未知", "Unknown")
            }}</el-tag></template
          ></el-table-column
        ></el-table
      >
      <el-alert
        v-if="catalogError"
        :title="catalogError"
        type="error"
        :closable="false"
      />
      <template #footer
        ><el-button @click="showCatalog = false">{{
          l("关闭", "Close")
        }}</el-button
        ><el-button
          type="primary"
          :disabled="!catalogSelected.length || busy"
          @click="addCatalogPoints"
          >{{ l("添加所选测点", "Add selected points") }}</el-button
        ></template
      >
    </el-dialog>
    <el-dialog
      v-model="showOperation"
      :title="operationTitle"
      width="680px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-alert
        :title="
          operationService === 'local_values'
            ? l(
                '仅修改服务端本地发布值，不改变远端 SET 权限。',
                'Updates local published values only; remote SET permissions are unchanged.',
              )
            : l(
                'SET / ACTION 不自动重试。超时或取消后结果未知，可重新读取核对，人工重新执行须单独触发。',
                'SET / ACTION never auto retry. After timeout/cancellation the outcome is unknown; read back or explicitly execute again.',
              )
        "
        type="warning"
        :closable="false"
      />
      <el-form label-width="120px" class="operation-form"
        ><el-form-item :label="operationService === 'action' ? 'OMD' : 'OAD'"
          ><el-input
            v-model="operationAddress"
            :disabled="operationService !== 'action'" /></el-form-item
        ><el-form-item
          v-if="operationPoint"
          :label="l('原始值', 'Previous value')"
          ><code>{{
            dataText(operationPoint.last_good || operationPoint.initial_value)
          }}</code></el-form-item
        ><el-form-item label="Data"
          ><Dlt698DataEditor
            v-model="operationData"
            :locked="operationService !== 'action' && operationPoint?.standard"
            @valid="operationValid = $event" /></el-form-item
      ></el-form>
      <el-alert
        v-if="operationError"
        :title="operationError"
        type="error"
        :closable="false"
      />
      <el-table
        v-if="operationResults.length"
        :data="operationResults"
        border
        stripe
        ><el-table-column prop="index" width="60" /><el-table-column
          prop="oad"
          label="OAD / OMD"
        /><el-table-column
          prop="kind"
          :label="l('结果', 'Result')"
        /><el-table-column prop="dar" label="DAR" width="80" /><el-table-column
          label="Data"
          ><template #default="{ row }">{{
            dataText(row.data)
          }}</template></el-table-column
        ></el-table
      >
      <template #footer
        ><el-button :disabled="busy" @click="showOperation = false">{{
          l("关闭", "Close")
        }}</el-button
        ><el-button
          v-if="operationPoint && operationService !== 'local_values'"
          :disabled="!can('get') || busy"
          :loading="busyKind === 'read-operation'"
          @click="readPoints([operationPoint], 'operation')"
          >{{ l("重新读取核对", "Read back") }}</el-button
        ><el-button
          type="primary"
          :disabled="busy || !operationValid || !can(operationService)"
          :loading="busyKind === 'operation'"
          @click="submitOperation"
          >{{ l("执行一次", "Execute once") }}</el-button
        ></template
      >
    </el-dialog>
    <AddDeviceDialog
      v-if="!preview"
      v-model:visible="showDeviceEdit"
      :channel-id="channelId"
      @success="load"
    />
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onActivated,
  onDeactivated,
  onUnmounted,
  reactive,
  ref,
  watch,
} from "vue";
import { Search, List, Plus, Upload, Download } from "@element-plus/icons-vue";
import { dlt698Api } from "@/api/dlt698Api";
import { getApiErrorMessage } from "@/api/http";
import type {
  Dlt698Config,
  Dlt698Data,
  Dlt698Feature,
  Dlt698Operation,
  Dlt698Point,
  Dlt698RecordQuery,
  Dlt698RecordResult,
  Dlt698Report,
  Dlt698Result,
  Dlt698Role,
  Dlt698Route,
  Dlt698Status,
} from "@/types/dlt698";
import type { ChannelCreateRequest } from "@/types/channel";
import {
  applyReadResults,
  configError,
  dataText,
  defaultDlt698Config,
  normalizeOad,
  validateData,
} from "@/utils/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
import Dlt698PointTable from "./Dlt698PointTable.vue";
import Dlt698PointDialog from "./Dlt698PointDialog.vue";
import Dlt698DataEditor from "./Dlt698DataEditor.vue";
import Dlt698ProtocolConfig from "./Dlt698ProtocolConfig.vue";
import Dlt698Records from "./Dlt698Records.vue";
import Dlt698Services from "./Dlt698Services.vue";
import DeviceFormConfig from "../DeviceFormConfig.vue";
import AddDeviceDialog from "../AddDeviceDialog.vue";
import { previewPoints } from "./dlt698Preview";

const props = defineProps<{
  channelId: number;
  deviceName: string;
  role: Dlt698Role;
  running: boolean;
  preview?: boolean;
}>();
const emit = defineEmits<{
  (e: "capabilities", status: Dlt698Status): void;
  (e: "config-changed"): void;
}>();
const l = useDlt698Text();
const emptyStatus = (): Dlt698Status => ({
  available: false,
  state: "stopped",
  features: {},
  sessions: [],
  security_backend: false,
});
const status = ref(emptyStatus()),
  loading = ref(false),
  loadError = ref(""),
  config = ref(defaultDlt698Config());
// Unsaved connection edits must not switch the role of a running workspace.
const roleValue = computed(() =>
  props.preview ? config.value.role : props.role,
);
const points = ref<Dlt698Point[]>([]),
  selected = ref<Dlt698Point[]>([]),
  category = ref("all"),
  search = ref(""),
  tab = ref("points");
const busy = ref(false),
  busyKind = ref(""),
  busyPointCode = ref(""),
  workspaceError = ref(""),
  notice = ref(""),
  readResults = ref<Dlt698Result[]>([]);
const showPoint = ref(false),
  editingPoint = ref<Dlt698Point>(),
  pointError = ref(""),
  fileInput = ref<HTMLInputElement>();
const interval = ref(1000),
  autoRunning = computed(() => status.value.auto_read?.running === true);
const showCatalog = ref(false),
  catalog = ref<Dlt698Point[]>([]),
  catalogSelected = ref<Dlt698Point[]>([]),
  catalogSearch = ref(""),
  catalogError = ref("");
const recordResult = ref<Dlt698RecordResult>(),
  recordError = ref(""),
  appendComplete = ref(0);
const reports = ref<Dlt698Report[]>([]),
  routes = ref<Dlt698Route[]>([]),
  serviceResults = ref<Dlt698Result[]>([]),
  serviceError = ref("");
const showOperation = ref(false),
  operationService = ref<"set" | "action" | "local_values">("set"),
  operationPoint = ref<Dlt698Point>(),
  operationAddress = ref(""),
  operationData = ref<Dlt698Data>({ type: "Null", value: null }),
  operationValid = ref(true),
  operationError = ref(""),
  operationResults = ref<Dlt698Result[]>([]);
const configSaveError = ref(""),
  configSaved = ref(""),
  showDeviceEdit = ref(false),
  previewMedia = ref<"serial" | "network">("network");
const previewChannel = reactive<ChannelCreateRequest>({
  code: "DLT698-PREVIEW",
  name: "DL/T 698",
  protocol_type: 8,
  conn_type: 1,
  ip: "127.0.0.1",
  port: 6980,
  com_port: "COM1",
  baud_rate: 9600,
  data_bits: 8,
  stop_bits: 1,
  parity: "E",
  rtu_addr: "1",
});
let epoch = 0,
  controller: AbortController | undefined,
  timer: ReturnType<typeof setTimeout> | undefined,
  active = true;
const categories = [
  { key: "all", zh: "全部", en: "All" },
  { key: "energy", zh: "电能量", en: "Energy" },
  { key: "demand", zh: "最大需量", en: "Demand" },
  { key: "variable", zh: "变量", en: "Variables" },
  { key: "harmonic", zh: "谐波", en: "Harmonics" },
  { key: "parameter", zh: "参数", en: "Parameters" },
];
const filteredPoints = computed(() =>
  points.value.filter(
    (p) =>
      (category.value === "all" || p.category === category.value) &&
      `${p.name} ${p.oad} ${p.code}`
        .toLowerCase()
        .includes(search.value.trim().toLowerCase()),
  ),
);
const readTargets = computed(() =>
  selected.value.length ? selected.value : filteredPoints.value,
);
const tabFeature = computed<Dlt698Feature>(() =>
  tab.value === "proxy" && roleValue.value === "server"
    ? "routes"
    : tab.value === "proxy"
      ? "proxy"
      : tab.value === "reports"
        ? "reports"
        : "records",
);
const catalogFiltered = computed(() =>
  catalog.value.filter((p) =>
    `${p.name} ${p.oad}`
      .toLowerCase()
      .includes(catalogSearch.value.toLowerCase()),
  ),
);
const operationTitle = computed(() =>
  operationService.value === "set"
    ? l("SET 参数写入", "SET attribute")
    : operationService.value === "action"
      ? l("ACTION 方法调用", "ACTION method")
      : l("本地发布值修改", "Edit local published value"),
);
const stateLabel = computed(() => {
  if (props.preview) return l("未连接 · 界面预览", "Disconnected · UI preview");
  const labels = {
    stopped: ["已停止", "Stopped"],
    listening: ["监听中", "Listening"],
    associating: ["关联中", "Associating"],
    associated: ["已关联", "Associated"],
    requesting: ["请求进行中", "Request in progress"],
    timeout: ["超时", "Timeout"],
    rejected: ["远端拒绝", "Rejected"],
    cancelled: ["已取消", "Cancelled"],
    lost: ["连接失效", "Connection lost"],
  };
  return l(...(labels[status.value.state] as [string, string]));
});
function can(feature: Dlt698Feature): boolean {
  if (
    props.preview ||
    !status.value.available ||
    !status.value.features[feature]?.supported
  )
    return false;
  if (
    ["get", "set", "action", "proxy", "md5", "then_get", "auto_read"].includes(
      feature,
    )
  )
    return (
      roleValue.value === "client" &&
      ["associated", "requesting"].includes(status.value.state)
    );
  if (["local_values", "simulation", "routes"].includes(feature))
    return roleValue.value === "server";
  return true;
}
function errorText(error: unknown) {
  return getApiErrorMessage(error, l("操作失败", "Operation failed"));
}
function stopPolling() {
  if (timer) clearTimeout(timer);
  timer = undefined;
}
function schedulePoll() {
  stopPolling();
  if (!active || props.preview || !status.value.available) return;
  const token = epoch,
    id = props.channelId;
  timer = setTimeout(async () => {
    try {
      const next = await dlt698Api.status(id);
      if (token !== epoch || !active) return;
      status.value = next;
      emit("capabilities", next);
      if (
        (next.auto_read?.running || roleValue.value === "server") &&
        !busy.value
      ) {
        const rows = await dlt698Api.points(id);
        if (token === epoch && active) points.value = rows;
      }
    } catch (e) {
      if (token === epoch) {
        status.value = emptyStatus();
        loadError.value = errorText(e);
        emit("capabilities", status.value);
      }
    }
    if (token === epoch) schedulePoll();
  }, 3000);
}
async function load() {
  const token = ++epoch,
    id = props.channelId;
  stopPolling();
  controller?.abort();
  busy.value = false;
  busyKind.value = "";
  busyPointCode.value = "";
  loading.value = false;
  loadError.value = "";
  status.value = emptyStatus();
  selected.value = [];
  emit("capabilities", status.value);
  readResults.value = [];
  serviceResults.value = [];
  recordResult.value = undefined;
  reports.value = [];
  routes.value = [];
  workspaceError.value = "";
  serviceError.value = "";
  recordError.value = "";
  notice.value = "";
  config.value = { ...defaultDlt698Config(), role: props.role };
  if (props.preview) {
    points.value = previewPoints();
    try {
      const raw = localStorage.getItem(`dlt698-preview-v1-${props.role}`);
      if (raw) {
        const saved = JSON.parse(raw);
        if (saved.config && !configError(saved.config))
          config.value = saved.config;
        if (Array.isArray(saved.points)) {
          saved.points.forEach((p: Dlt698Point) => {
            normalizeOad(p.oad);
            validateData(p.initial_value);
          });
          points.value = saved.points;
        }
        if (saved.channel) Object.assign(previewChannel, saved.channel);
      }
    } catch {
      workspaceError.value = l(
        "草稿无效，已恢复设计示例",
        "Invalid draft; restored design examples",
      );
      points.value = previewPoints();
    }
    previewMedia.value = [0, 3].includes(previewChannel.conn_type)
      ? "serial"
      : "network";
    return;
  }
  points.value = [];
  loading.value = true;
  try {
    const nextStatus = await dlt698Api.status(id);
    if (token !== epoch) return;
    status.value = nextStatus;
    emit("capabilities", nextStatus);
    if (nextStatus.available) {
      const [nextConfig, nextPoints] = await Promise.all([
        dlt698Api.config(id),
        dlt698Api.points(id),
      ]);
      if (token !== epoch) return;
      config.value = nextConfig;
      points.value = nextPoints;
      interval.value = nextStatus.auto_read?.interval_ms || 1000;
      schedulePoll();
    }
  } catch (e) {
    if (token === epoch) {
      status.value = emptyStatus();
      emit("capabilities", status.value);
      loadError.value = errorText(e);
    }
  } finally {
    if (token === epoch) loading.value = false;
  }
}
function persistDraft() {
  if (props.preview)
    localStorage.setItem(
      `dlt698-preview-v1-${props.role}`,
      JSON.stringify({
        config: config.value,
        points: points.value,
        channel: previewChannel,
      }),
    );
}
function resetDraft() {
  if (!props.preview) return;
  localStorage.removeItem(`dlt698-preview-v1-${props.role}`);
  points.value = previewPoints();
  config.value = { ...defaultDlt698Config(), role: props.role };
  selected.value = [];
  recordResult.value = undefined;
  workspaceError.value = "";
  notice.value = "";
}
async function run(
  kind: string,
  targetError: { value: string },
  task: (token: number, id: number) => Promise<void>,
  pointCode = "",
) {
  if (busy.value) return;
  const token = epoch,
    id = props.channelId;
  busy.value = true;
  busyKind.value = kind;
  busyPointCode.value = pointCode;
  targetError.value = "";
  notice.value = "";
  try {
    await task(token, id);
  } catch (e) {
    if (token === epoch) targetError.value = errorText(e);
  } finally {
    if (token === epoch) {
      busy.value = false;
      busyKind.value = "";
      busyPointCode.value = "";
    }
  }
}
function openPoint(point?: Dlt698Point) {
  editingPoint.value = point;
  pointError.value = "";
  showPoint.value = true;
}
async function setInlineValue(point: Dlt698Point, data: Dlt698Data) {
  const service = roleValue.value === "server" ? "local_values" : "set";
  if (props.preview || busy.value || !can(service)) return;
  await run(
    "point-value",
    workspaceError,
    async (token, id) => {
      const results = await dlt698Api.operation(id, {
        service,
        items: [{ oad: point.oad, data }],
      });
      if (token !== epoch) return;
      const result = results[0];
      if (
        !result ||
        (result.kind !== "data" && !(result.kind === "dar" && result.dar === 0))
      ) {
        throw new Error(
          result?.message ||
            (result?.kind === "dar"
              ? `DAR = ${result.dar}`
              : l(
                  "写入结果未知，请重新读取确认",
                  "Write outcome unknown; read again to confirm",
                )),
        );
      }
      const rows = await dlt698Api.points(id);
      if (token === epoch) points.value = rows;
    },
    point.code,
  );
}
async function saveInlinePoint(point: Dlt698Point, original: Dlt698Point) {
  if (busy.value) return;
  editingPoint.value = original;
  await savePoint(point);
}
async function savePoint(point: Dlt698Point) {
  await run(
    "point-save",
    pointError,
    async (token, id) => {
      if (
        points.value.some(
          (p) => p.code === point.code && p.code !== editingPoint.value?.code,
        )
      )
        throw new Error(l("测点编码已存在", "Point code already exists"));
      let saved = props.preview
        ? point
        : await dlt698Api.savePoint(id, point, editingPoint.value?.code);
      if (token !== epoch) return;
      if (
        !props.preview &&
        editingPoint.value &&
        editingPoint.value.oad === saved.oad &&
        editingPoint.value.data_type === saved.data_type
      )
        saved = { ...editingPoint.value, ...saved };
      if (
        props.preview &&
        editingPoint.value &&
        (editingPoint.value.oad !== point.oad ||
          editingPoint.value.data_type !== point.data_type)
      )
        saved = {
          ...saved,
          result: undefined,
          last_good: undefined,
          last_good_at: undefined,
        };
      const i = points.value.findIndex(
        (p) => p.code === editingPoint.value?.code,
      );
      if (i >= 0) points.value.splice(i, 1, saved);
      else points.value.push(saved);
      persistDraft();
      showPoint.value = false;
    },
    editingPoint.value?.code || point.code,
  );
}
async function deletePoint(point: Dlt698Point) {
  await run("point-delete", workspaceError, async (token, id) => {
    if (!props.preview) await dlt698Api.deletePoint(id, point.code);
    if (token !== epoch) return;
    points.value = points.value.filter((p) => p.code !== point.code);
    selected.value = selected.value.filter((p) => p.code !== point.code);
    persistDraft();
  });
}
async function readPoints(
  rows: Dlt698Point[],
  source: "point" | "batch" | "operation",
) {
  if (!can("get") || !rows.length) return;
  await run(
    `read-${source}`,
    workspaceError,
    async (token, id) => {
      controller = new AbortController();
      const codes = rows.map((p) => p.code);
      try {
        const results = await dlt698Api.read(id, codes, controller.signal);
        if (token !== epoch) return;
        readResults.value = results;
        points.value = applyReadResults(points.value, results, codes);
      } catch (e) {
        if (token !== epoch) return;
        const results: Dlt698Result[] = rows.map((p, index) => ({
          index,
          oad: p.oad,
          kind: "transport_error",
          message: controller?.signal.aborted
            ? l(
                "读取已取消；保留上次有效值",
                "Read cancelled; last good value retained",
              )
            : errorText(e),
        }));
        readResults.value = results;
        points.value = applyReadResults(points.value, results, codes);
        throw e;
      }
    },
    source === "batch" ? "" : rows[0].code,
  );
}
function cancelRead() {
  controller?.abort();
}
async function setAutoRead() {
  await run("auto-read", workspaceError, async (token, id) => {
    await dlt698Api.autoRead(
      id,
      !autoRunning.value,
      interval.value,
      readTargets.value.map((p) => p.code),
    );
    const next = await dlt698Api.status(id);
    if (token === epoch) status.value = next;
  });
}
async function openCatalog() {
  showCatalog.value = true;
  catalogSelected.value = [];
  catalogError.value = "";
  if (props.preview) {
    catalog.value = previewPoints()
      .filter((p) => p.standard)
      .map((p) => ({
        ...p,
        result: undefined,
        last_good: undefined,
        last_good_at: undefined,
      }));
    return;
  }
  await run("catalog", catalogError, async (token, id) => {
    const rows = await dlt698Api.catalog(id, config.value);
    if (token === epoch) catalog.value = rows;
  });
}
async function probeCatalog() {
  await run("probe", catalogError, async (token, id) => {
    const rows = catalogSelected.value.slice();
    controller = new AbortController();
    const results = await dlt698Api.probe(
      id,
      rows.map((p) => p.oad),
      controller.signal,
    );
    if (token === epoch)
      catalog.value = applyReadResults(
        catalog.value,
        results,
        rows.map((p) => p.code),
      );
  });
}
async function addCatalogPoints() {
  await run("catalog", catalogError, async (token, id) => {
    let count = 0;
    for (const point of catalogSelected.value) {
      if (points.value.some((p) => p.code === point.code)) continue;
      const saved = props.preview
        ? point
        : await dlt698Api.savePoint(id, point);
      if (token !== epoch) return;
      points.value.push(saved);
      count++;
    }
    persistDraft();
    showCatalog.value = false;
    notice.value = `${l("已添加测点", "Points added")}: ${count}`;
  });
}
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file || !can("import")) return;
  await run("import", workspaceError, async (token, id) => {
    await dlt698Api.importPoints(id, file);
    const rows = await dlt698Api.points(id);
    if (token === epoch) points.value = rows;
  });
  input.value = "";
}
function openOperation(
  service: "set" | "action" | "local_values",
  point?: Dlt698Point,
) {
  operationService.value = service;
  operationPoint.value = point;
  operationAddress.value = point?.oad || "F0010100";
  operationData.value = JSON.parse(
    JSON.stringify(
      point?.last_good || point?.initial_value || { type: "Null", value: null },
    ),
  );
  operationResults.value = [];
  operationError.value = "";
  showOperation.value = true;
}
async function submitOperation() {
  if (
    props.preview ||
    !can(operationService.value) ||
    !operationValid.value ||
    busy.value
  )
    return;
  try {
    normalizeOad(operationAddress.value);
    validateData(operationData.value);
  } catch (e) {
    operationError.value = errorText(e);
    return;
  }
  const service = operationService.value;
  const request: Dlt698Operation = {
    service,
    items: [
      {
        [service === "action" ? "omd" : "oad"]: operationAddress.value,
        data: operationData.value,
      },
    ],
  };
  await run("operation", operationError, async (token, id) => {
    try {
      const results = await dlt698Api.operation(id, request);
      if (token === epoch) {
        operationResults.value = results;
      }
    } catch (e) {
      if (token === epoch)
        operationResults.value = [
          {
            index: 0,
            oad: operationAddress.value,
            kind: service === "local_values" ? "transport_error" : "unknown",
            message: errorText(e),
          },
        ];
      throw e;
    }
    // A failed refresh must not turn a known SET/ACTION response into unknown.
    if (token === epoch) {
      try {
        const rows = await dlt698Api.points(id);
        if (token === epoch) points.value = rows;
      } catch (e) {
        if (token === epoch) workspaceError.value = errorText(e);
      }
    }
  });
}
async function queryRecords(query: Dlt698RecordQuery) {
  if (!can("records")) return;
  await run("records", recordError, async (token, id) => {
    controller = new AbortController();
    recordResult.value = undefined;
    const result = await dlt698Api.records(id, query, controller.signal);
    if (token === epoch) recordResult.value = result;
  });
}
async function appendRecord(query: Dlt698RecordQuery, row: Dlt698Data[]) {
  if (roleValue.value !== "server" || (!props.preview && !can("records")))
    return;
  await run("append", recordError, async (token, id) => {
    if (!props.preview) await dlt698Api.appendRecord(id, query, row);
    if (token !== epoch) return;
    if (props.preview) {
      recordResult.value ||= {
        columns: query.columns.map((oad) => ({ oad, name: "Data" })),
        rows: [],
        blocks: 0,
      };
      recordResult.value.rows.push(row);
    }
    appendComplete.value++;
  });
}
async function refreshReports() {
  await run("reports", serviceError, async (token, id) => {
    const rows = await dlt698Api.reports(id);
    if (token === epoch) reports.value = rows;
  });
}
async function performOperation(request: Dlt698Operation) {
  const feature: Dlt698Feature =
    request.service === "report" ? "reports" : request.service;
  if (!can(feature)) return;
  await run("service", serviceError, async (token, id) => {
    try {
      const results = await dlt698Api.operation(id, request);
      if (token === epoch) serviceResults.value = results;
    } catch (e) {
      if (token === epoch)
        serviceResults.value = request.items.map((item, index) => ({
          index,
          oad: item.oad || item.omd || item.tsa || "",
          kind:
            request.service === "md5" ||
            (request.service === "proxy" &&
              request.proxy_service?.startsWith("Get"))
              ? "transport_error"
              : "unknown",
          tsa: item.tsa,
          message: errorText(e),
        }));
      throw e;
    }
  });
}
async function saveRoute(route: Dlt698Route) {
  await run("routes", serviceError, async (token, id) => {
    await dlt698Api.saveRoute(id, route);
    const rows = await dlt698Api.routes(id);
    if (token === epoch) routes.value = rows;
  });
}
async function saveConfig() {
  await run("config", configSaveError, async (token, id) => {
    const invalid = configError(config.value);
    if (invalid) throw new Error(invalid);
    if (props.preview) persistDraft();
    else {
      const saved = await dlt698Api.saveConfig(id, config.value);
      if (token !== epoch) return;
      config.value = saved;
      emit("config-changed");
    }
    configSaved.value = props.preview
      ? l("预览草稿已保存", "Preview draft saved")
      : l("配置已保存", "Configuration saved");
  });
}
function exportDraft() {
  const blob = new Blob(
    [
      JSON.stringify(
        {
          preview: true,
          config: config.value,
          channel: previewChannel,
          points: points.value,
          records: recordResult.value,
        },
        null,
        2,
      ),
    ],
    { type: "application/json" },
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `dlt698-${roleValue.value}-preview.json`;
  link.click();
  URL.revokeObjectURL(url);
}
const businessTabs = computed(() => [
  {
    name: "points",
    label:
      roleValue.value === "client"
        ? l("测点读取", "Point reads")
        : l("测点管理", "Point management"),
  },
  {
    name: "records",
    label:
      roleValue.value === "client"
        ? l("记录查询", "Record queries")
        : l("记录管理", "Record management"),
  },
  {
    name: "reports",
    label:
      roleValue.value === "client"
        ? l("上报接收", "Received reports")
        : l("主动上报", "Send reports"),
  },
  {
    name: "proxy",
    label:
      roleValue.value === "client"
        ? l("代理服务", "Proxy services")
        : l("代理路由", "Proxy routes"),
  },
  { name: "config", label: l("连接配置", "Connection settings") },
]);
watch(() => [props.channelId, props.role, props.preview], load, {
  immediate: true,
});
watch(
  () => props.running,
  () => {
    if (!props.preview) load();
  },
);
watch(tab, async (name) => {
  serviceResults.value = [];
  serviceError.value = "";
  if (name === "reports" && can("reports")) await refreshReports();
  if (name === "proxy" && can("routes"))
    await run("routes", serviceError, async (token, id) => {
      const rows = await dlt698Api.routes(id);
      if (token === epoch) routes.value = rows;
    });
});
onActivated(() => {
  active = true;
  if (!props.preview && status.value.available) schedulePoll();
});
onDeactivated(() => {
  active = false;
  stopPolling();
  controller?.abort();
});
onUnmounted(() => {
  active = false;
  epoch++;
  stopPolling();
  controller?.abort();
});
</script>

<style scoped lang="scss">
.dlt698-panel {
  display: grid;
  gap: 12px;
  width: 100%;
  min-width: 0;
}
.heading-status {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.business-tabs {
  min-width: 0;
  :deep(.el-tabs__header) {
    margin: 0 0 15px;
  }
  :deep(.el-tabs__content) {
    overflow: visible;
  }
}
.workspace {
  background: var(--panel-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  min-width: 0;
}
.heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 17px;
}
p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.categories,
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
  :deep(.el-button + .el-button) {
    margin-left: 0;
  }
}
.search {
  width: 260px;
}
.point-hint,
.result-table {
  margin-top: 16px;
}
.unavailable-hint {
  margin-bottom: 16px;
}
.muted {
  color: var(--text-secondary);
  font-size: 12px;
}
.operation-form {
  margin-top: 20px;
}
@media (max-width: 900px) {
  .workspace {
    padding: 12px;
  }
  .search {
    width: 100%;
  }
  .heading {
    align-items: flex-start;
  }
}
</style>
