<template>
  <div v-loading="loading" class="ua-simulation">
    <OpcUaPageHeading
      :title="t('opcua.simulation')"
      :description="t('opcua.simulationDescription')"
    >
      <div class="ua-actions">
        <el-tag v-if="dirty" type="warning" effect="plain">{{
          t("opcua.simulationUnsaved")
        }}</el-tag>
        <el-button :disabled="saving || toggling" @click="reload">{{
          t("opcua.refresh")
        }}</el-button>
        <el-button
          type="primary"
          :disabled="!canEdit || !dirty"
          :loading="saving"
          @click="save"
        >
          {{ t("opcua.saveConfig") }}
        </el-button>
      </div>
    </OpcUaPageHeading>
    <el-alert
      v-if="running"
      :title="t('opcua.simulationRunningHint')"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="!loaded && !loading"
      :title="t('opcua.simulationLoadFailed')"
      type="error"
      :closable="false"
      show-icon
    />

    <el-tabs v-model="tab" class="simulation-tabs">
      <el-tab-pane :label="t('simConfig.tabSelect')" name="select">
        <div class="simulation-selection">
          <section class="ua-section variable-panel">
            <div class="ua-section-heading">
              <h3>
                {{ t("opcua.variables") }} <span>{{ nodes.length }}</span>
              </h3>
              <el-tag size="small" type="info">{{
                t("opcua.simulationSelectedCount", { count: rules.length })
              }}</el-tag>
            </div>
            <el-input
              v-model="nodeSearch"
              :placeholder="t('opcua.nodeSearch')"
              clearable
              :prefix-icon="Search"
            />
            <div class="variable-select-all">
              <el-checkbox
                :model-value="allFilteredSelected"
                :indeterminate="someFilteredSelected && !allFilteredSelected"
                :disabled="!canEdit || !filteredNodes.length"
                @change="
                  (value: string | number | boolean) =>
                    selectFiltered(Boolean(value))
                "
              >
                {{ t("opcua.simulationSelectFiltered") }}
              </el-checkbox>
              <span class="ua-muted">{{ filteredNodes.length }}</span>
            </div>
            <div class="variable-list">
              <div
                v-for="node in pagedNodes"
                :key="node.node_id"
                class="variable-row"
                :class="{ 'is-selected': ruleIds.has(node.node_id) }"
                @click="selectNode(node, !ruleIds.has(node.node_id))"
              >
                <el-checkbox
                  :model-value="ruleIds.has(node.node_id)"
                  :disabled="!canEdit"
                  :aria-label="node.browse_name"
                  @click.stop
                  @change="
                    (value: string | number | boolean) =>
                      selectNode(node, Boolean(value))
                  "
                />
                <span class="variable-label">
                  <strong :title="node.browse_name">{{
                    node.browse_name
                  }}</strong>
                  <span class="ua-code" :title="node.node_id">{{
                    node.node_id
                  }}</span>
                </span>
                <el-tag size="small" type="info" effect="plain">{{
                  node.data_type
                }}</el-tag>
              </div>
              <el-empty
                v-if="!filteredNodes.length"
                :image-size="64"
                :description="
                  nodes.length
                    ? t('simConfig.noSearchResults')
                    : t('opcua.simulationNoVariables')
                "
              />
            </div>
            <el-pagination
              v-model:current-page="nodePage"
              :total="filteredNodes.length"
              :page-size="50"
              layout="prev, pager, next"
              small
            />
          </section>

          <section class="ua-section rule-panel">
            <div class="ua-section-heading">
              <h3>
                {{
                  t("opcua.simulationSelectedCount", { count: rules.length })
                }}
              </h3>
              <el-button
                type="danger"
                text
                :disabled="!canEdit || !rules.length"
                @click="clearRules"
                >{{ t("simConfig.clearAll") }}</el-button
              >
            </div>
            <el-input
              v-model="ruleSearch"
              :placeholder="t('opcua.nodeSearch')"
              clearable
              :prefix-icon="Search"
              class="rule-search"
            />
            <el-table
              :data="pagedRules"
              stripe
              :empty-text="t('simConfig.noSelected')"
              max-height="490"
            >
              <el-table-column
                :label="t('opcua.boundVariable')"
                min-width="180"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  <div>
                    {{ nodeMap.get(row.node_id)?.browse_name || row.node_id }}
                  </div>
                  <span class="ua-muted ua-code">{{ row.node_id }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('simConfig.method')" width="140">
                <template #default="{ row }">
                  <el-select
                    v-model="row.kind"
                    :disabled="!canEdit || !nodeMap.has(row.node_id)"
                    size="small"
                  >
                    <el-option
                      v-for="kind in kindsFor(row.node_id)"
                      :key="kind"
                      :label="t('opcua.' + kind)"
                      :value="kind"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('opcua.simulationParameters')"
                min-width="210"
              >
                <template #default="{ row }">
                  <el-input
                    v-if="row.kind === 'fixed'"
                    v-model="row.valueText"
                    :disabled="!canEdit"
                    size="small"
                    :aria-label="t('simConfig.fixedValue')"
                    :placeholder="fixedPlaceholder(row.node_id)"
                  />
                  <div v-else class="range-inputs">
                    <el-input-number
                      v-model="row.minimum"
                      :disabled="!canEdit"
                      :controls="false"
                      size="small"
                      :aria-label="t('opcua.minimum')"
                    />
                    <span>~</span>
                    <el-input-number
                      v-model="row.maximum"
                      :disabled="!canEdit"
                      :controls="false"
                      size="small"
                      :aria-label="t('opcua.maximum')"
                    />
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('opcua.enabled')"
                width="70"
                align="center"
              >
                <template #default="{ row }"
                  ><el-switch
                    v-model="row.enabled"
                    :disabled="!canEdit"
                    :aria-label="t('opcua.enabled')"
                /></template>
              </el-table-column>
              <el-table-column
                :label="t('opcua.actions')"
                width="115"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button link type="primary" @click="editRule(row)">{{
                    t("opcua.edit")
                  }}</el-button>
                  <el-button
                    link
                    type="danger"
                    :disabled="!canEdit"
                    @click="removeRule(row.node_id)"
                    >{{ t("opcua.delete") }}</el-button
                  >
                </template>
              </el-table-column>
            </el-table>
            <el-pagination
              v-model:current-page="rulePage"
              :total="filteredRules.length"
              :page-size="10"
              layout="total, prev, pager, next"
              small
            />
          </section>
        </div>
        <p class="ua-note">{{ t("opcua.simulationHint") }}</p>
      </el-tab-pane>

      <el-tab-pane :label="t('simConfig.tabData')" name="data">
        <section class="ua-section">
          <div class="ua-section-heading">
            <h3>
              {{ t("simConfig.dataCount", { count: savedRules.length }) }}
            </h3>
            <div class="ua-actions">
              <el-switch
                v-model="autoRefresh"
                :active-text="t('simConfig.autoRefresh')"
              />
              <el-select
                v-model="pollInterval"
                :disabled="!autoRefresh"
                class="refresh-interval"
                :aria-label="t('opcua.simulationRefreshInterval')"
              >
                <el-option
                  v-for="ms in [500, 1000, 2000, 5000]"
                  :key="ms"
                  :label="`${ms / 1000} s`"
                  :value="ms"
                />
              </el-select>
              <el-button
                :icon="Refresh"
                :disabled="!running || !savedRules.length || toggling"
                :loading="reading"
                @click="refreshData"
                >{{ t("opcua.refresh") }}</el-button
              >
              <el-button
                :icon="VideoPause"
                :disabled="!canControl || !hasActiveRules"
                :loading="toggling"
                @click="setPaused(true)"
                >{{ t("opcua.pause") }}</el-button
              >
              <el-button
                type="success"
                :icon="CaretRight"
                :disabled="!canControl || !hasPausedRules"
                :loading="toggling"
                @click="setPaused(false)"
                >{{ t("opcua.resume") }}</el-button
              >
            </div>
          </div>
          <el-alert
            v-if="dirty"
            :title="t('opcua.simulationSavedDataHint')"
            type="warning"
            :closable="false"
          />
          <el-alert
            v-if="!running"
            :title="t('opcua.simulationStoppedHint')"
            type="info"
            :closable="false"
          />
          <el-alert
            v-if="dataError"
            :title="dataError"
            type="error"
            :closable="false"
          />
          <el-table
            :data="pagedDataRules"
            stripe
            :empty-text="t('simConfig.noSelected')"
          >
            <el-table-column
              :label="t('opcua.boundVariable')"
              min-width="240"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <div>
                  {{ nodeMap.get(row.node_id)?.browse_name || row.node_id }}
                </div>
                <span class="ua-muted ua-code">{{ row.node_id }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('opcua.dataType')" width="110"
              ><template #default="{ row }">{{
                nodeMap.get(row.node_id)?.data_type || "—"
              }}</template></el-table-column
            >
            <el-table-column :label="t('simConfig.method')" width="100"
              ><template #default="{ row }">{{
                row.kind ? t("opcua." + row.kind) : "—"
              }}</template></el-table-column
            >
            <el-table-column
              prop="interval_ms"
              :label="t('opcua.intervalMs')"
              width="145"
            />
            <el-table-column
              :label="t('opcua.currentValue')"
              min-width="140"
              show-overflow-tooltip
              ><template #default="{ row }">{{
                running ? displayValue(values[row.node_id]?.value) : "—"
              }}</template></el-table-column
            >
            <el-table-column
              :label="t('opcua.quality')"
              min-width="160"
              show-overflow-tooltip
              ><template #default="{ row }">{{
                valueErrors[row.node_id] ||
                values[row.node_id]?.status_code ||
                "—"
              }}</template></el-table-column
            >
            <el-table-column :label="t('opcua.state')" width="120">
              <template #default="{ row }"
                ><el-tag :type="stateType(row)" size="small">{{
                  stateLabel(row)
                }}</el-tag></template
              >
            </el-table-column>
            <el-table-column
              :label="t('opcua.lastError')"
              min-width="180"
              show-overflow-tooltip
              ><template #default="{ row }">{{
                states[row.node_id]?.error || "—"
              }}</template></el-table-column
            >
          </el-table>
          <div class="data-footer">
            <span class="ua-muted">{{
              sampledAt ? t("opcua.sampledAt") + ": " + sampledAt : ""
            }}</span>
            <el-pagination
              v-model:current-page="dataPage"
              :total="savedRules.length"
              :page-size="20"
              layout="total, prev, pager, next"
              small
            />
          </div>
        </section>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="editorOpen"
      :title="t('opcua.editRule')"
      width="640px"
      :close-on-click-modal="false"
      append-to-body
      class="ua-simulation-dialog"
    >
      <template v-if="editor">
        <p class="editor-variable">
          {{ nodeMap.get(editor.node_id)?.browse_name || editor.node_id
          }}<br /><span class="ua-code">{{ editor.node_id }}</span>
        </p>
        <el-form
          label-position="top"
          :disabled="!canEdit"
          class="simulation-editor-form"
        >
          <el-form-item :label="t('simConfig.method')"
            ><el-select v-model="editor.kind"
              ><el-option
                v-for="kind in kindsFor(editor.node_id)"
                :key="kind"
                :label="t('opcua.' + kind)"
                :value="kind" /></el-select
          ></el-form-item>
          <el-form-item :label="t('opcua.enabled')"
            ><el-switch v-model="editor.enabled"
          /></el-form-item>
          <el-form-item
            v-if="editor.kind === 'fixed'"
            :label="t('simConfig.fixedValue')"
            class="editor-wide"
            ><el-input
              v-model="editor.valueText"
              :placeholder="fixedPlaceholder(editor.node_id)"
          /></el-form-item>
          <template v-else>
            <el-form-item :label="t('opcua.minimum')"
              ><el-input-number v-model="editor.minimum" :controls="false"
            /></el-form-item>
            <el-form-item :label="t('opcua.maximum')"
              ><el-input-number v-model="editor.maximum" :controls="false"
            /></el-form-item>
            <template v-if="editor.kind === 'sine'">
              <el-form-item :label="t('opcua.periodSeconds')"
                ><el-input-number
                  v-model="editor.period_s"
                  :min="0.01"
                  :max="86400"
                  :controls="false"
              /></el-form-item>
              <el-form-item :label="t('opcua.offsetSeconds')"
                ><el-input-number
                  v-model="editor.offset_s"
                  :min="-86400"
                  :max="86400"
                  :controls="false"
              /></el-form-item>
            </template>
            <el-form-item
              v-if="editor.kind === 'step'"
              :label="t('opcua.stepSize')"
              ><el-input-number v-model="editor.step" :controls="false"
            /></el-form-item>
          </template>
          <el-form-item :label="t('opcua.intervalMs')"
            ><el-input-number
              v-model="editor.interval_ms"
              :min="50"
              :max="3600000"
              :precision="0"
              :controls="false"
          /></el-form-item>
          <el-form-item :label="t('opcua.writePolicy')"
            ><el-select v-model="editor.write_policy"
              ><el-option
                v-for="policy in ['pause', 'overwrite', 'reject']"
                :key="policy"
                :label="t('opcua.policy' + policy)"
                :value="policy" /></el-select
          ></el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="editorOpen = false">{{
          t("opcua.cancel")
        }}</el-button>
        <el-button type="primary" :disabled="!canEdit" @click="applyEditor">{{
          t("opcua.simulationApplyRule")
        }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Search,
  Refresh,
  VideoPause,
  CaretRight,
} from "@element-plus/icons-vue";
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import {
  getOpcUaFeatures,
  listOpcUaVariables,
  saveOpcUaFeature,
  getOpcUaCapabilities,
  readOpcUaServerValues,
  pauseOpcUaSimulation,
} from "@/api/opcuaApi";
import type { OpcUaVariable, OpcUaValueSnapshot } from "@/api/opcuaApi";
import { showError } from "@/api/http";
import { OpcUaScalarError } from "@/utils/opcuaValue";
import {
  createSimulationRule,
  isNumericVariable,
  ruleToForm,
  serializeSimulationRule,
  simulationValueText,
  SimulationRuleError,
} from "@/utils/opcuaSimulation";
import type {
  SimulationKind,
  SimulationRuleForm,
  OpcUaSimulationRule,
} from "@/utils/opcuaSimulation";

