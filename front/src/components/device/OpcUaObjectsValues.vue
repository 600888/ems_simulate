<template>
  <el-alert
    v-if="!running"
    :title="t('opcua.liveValuesStopped')"
    type="info"
    :closable="false"
    class="state-note"
  />
  <el-alert
    v-if="valueError"
    :title="t('opcua.valuesUnavailable')"
    :description="valueError"
    type="warning"
    :closable="false"
    class="state-note"
  />
  <div class="objects-workspace">
    <aside class="ua-section object-tree">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.objectTree") }}</h3>
        <el-tag size="small" effect="plain">Objects</el-tag>
      </div>
      <el-input
        v-model="treeSearch"
        :placeholder="t('opcua.loadedNodeSearch')"
        clearable
      />
      <el-tree
        ref="tree"
        :key="treeEpoch"
        node-key="node_id"
        lazy
        :load="loadTree"
        :props="treeProps"
        :default-expanded-keys="['i=85']"
        :current-node-key="selected?.node_id"
        highlight-current
        :filter-node-method="filterTree"
        @node-click="selectTreeNode"
      >
        <template #default="{ data }"
          ><span class="tree-label"
            ><el-icon
              ><Folder v-if="data.node_class === 'Object'" /><Document
                v-else /></el-icon
            ><span :title="data.node_id">{{ data.browse_name }}</span></span
          ></template
        >
      </el-tree>
    </aside>
    <section class="ua-section object-content">
      <div class="ua-section-heading selected-heading">
        <h3 :title="selected?.browse_name">
          {{ selected?.browse_name || t("opcua.chooseObjectNode") }}
        </h3>
        <el-tag v-if="selected" effect="plain">{{
          selected.node_class
        }}</el-tag>
      </div>
      <p v-if="selected" class="ua-code selected-id">
        {{ selected.node_id }}
      </p>
      <el-tabs v-model="workspaceTab" class="workspace-tabs">
        <el-tab-pane :label="t('opcua.variables')" name="variables">
          <div class="tab-panel variables-panel">
            <div class="ua-toolbar">
              <el-input
                v-model="search"
                :placeholder="t('opcua.nodeSearch')"
                clearable
                @input="page = 1"
              /><el-button
                :disabled="!running"
                :loading="reading"
                @click="refreshValues"
                >{{ t("opcua.refresh") }}</el-button
              >
              <span class="variables-summary">
                {{ t("opcua.variables") }} {{ filteredVariables.length }} ·
                {{ running ? t("opcua.pollInterval") : t("opcua.notRunning") }}
              </span>
            </div>
            <div class="variable-table">
              <el-table
                :data="visibleVariables"
                height="100%"
                row-key="node_id"
                highlight-current-row
                :current-row-key="selected?.node_id"
                class="ua-selectable"
                @row-click="selectVariable"
              >
                <el-table-column
                  prop="browse_name"
                  label="BrowseName"
                  min-width="180"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="data_type"
                  :label="t('opcua.dataType')"
                  width="100"
                />
                <el-table-column
                  :label="t('opcua.currentValue')"
                  min-width="125"
                  show-overflow-tooltip
                  ><template #default="{ row }"
                    ><strong
                      class="ua-code"
                      :title="String(values[row.node_id]?.value ?? '')"
                      >{{ formatValue(values[row.node_id]?.value) }}</strong
                    ></template
                  ></el-table-column
                >
                <el-table-column :label="t('opcua.quality')" min-width="130"
                  ><template #default="{ row }"
                    ><span
                      :class="
                        values[row.node_id]?.status_code.startsWith('Good')
                          ? 'ua-good'
                          : 'ua-warning'
                      "
                      >{{
                        nodeErrors[row.node_id] ||
                        values[row.node_id]?.status_code ||
                        "—"
                      }}</span
                    ></template
                  ></el-table-column
                >
                <el-table-column
                  prop="node_id"
                  label="NodeId"
                  min-width="220"
                  show-overflow-tooltip
                />
              </el-table>
            </div>
            <el-pagination
              v-if="filteredVariables.length > 50"
              v-model:current-page="page"
              layout="total, prev, pager, next"
              :page-size="50"
              :total="filteredVariables.length"
            />
          </div>
        </el-tab-pane>
        <el-tab-pane :label="t('opcua.nodeProperties')" name="properties">
          <div class="tab-panel" v-loading="inspecting">
            <dl v-if="selected" class="properties-grid">
              <template v-for="attribute in attributes" :key="attribute.label"
                ><div>
                  <dt>{{ attribute.label }}</dt>
                  <dd>{{ attribute.value ?? "—" }}</dd>
                </div></template
              >
            </dl>
            <el-empty
              v-else
              :image-size="65"
              :description="t('opcua.chooseObjectNode')"
            />
          </div>
        </el-tab-pane>
        <el-tab-pane :label="t('opcua.nodeReferences')" name="references">
          <div class="tab-panel" v-loading="inspecting">
            <el-table v-if="running && details" :data="details.references">
              <el-table-column
                prop="browse_name"
                label="BrowseName"
                min-width="150"
                show-overflow-tooltip
              />
              <el-table-column
                prop="reference_type"
                :label="t('opcua.referenceType')"
                width="130"
              />
              <el-table-column
                :label="t('opcua.referenceDirection')"
                width="100"
                ><template #default="{ row }">{{
                  t(
                    row.forward
                      ? "opcua.forwardReference"
                      : "opcua.inverseReference",
                  )
                }}</template></el-table-column
              >
              <el-table-column
                prop="node_id"
                :label="t('opcua.targetNode')"
                min-width="200"
                show-overflow-tooltip
              />
            </el-table>
            <el-empty
              v-else
              :image-size="65"
              :description="
                t(
                  selected
                    ? 'opcua.stoppedReferences'
                    : 'opcua.chooseObjectNode',
                )
              "
            />
            <p v-if="details?.references_truncated" class="ua-note">
              {{ t("opcua.referenceLimit") }}
            </p>
          </div>
        </el-tab-pane>
        <el-tab-pane
          :label="t('opcua.value')"
          name="value"
          :disabled="!selectedVariable"
        >
          <div v-if="selectedVariable" class="tab-panel" v-loading="inspecting">
            <dl class="value-summary">
              <div>
                <dt>{{ t("opcua.currentValue") }}</dt>
                <dd
                  class="current-value"
                  :title="String(currentValue?.value ?? '')"
                >
                  {{ formatValue(currentValue?.value) }}
                </dd>
              </div>
              <div>
                <dt>{{ t("opcua.quality") }}</dt>
                <dd>
                  {{
                    nodeErrors[selectedVariable.node_id] ||
                    currentValue?.status_code ||
                    "—"
                  }}
                </dd>
              </div>
              <div>
                <dt>{{ t("opcua.sampledAt") }}</dt>
                <dd>{{ sampledAt || "—" }}</dd>
              </div>
            </dl>
            <div class="ua-toolbar">
              <el-input
                v-model="writeText"
                :placeholder="t('opcua.serverValueWrite')"
                :disabled="!canWrite"
              /><el-button
                type="primary"
                :disabled="!canWrite"
                :loading="writing"
                @click="writeValue"
                >{{ t("opcua.write") }}</el-button
              >
            </div>
            <dl class="value-timestamps ua-note">
              <div>
                <dt>{{ t("opcua.sourceTimestamp") }}</dt>
                <dd>{{ currentValue?.source_timestamp || "—" }}</dd>
              </div>
              <div>
                <dt>{{ t("opcua.serverTimestamp") }}</dt>
                <dd>{{ currentValue?.server_timestamp || "—" }}</dd>
              </div>
            </dl>
          </div>
        </el-tab-pane>
        <el-tab-pane
          :label="t('opcua.valueWaveform')"
          name="waveform"
          :disabled="!selectedVariable"
        >
          <div v-if="selectedVariable" class="tab-panel waveform">
            <div class="ua-section-heading">
              <h3>{{ t("opcua.valueWaveform") }}</h3>
              <strong class="ua-code ua-good">{{
                formatValue(currentValue?.value)
              }}</strong>
            </div>
            <OpcUaTrendPlot
              :title="t('opcua.valueWaveform')"
              :points="samples"
            />
            <p class="ua-note">
              {{ t("opcua.selectedVariable") }} ·
              {{ selectedVariable.browse_name }}
            </p>
          </div>
        </el-tab-pane>
        <el-tab-pane
          :label="t('opcua.simulation')"
          name="simulation"
          :disabled="!selectedVariable"
        >
          <div v-if="selectedVariable" class="tab-panel simulation-parameters">
            <div class="ua-section-heading">
              <h3>{{ t("opcua.rule") }}</h3>
              <el-button
                link
                type="primary"
                @click="emit('configure', selectedVariable.node_id)"
                >{{ t("opcua.edit") }}</el-button
              >
            </div>
            <dl v-if="rule" class="properties-grid rule-properties">
              <div>
                <dt>{{ t("opcua.rule") }}</dt>
                <dd>{{ t("opcua." + rule.kind) }}</dd>
              </div>
              <div>
                <dt>{{ t("opcua.enabled") }}</dt>
                <dd>
                  {{ t(rule.enabled ? "opcua.enabled" : "opcua.disabled") }}
                </dd>
              </div>
              <template v-if="rule.kind !== 'fixed'"
                ><div>
                  <dt>{{ t("opcua.minimum") }}</dt>
                  <dd>{{ rule.minimum }}</dd>
                </div>
                <div>
                  <dt>{{ t("opcua.maximum") }}</dt>
                  <dd>{{ rule.maximum }}</dd>
                </div></template
              ><template v-if="rule.kind === 'sine'"
                ><div>
                  <dt>{{ t("opcua.periodSeconds") }}</dt>
                  <dd>{{ rule.period_s }}</dd>
                </div>
                <div>
                  <dt>{{ t("opcua.offsetSeconds") }}</dt>
                  <dd>{{ rule.offset_s }}</dd>
                </div></template
              >
              <div v-if="rule.kind === 'fixed'">
                <dt>{{ t("opcua.value") }}</dt>
                <dd>{{ formatValue(rule.value) }}</dd>
              </div>
              <div v-if="rule.kind === 'step'">
                <dt>{{ t("opcua.stepSize") }}</dt>
                <dd>{{ rule.step }}</dd>
              </div>
              <div>
                <dt>{{ t("opcua.intervalMs") }}</dt>
                <dd>{{ rule.interval_ms }}</dd>
              </div>
              <div>
                <dt>{{ t("opcua.writePolicy") }}</dt>
                <dd>{{ t("opcua.policy" + rule.write_policy) }}</dd>
              </div>
            </dl>
            <p v-else class="ua-note">{{ t("opcua.noSimulationRule") }}</p>
          </div>
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElTree } from "element-plus";
import type { TreeNodeData } from "element-plus/es/components/tree/src/tree.type";
import { Document, Folder } from "@element-plus/icons-vue";
import { showError } from "@/api/http";
import {
  browseOpcUaServer,
  getOpcUaFeatures,
  inspectOpcUaServerNode,
  readOpcUaServerValues,
  writeOpcUaServerValue,
} from "@/api/opcuaApi";
import type {
  OpcUaNodeDetails,
  OpcUaObjectNode,
  OpcUaValueSnapshot,
  OpcUaVariable,
} from "@/api/opcuaApi";
import {
  OPCUA_SCALAR_TYPES,
  parseOpcUaScalar,
  type OpcUaScalarType,
} from "@/utils/opcuaValue";
import OpcUaTrendPlot from "./OpcUaTrendPlot.vue";