const props = withDefaults(
  defineProps<{
    channelId: number;
    running: boolean;
    active?: boolean;
    selectedNodeId?: string;
    revision?: number;
  }>(),
  { active: true, revision: 0 },
);
const { t } = useI18n();
const tab = ref("select"),
  nodes = ref<OpcUaVariable[]>([]),
  rules = ref<SimulationRuleForm[]>([]),
  savedRules = ref<OpcUaSimulationRule[]>([]);
const loading = ref(false),
  loaded = ref(false),
  saving = ref(false),
  toggling = ref(false),
  reading = ref(false);
const baseline = ref("[]");
const dirty = computed(
  () => loaded.value && JSON.stringify(rules.value) !== baseline.value,
);
const canEdit = computed(
  () => loaded.value && !loading.value && !saving.value && !toggling.value,
);
const nodeMap = computed(
  () => new Map(nodes.value.map((node) => [node.node_id, node])),
);
const ruleIds = computed(
  () => new Set(rules.value.map((rule) => rule.node_id)),
);
const nodeSearch = ref(""),
  ruleSearch = ref(""),
  nodePage = ref(1),
  rulePage = ref(1),
  dataPage = ref(1);
function matches(id: string, search: string) {
  const node = nodeMap.value.get(id);
  return `${id} ${node?.browse_name || ""} ${node?.point_code || ""}`
    .toLowerCase()
    .includes(search.trim().toLowerCase());
}
const filteredNodes = computed(() =>
  nodes.value.filter((node) => matches(node.node_id, nodeSearch.value)),
);
const filteredRules = computed(() =>
  rules.value.filter((rule) => matches(rule.node_id, ruleSearch.value)),
);
const pagedNodes = computed(() =>
  filteredNodes.value.slice((nodePage.value - 1) * 50, nodePage.value * 50),
);
const pagedRules = computed(() =>
  filteredRules.value.slice((rulePage.value - 1) * 10, rulePage.value * 10),
);
const pagedDataRules = computed(() =>
  savedRules.value.slice((dataPage.value - 1) * 20, dataPage.value * 20),
);
const allFilteredSelected = computed(
  () =>
    filteredNodes.value.length > 0 &&
    filteredNodes.value.every((node) => ruleIds.value.has(node.node_id)),
);
const someFilteredSelected = computed(() =>
  filteredNodes.value.some((node) => ruleIds.value.has(node.node_id)),
);
const editorOpen = ref(false),
  editor = ref<SimulationRuleForm | null>(null);