const props = defineProps<{
  channelId: number;
  running: boolean;
  active: boolean;
  revision: number;
  variables: OpcUaVariable[];
}>();
const emit = defineEmits<{ configure: [nodeId: string] }>();
const { t } = useI18n();
type TreeNode = OpcUaObjectNode & { parentId?: string; offset?: number };
const tree = ref<InstanceType<typeof ElTree>>();
const treeEpoch = ref(0),
  treeSearch = ref(""),
  search = ref(""),
  page = ref(1);
const treeProps = {
  label: "browse_name",
  isLeaf: (node: TreeNodeData) => !["Object", "More"].includes(node.node_class),
};
const filteredVariables = computed(() =>
  props.variables.filter((n) =>
    `${n.node_id} ${n.browse_name}`
      .toLowerCase()
      .includes(search.value.toLowerCase()),
  ),
);
const visibleVariables = computed(() =>
  filteredVariables.value.slice((page.value - 1) * 50, page.value * 50),
);
const selected = ref<OpcUaObjectNode | null>(null),
  details = ref<OpcUaNodeDetails | null>(null);
const selectedVariable = computed(() =>
  selected.value?.node_class === "Variable" ? selected.value : null,
);
const workspaceTab = ref("variables"),
  inspecting = ref(false),
  reading = ref(false),
  writing = ref(false),
  writeText = ref("");