const autoRefresh = ref(true),
  pollInterval = ref(1000),
  sampledAt = ref(""),
  dataError = ref("");
const values = ref<Record<string, OpcUaValueSnapshot>>({}),
  valueErrors = ref<Record<string, string>>({});
type RuleState = { node_id: string; paused: boolean; error: string | null };
const states = ref<Record<string, RuleState>>({}),
  simulationRunning = ref(false);
const canControl = computed(
  () =>
    props.running &&
    loaded.value &&
    simulationRunning.value &&
    !loading.value &&
    !saving.value &&
    !toggling.value &&
    !reading.value,
);
const hasActiveRules = computed(() =>
  savedRules.value.some(
    (rule) => rule.enabled && states.value[rule.node_id]?.paused === false,
  ),
);
const hasPausedRules = computed(() =>
  savedRules.value.some(
    (rule) => rule.enabled && states.value[rule.node_id]?.paused === true,
  ),
);
let generation = 0,
  pollingGeneration = 0,
  disposed = false;
let timer: ReturnType<typeof setTimeout> | undefined;
let pendingRead: Promise<void> | null = null;

function kindsFor(id: string): SimulationKind[] {
  const node = nodeMap.value.get(id);
  return node && isNumericVariable(node)
    ? ["fixed", "random", "sine", "step"]
    : ["fixed"];
}
function fixedPlaceholder(id: string) {
  const type = nodeMap.value.get(id)?.data_type;
  if (type === "Boolean") return "true / false";
  if (type === "DateTime") return "2026-10-02T00:00:00Z";
  if (type === "ByteString") return "Base64";
  return type || t("simConfig.fixedValue");
}
function selectNode(node: OpcUaVariable, selected: boolean) {
  if (!canEdit.value) return;
  if (!selected) removeRule(node.node_id);
  else if (!ruleIds.value.has(node.node_id)) {
    if (rules.value.length >= 1000)
      return void ElMessage.warning(t("opcua.simulationRuleLimit"));
    rules.value.push(createSimulationRule(node));
  }
}
function selectFiltered(selected: boolean) {
  if (!canEdit.value) return;
  if (selected) {
    const additions = filteredNodes.value.filter(
      (node) => !ruleIds.value.has(node.node_id),
    );
    if (rules.value.length + additions.length > 1000)
      return void ElMessage.warning(t("opcua.simulationRuleLimit"));
    rules.value.push(...additions.map(createSimulationRule));
  } else {
    const ids = new Set(filteredNodes.value.map((node) => node.node_id));
    rules.value = rules.value.filter((rule) => !ids.has(rule.node_id));
  }
}
function removeRule(id: string) {
  if (canEdit.value)
    rules.value = rules.value.filter((rule) => rule.node_id !== id);
}
async function clearRules() {
  try {
    await ElMessageBox.confirm(
      t("opcua.simulationClearConfirm"),
      t("simConfig.clearAll"),
      { type: "warning" },
    );
    if (canEdit.value) rules.value = [];
  } catch {
    /* Cancel keeps the selection. */
  }
}
function editRule(rule: SimulationRuleForm) {
  editor.value = { ...rule };
  editorOpen.value = true;
}
function validationError(error: unknown, id: string) {
  const message =
    error instanceof SimulationRuleError
      ? t("opcua." + error.key)
      : error instanceof OpcUaScalarError
        ? t(error.type === "Boolean" ? "opcua.badBoolean" : "opcua.badNumber", {
            type: error.type,
          })
        : String(error);
  ElMessage.warning(`${nodeMap.value.get(id)?.browse_name || id}: ${message}`);
}
function applyEditor() {
  if (!canEdit.value || !editor.value) return;
  try {
    serializeSimulationRule(
      editor.value,
      nodeMap.value.get(editor.value.node_id),
    );
    const index = rules.value.findIndex(
      (rule) => rule.node_id === editor.value!.node_id,
    );
    if (index >= 0) rules.value[index] = { ...editor.value };
    editorOpen.value = false;
  } catch (error) {
    validationError(error, editor.value.node_id);
  }
}
function selectRequestedRule() {
  if (!props.selectedNodeId || !loaded.value) return;
  tab.value = "select";
  ruleSearch.value = "";
  const index = rules.value.findIndex(
    (rule) => rule.node_id === props.selectedNodeId,
  );
  if (index >= 0) {
    rulePage.value = Math.floor(index / 10) + 1;
    editRule(rules.value[index]);
  } else {
    nodeSearch.value = props.selectedNodeId;
  }
}
async function load(selectRequested = false, preserveDraft = false) {
  const draft = preserveDraft ? rules.value : null;
  const epoch = ++generation,
    channel = props.channelId;
  stopPolling();
  loading.value = true;
  loaded.value = false;
  editorOpen.value = false;
  clearData();
  try {
    const [features, variables] = await Promise.all([
      getOpcUaFeatures(channel),
      listOpcUaVariables(channel),
    ]);
    if (epoch !== generation || disposed) return;
    nodes.value = variables.nodes;
    savedRules.value = features.simulation?.rules || [];
    const savedForms = savedRules.value.map(ruleToForm);
    rules.value = draft ?? savedForms;
    baseline.value = JSON.stringify(savedForms);
    loaded.value = true;
    if (selectRequested) selectRequestedRule();
  } catch (error) {
    if (epoch === generation && !disposed) showError(error);
  } finally {
    if (epoch === generation && !disposed) {
      loading.value = false;
      restartPolling();
    }
  }
}
async function reload() {
  if (dirty.value) {
    try {
      await ElMessageBox.confirm(
        t("opcua.simulationDiscardConfirm"),
        t("opcua.refresh"),
        { type: "warning" },
      );
    } catch {
      return;
    }
  }
  await load();
}
async function save() {
  if (!canEdit.value) return;
  const config: OpcUaSimulationRule[] = [];
  for (const rule of rules.value) {
    try {
      config.push(
        serializeSimulationRule(rule, nodeMap.value.get(rule.node_id)),
      );
    } catch (error) {
      validationError(error, rule.node_id);
      return;
    }
  }
  saving.value = true;
  const epoch = generation,
    channel = props.channelId;
  try {
    await saveOpcUaFeature(channel, "simulation", { rules: config });
    if (epoch !== generation || disposed) return;
    savedRules.value = config;
    rules.value = config.map(ruleToForm);
    baseline.value = JSON.stringify(rules.value);
    ElMessage.success(t("opcua.configSaved"));
    restartPolling();
  } catch (error) {
    if (epoch === generation && !disposed) showError(error);
  } finally {
    saving.value = false;
  }
}
function clearData() {
  values.value = {};
  valueErrors.value = {};
  states.value = {};
  sampledAt.value = "";
  dataError.value = "";
  simulationRunning.value = false;
}
function displayValue(value: unknown) {
  return value == null ? "—" : simulationValueText(value);
}
function stateLabel(rule: OpcUaSimulationRule) {
  if (!rule.enabled) return t("opcua.disabled");
  if (!props.running) return t("opcua.stopped");
  const state = states.value[rule.node_id];
  if (state?.error) return t("opcua.simulationError");
  if (!simulationRunning.value || !state) return t("opcua.notRunning");
  return t(state.paused ? "opcua.simulationPaused" : "opcua.running");
}
function stateType(rule: OpcUaSimulationRule) {
  if (states.value[rule.node_id]?.error) return "danger";
  if (
    !props.running ||
    !rule.enabled ||
    !simulationRunning.value ||
    !states.value[rule.node_id]
  )
    return "info";
  return states.value[rule.node_id].paused ? "warning" : "success";
}
async function readData() {
  const epoch = generation,
    channel = props.channelId;
  reading.value = true;
  try {
    const ids = pagedDataRules.value.map((rule) => rule.node_id);
    const [capabilities, result] = await Promise.all([
      getOpcUaCapabilities(channel),
      readOpcUaServerValues(channel, ids),
    ]);
    if (epoch !== generation || disposed || !props.running || !props.active)
      return;
    const capability = capabilities.capabilities.find(
      (item) => item.name === "simulation",
    );
    simulationRunning.value = capability?.running ?? false;
    const runtime = (capability?.details?.rules || []) as RuleState[];
    states.value = Object.fromEntries(
      runtime.map((state) => [state.node_id, state]),
    );
    values.value = Object.fromEntries(
      result.values.map((value) => [value.node_id, value]),
    );
    valueErrors.value = Object.fromEntries(
      result.errors.map((error) => [error.node_id, error.message]),
    );
    sampledAt.value = new Date().toLocaleTimeString();
    dataError.value = "";
  } catch (error) {
    if (epoch === generation && !disposed && props.running && props.active) {
      clearData();
      dataError.value = error instanceof Error ? error.message : String(error);
    }
  } finally {
    reading.value = false;
  }
}
async function refreshData() {
  if (
    !props.running ||
    !props.active ||
    !loaded.value ||
    !savedRules.value.length ||
    disposed
  )
    return;
  // A page change or control action waits for the current request, then reads
  // its own page/state. Periodic reads never overlap.
  while (pendingRead) await pendingRead;
  if (!props.running || !props.active || disposed) return;
  const request = readData();
  pendingRead = request;
  await request;
  if (pendingRead === request) pendingRead = null;
}
async function setPaused(paused: boolean) {
  if (!canControl.value) return;
  toggling.value = true;
  const epoch = generation;
  try {
    await pauseOpcUaSimulation(props.channelId, paused);
    if (epoch !== generation || disposed) return;
    await refreshData();
    ElMessage.success(
      t(paused ? "opcua.simulationPaused" : "opcua.simulationResumed"),
    );
  } catch (error) {
    if (epoch === generation && !disposed) showError(error);
  } finally {
    toggling.value = false;
  }
}
function stopPolling() {
  ++pollingGeneration;
  if (timer) clearTimeout(timer);
  timer = undefined;
}
function shouldPoll() {
  return (
    props.active &&
    props.running &&
    loaded.value &&
    tab.value === "data" &&
    savedRules.value.length > 0
  );
}
function restartPolling() {
  stopPolling();
  if (!shouldPoll()) return;
  const epoch = generation,
    pollingEpoch = pollingGeneration;
  const tick = async () => {
    await refreshData();
    if (
      epoch === generation &&
      pollingEpoch === pollingGeneration &&
      !disposed &&
      shouldPoll() &&
      autoRefresh.value
    )
      timer = setTimeout(tick, pollInterval.value);
  };
  void tick();
}
watch(nodeSearch, () => {
  nodePage.value = 1;
});
watch(ruleSearch, () => {
  rulePage.value = 1;
});
watch(
  () => filteredNodes.value.length,
  (count) => {
    nodePage.value = Math.min(
      nodePage.value,
      Math.max(1, Math.ceil(count / 50)),
    );
  },
);
watch(
  () => filteredRules.value.length,
  (count) => {
    rulePage.value = Math.min(
      rulePage.value,
      Math.max(1, Math.ceil(count / 10)),
    );
  },
);
watch(
  () => savedRules.value.length,
  (count) => {
    dataPage.value = Math.min(
      dataPage.value,
      Math.max(1, Math.ceil(count / 20)),
    );
  },
);
watch(
  () => props.channelId,
  () => {
    nodes.value = [];
    rules.value = [];
    savedRules.value = [];
    void load(true);
  },
  { immediate: true },
);
watch(() => props.selectedNodeId, selectRequestedRule);
watch(
  () => props.revision,
  () => {
    void load(false, dirty.value);
  },
);
watch(
  () => props.running,
  () => {
    ++generation;
    editorOpen.value = false;
    clearData();
    // Device state changes do not replace an unsaved selection.
    if (loading.value || !loaded.value) void load();
    else restartPolling();
  },
);
watch(
  [() => props.active, tab, autoRefresh, pollInterval, dataPage],
  restartPolling,
);
onBeforeUnmount(() => {
  disposed = true;
  ++generation;
  stopPolling();
});
</script>