const values = ref<Record<string, OpcUaValueSnapshot>>({}),
  nodeErrors = ref<Record<string, string>>({}),
  valueError = ref(""),
  sampledAt = ref("");
const samples = ref<
  { timestamp: string; value: unknown; status: string; breakBefore?: boolean }[]
>([]);
const rules = ref<Record<string, any>[]>([]);
const rule = computed(() =>
  rules.value.find((r) => r.node_id === selected.value?.node_id),
);
const definition = computed(() =>
  props.variables.find((n) => n.node_id === selected.value?.node_id),
);
const currentValue = computed(() =>
  selected.value ? values.value[selected.value.node_id] : undefined,
);
const canWrite = computed(
  () =>
    props.running &&
    props.active &&
    details.value?.writable &&
    details.value.value_rank === -1 &&
    OPCUA_SCALAR_TYPES.includes(details.value.data_type as OpcUaScalarType),
);
const attributes = computed(() => {
  const node = details.value,
    local = definition.value;
  return [
    { label: "BrowseName", value: selected.value?.browse_name },
    { label: t("opcua.nodeClass"), value: selected.value?.node_class },
    {
      label: t("opcua.namespaceUri"),
      value: node?.namespace_uri ?? local?.namespace_uri,
    },
    {
      label: t("opcua.typeDefinition"),
      value:
        node?.type_definition ?? (local ? "BaseDataVariableType" : undefined),
    },
    { label: t("opcua.dataType"), value: node?.data_type ?? local?.data_type },
    {
      label: t("opcua.valueRank"),
      value: node?.value_rank ?? (local ? -1 : undefined),
    },
    {
      label: t("opcua.arrayDimensions"),
      value:
        node?.value_rank === -1 || (!node && local)
          ? t("opcua.scalarValue")
          : node?.array_dimensions?.join(" × ") || "—",
    },
    {
      label: t("opcua.access"),
      value:
        selected.value?.node_class === "Variable"
          ? t(
              (node?.writable ?? local?.writable)
                ? "opcua.readWrite"
                : "opcua.readOnly",
            )
          : "—",
    },
    {
      label: t("opcua.initialValue"),
      value: local ? formatValue(local.initial_value) : "—",
    },
    { label: t("opcua.nodeDescription"), value: node?.description || "—" },
  ];
});
let generation = 0,
  selectionGeneration = 0,
  timer: ReturnType<typeof setTimeout> | undefined,
  disposed = false,
  inFlight = false,
  interrupted = false;
function formatValue(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (typeof value === "number" && Number.isFinite(value))
    return Number(value.toPrecision(8)).toString();
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function filterTree(query: string, node: TreeNodeData) {
  return `${node.browse_name} ${node.node_id}`
    .toLowerCase()
    .includes(query.toLowerCase());
}
watch(treeSearch, (query) => tree.value?.filter(query));
async function loadTree(
  node: { level: number; data: TreeNodeData },
  resolve: (children: TreeNode[]) => void,
) {
  if (!node.level) {
    resolve([
      { node_id: "i=85", browse_name: "Objects", node_class: "Object" },
    ]);
    return;
  }
  if (!props.active) {
    resolve([]);
    return;
  }
  if (!props.running) {
    resolve(
      node.data.node_id === "i=85"
        ? props.variables.map((n) => ({ ...n, node_class: "Variable" }))
        : [],
    );
    return;
  }
  const epoch = generation,
    channelId = props.channelId;
  try {
    const id = node.data.parentId || node.data.node_id;
    const result = await browseOpcUaServer(
      channelId,
      id,
      node.data.offset || 0,
    );
    if (epoch !== generation || disposed) {
      resolve([]);
      return;
    }
    const children: TreeNode[] = result.nodes;
    if (result.has_more)
      children.push({
        node_id: `more:${id}:${result.offset + result.nodes.length}`,
        browse_name: t("opcua.nextPage"),
        node_class: "More",
        parentId: id,
        offset: result.offset + result.nodes.length,
      });
    resolve(children);
  } catch (error) {
    resolve([]);
    if (epoch === generation && !disposed) showError(error);
  }
}
function selectTreeNode(node: TreeNode) {
  if (node.node_class === "More") return;
  if (workspaceTab.value === "variables") workspaceTab.value = "properties";
  void selectNode(node);
}
function selectVariable(node: OpcUaVariable) {
  workspaceTab.value = "properties";
  void selectNode({ ...node, node_class: "Variable" });
  tree.value?.setCurrentKey(node.node_id);
}
async function selectNode(node: OpcUaObjectNode) {
  const selection = ++selectionGeneration,
    epoch = generation;
  const changed = selected.value?.node_id !== node.node_id;
  selected.value = node;
  details.value = null;
  writeText.value = "";
  if (changed) {
    samples.value = [];
    interrupted = false;
  }
  if (!props.running || !props.active) {
    inspecting.value = false;
    return;
  }
  inspecting.value = true;
  try {
    const result = await inspectOpcUaServerNode(props.channelId, node.node_id);
    if (selection === selectionGeneration && epoch === generation && !disposed)
      details.value = result;
  } catch (error) {
    if (selection === selectionGeneration && epoch === generation && !disposed)
      showError(error);
  } finally {
    if (selection === selectionGeneration && epoch === generation)
      inspecting.value = false;
  }
  if (selection === selectionGeneration && epoch === generation)
    void refreshValues();
}
async function refreshValues() {
  if (!props.running || !props.active || disposed || inFlight) return;
  const ids = visibleVariables.value.map((n) => n.node_id);
  if (
    selected.value?.node_class === "Variable" &&
    !ids.includes(selected.value.node_id)
  ) {
    ids.push(selected.value.node_id);
  }
  if (!ids.length) return;
  const epoch = generation,
    selection = selectionGeneration;
  inFlight = true;
  reading.value = true;
  try {
    const batches = await Promise.all([
      readOpcUaServerValues(props.channelId, ids.slice(0, 50)),
      ...(ids.length > 50
        ? [readOpcUaServerValues(props.channelId, ids.slice(50))]
        : []),
    ]);
    const result = {
      values: batches.flatMap((batch) => batch.values),
      errors: batches.flatMap((batch) => batch.errors || []),
    };
    if (epoch !== generation || disposed) return;
    values.value = Object.fromEntries(result.values.map((v) => [v.node_id, v]));
    nodeErrors.value = Object.fromEntries(
      (result.errors || []).map((e) => [e.node_id, e.message]),
    );
    valueError.value = "";
    const now = new Date().toISOString();
    sampledAt.value = new Date(now).toLocaleTimeString();
    const value = currentValue.value;
    if (value && selection === selectionGeneration) {
      samples.value = [
        ...samples.value,
        {
          timestamp: now,
          value: value.value,
          status: value.status_code,
          breakBefore: interrupted,
        },
      ].slice(-120);
      interrupted = false;
    } else if (selected.value?.node_class === "Variable") interrupted = true;
  } catch (error) {
    if (epoch === generation && !disposed) {
      values.value = {};
      nodeErrors.value = {};
      sampledAt.value = "";
      valueError.value = error instanceof Error ? error.message : String(error);
      interrupted = true;
    }
  } finally {
    inFlight = false;
    reading.value = false;
  }
}
async function poll() {
  const epoch = generation;
  await refreshValues();
  if (epoch === generation && !disposed && props.running && props.active)
    timer = setTimeout(poll, 1000);
}
async function writeValue() {
  if (!canWrite.value || !selected.value || !details.value) return;
  const epoch = generation,
    selection = selectionGeneration,
    nodeId = selected.value.node_id;
  writing.value = true;
  try {
    const value = parseOpcUaScalar(
      writeText.value,
      details.value.data_type as OpcUaScalarType,
    );
    await writeOpcUaServerValue(props.channelId, nodeId, value);
    if (
      epoch === generation &&
      selection === selectionGeneration &&
      !disposed
    ) {
      ElMessage.success(t("opcua.writeCompleted"));
      await refreshValues();
    }
  } catch (error) {
    if (epoch === generation && !disposed) showError(error);
  } finally {
    writing.value = false;
  }
}
watch(selectedVariable, (node) => {
  if (!node && ["value", "waveform", "simulation"].includes(workspaceTab.value))
    workspaceTab.value = "properties";
});
watch(
  () => [props.channelId, props.running, props.active, props.revision],
  async () => {
    const epoch = ++generation;
    ++selectionGeneration;
    if (timer) clearTimeout(timer);
    timer = undefined;
    treeEpoch.value++;
    details.value = null;
    inspecting.value = false;
    values.value = {};
    nodeErrors.value = {};
    valueError.value = "";
    sampledAt.value = "";
    samples.value = [];
    if (!props.active) return;
    try {
      const features = await getOpcUaFeatures(props.channelId);
      if (epoch !== generation || disposed) return;
      rules.value = features.simulation?.rules || [];
    } catch (error) {
      if (epoch === generation && !disposed) showError(error);
    }
    if (epoch !== generation || disposed) return;
    const previous = props.variables.find(
      (n) => n.node_id === selected.value?.node_id,
    );
    const first = previous || props.variables[0];
    if (first) void selectNode({ ...first, node_class: "Variable" });
    else selected.value = null;
    if (props.running) void poll();
  },
  { immediate: true },
);
watch(
  () => props.variables,
  (nodes) => {
    if (!props.running) treeEpoch.value++;
    if (!selected.value && nodes.length)
      void selectNode({ ...nodes[0], node_class: "Variable" });
  },
);
onBeforeUnmount(() => {
  disposed = true;
  generation++;
  selectionGeneration++;
  if (timer) clearTimeout(timer);
});
</script>

<style scoped>
.state-note {
  margin-bottom: 16px;
}
.objects-workspace {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  height: clamp(380px, calc(100dvh - 320px), 760px);
  gap: 16px;
  min-height: 0;
}
.objects-workspace > .ua-section {
  min-height: 0;
  margin-bottom: 0;
}
.object-tree {
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  overflow: hidden;
}
.object-tree .el-input {
  margin-bottom: 16px;
  flex-shrink: 0;
}
.object-tree :deep(.el-tree) {
  flex: 1;
  min-height: 0;
  background: transparent;
  color: var(--ua-text);
  overflow: auto;
}
.object-tree :deep(.el-tree-node__content) {
  height: 34px;
}
.object-tree :deep(.el-tree-node__content:hover),
.object-tree :deep(.el-tree-node:focus > .el-tree-node__content),
.object-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: color-mix(in srgb, var(--ua-primary) 12%, var(--ua-surface));
  color: var(--ua-text);
}
.tree-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--ua-text);
}
.tree-label .el-icon {
  color: var(--ua-primary);
}
.object-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.selected-heading {
  flex-shrink: 0;
  flex-wrap: nowrap;
}
.selected-heading h3 {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.selected-heading .el-tag {
  flex-shrink: 0;
}
.workspace-tabs {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
.workspace-tabs :deep(.el-tabs__header) {
  flex-shrink: 0;
  margin-bottom: 0;
}
.workspace-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.workspace-tabs :deep(.el-tab-pane) {
  height: 100%;
}
.tab-panel {
  box-sizing: border-box;
  height: 100%;
  min-height: 0;
  padding-top: 16px;
  overflow: auto;
}
.variables-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.variables-panel > .ua-toolbar,
.variables-panel > .el-pagination {
  flex-shrink: 0;
}
.variable-table {
  flex: 1;
  min-height: 0;
}
.variables-summary {
  margin-left: auto;
  color: var(--ua-muted);
  font-size: 12px;
}
.ua-toolbar {
  margin-bottom: 14px;
}
.ua-toolbar .el-input {
  width: min(320px, 100%);
}
.properties-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px 24px;
  margin: 12px 0 8px;
}
.properties-grid dt {
  color: var(--ua-muted);
  font-size: 12px;
  margin-bottom: 7px;
}
.properties-grid dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 13px;
}
.selected-id {
  font-size: 12px;
  color: var(--ua-muted);
  margin: -4px 0 12px;
  overflow-wrap: anywhere;
  max-height: 60px;
  overflow: auto;
  flex-shrink: 0;
}
.value-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  gap: 14px;
  margin-bottom: 16px;
}
.value-summary > div {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--ua-line);
  border-radius: 6px;
  background: var(--ua-chart);
}
.value-summary dt,
.value-timestamps dt {
  color: var(--ua-muted);
  font-size: 12px;
  line-height: 20px;
  margin-bottom: 8px;
}
.value-summary dd,
.value-timestamps dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.value-summary dd {
  max-height: 160px;
  overflow: auto;
  line-height: 24px;
}
.value-summary .current-value {
  font-size: 24px;
  line-height: 32px;
  font-weight: 600;
}
.value-timestamps.ua-note {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 12px 18px;
}
.value-timestamps > div,
.properties-grid > div {
  min-width: 0;
}
.rule-properties {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.el-pagination {
  margin-top: 12px;
  justify-content: safe flex-end;
}
@container (max-width: 1050px) {
  .objects-workspace {
    grid-template-columns: 200px minmax(0, 1fr);
  }
  .properties-grid,
  .rule-properties {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 760px) {
  .objects-workspace {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
  }
  .object-tree {
    height: 240px;
    box-sizing: border-box;
  }
  .object-content {
    height: 520px;
    box-sizing: border-box;
  }
  .properties-grid,
  .rule-properties {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 480px) {
  .properties-grid,
  .rule-properties {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