<style scoped>
.simulation-tabs {
  margin-top: 16px;
}
.simulation-selection {
  display: grid;
  grid-template-columns: minmax(260px, 0.85fr) minmax(0, 2fr);
  gap: 16px;
}
.variable-panel,
.rule-panel {
  margin-bottom: 0;
  padding: 16px;
}
.variable-select-all {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
}
.variable-list {
  height: 420px;
  overflow: auto;
}
.variable-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 8px;
  border-bottom: 1px solid var(--ua-line);
  cursor: pointer;
  border-radius: 4px;
}
.variable-row.is-selected {
  background: var(--item-active-bg);
}
.variable-row:hover {
  background: var(--item-active-bg);
}
.variable-label {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.variable-label strong,
.variable-label span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.variable-label strong {
  font-size: 13px;
  font-weight: 500;
}
.variable-label span {
  color: var(--ua-muted);
  font-size: 11px;
}
.rule-search {
  margin-bottom: 14px;
}
.range-inputs {
  display: flex;
  align-items: center;
  gap: 6px;
}
.range-inputs .el-input-number {
  width: 86px;
  flex: 1;
  min-width: 0;
}
.el-pagination {
  justify-content: flex-end;
  margin-top: 12px;
  overflow-x: auto;
}
.refresh-interval {
  width: 90px;
}
.data-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.el-alert {
  margin-bottom: 12px;
}
.simulation-editor-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}
.simulation-editor-form .el-input-number,
.simulation-editor-form .el-select {
  width: 100%;
}
.editor-wide {
  grid-column: 1 / -1;
}
.editor-variable {
  overflow-wrap: anywhere;
  line-height: 1.6;
}
.editor-variable .ua-code {
  font-family: monospace;
  color: var(--el-text-color-secondary);
}
@container (max-width: 1000px) {
  .simulation-selection {
    grid-template-columns: 1fr;
  }
  .variable-list {
    height: 250px;
  }
}
@media (max-width: 680px) {
  .simulation-editor-form {
    grid-template-columns: 1fr;
  }
}
</style>
