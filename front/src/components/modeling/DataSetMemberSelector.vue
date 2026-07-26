<template>
  <section v-if="modelValue" class="dataset-member-page">
    <header class="selector-page-header">
      <div class="selector-title">
        <div>
          <small>{{ discovery?.dataset.path || dataSet.path }}</small>
          <div>
            <strong>批量选择 DataSet 成员</strong>
            <el-tag size="small" effect="plain">
              已有 {{ discovery?.summary.existing_count || 0 }} 项
            </el-tag>
            <el-tag
              v-if="discovery?.summary.invalid_count"
              size="small"
              type="danger"
              effect="plain"
            >
              {{ discovery.summary.invalid_count }} 项失效
            </el-tag>
          </div>
        </div>
        <span>支持 DO 整组与 DA 精确两种标准 FCDA 引用</span>
      </div>
      <div class="selector-header-actions">
        <el-button plain>选择规则</el-button>
        <el-button @click="emit('update:modelValue', false)"
          >返回 DataSet</el-button
        >
      </div>
    </header>

    <div v-loading="loading" class="member-selector">
      <el-alert
        v-if="invalidMembers.length"
        type="error"
        :closable="false"
        show-icon
        :title="`发现 ${invalidMembers.length} 个失效引用，请重新匹配或移除后再发布 SCL`"
      />

      <div class="selector-columns">
        <section class="candidate-panel selector-card">
          <header>
            <div>
              <strong>从 DataModel 选择</strong>
              <small>按层级勾选，系统自动填写 FCDA 引用和 FC</small>
            </div>
            <el-segmented
              v-model="selectionLevel"
              :options="selectionLevelOptions"
              size="small"
              aria-label="DataSet 成员选择粒度"
            />
          </header>

          <div class="candidate-filters">
            <el-input
              v-model="keyword"
              clearable
              placeholder="搜索 LD / LN / DO / DA 或完整引用"
            >
              <template #prefix
                ><el-icon><Search /></el-icon
              ></template>
            </el-input>
            <el-select v-model="fcFilter" aria-label="功能约束筛选">
              <el-option label="FC：全部" value="" />
              <el-option
                v-for="fc in fcOptions"
                :key="fc"
                :label="`FC：${fc}`"
                :value="fc"
              />
            </el-select>
            <el-checkbox v-model="onlyAvailable">仅可用</el-checkbox>
          </div>

          <div class="candidate-summary">
            <span>{{ filteredCandidateCount }} 个候选属性</span>
            <span>{{ newCandidateIds.length }} 个待生成</span>
          </div>

          <div v-loading="treeBuilding" class="candidate-tree-scroll">
            <el-tree-v2
              ref="treeRef"
              :data="candidateTree"
              :props="candidateTreeProps"
              :height="404"
              :item-size="36"
              show-checkbox
              :default-checked-keys="selectedOrder"
              :default-expanded-keys="defaultExpandedKeys"
              :expand-on-click-node="false"
              @check="handleTreeCheck"
            >
              <template #default="{ data }">
                <div
                  class="candidate-node"
                  :class="[
                    `level-${data.type}`,
                    { existing: data.candidate?.existing },
                  ]"
                >
                  <span class="candidate-kind-mark">{{
                    data.candidate?.selection_level || data.type.toUpperCase()
                  }}</span>
                  <span class="candidate-label">{{ data.label }}</span>
                  <template v-if="data.candidate">
                    <small>{{ data.candidate.b_type || "—" }}</small>
                    <el-tag
                      size="small"
                      effect="plain"
                      :type="fcTagType(data.candidate.fc)"
                    >
                      {{ data.candidate.fc || "—" }}
                    </el-tag>
                    <em v-if="data.candidate.existing">已存在</em>
                  </template>
                </div>
              </template>
            </el-tree-v2>
          </div>
        </section>

        <section class="selected-panel selector-card">
          <header>
            <div>
              <strong>已选成员</strong>
              <small>保持顺序写入 FCDA，可在生成前调整</small>
            </div>
            <el-button
              text
              type="danger"
              :disabled="!newCandidateIds.length"
              @click="clearNewSelections"
              >清空新增</el-button
            >
          </header>

          <div class="selection-options">
            <template v-if="selectionLevel === 'DA'">
              <el-switch v-model="autoCompanions" />
              <span>勾选值时自动建议同一 DO 的 q / t</span>
            </template>
            <span v-else>DO 整组将生成一个无 daName 的 FCDA</span>
            <small>重复引用自动跳过</small>
          </div>

          <el-scrollbar class="selected-list-scroll">
            <div ref="selectedListRef" class="selected-list">
              <div
                v-for="candidate in selectedCandidates"
                :key="candidate.id"
                class="selected-member is-sortable"
                :data-candidate-id="candidate.id"
              >
                <button
                  class="drag-handle"
                  type="button"
                  title="按住拖动调整顺序"
                  aria-label="拖动调整 FCDA 顺序"
                >
                  <span aria-hidden="true"></span>
                </button>
                <div>
                  <code>{{ candidate.reference }}</code>
                  <small>{{
                    candidate.description ||
                    (candidate.selection_level === "DO"
                      ? `${candidate.data_object} · DO 整组`
                      : `${candidate.data_object} · ${candidate.data_attribute}`)
                  }}</small>
                </div>
                <el-tag
                  size="small"
                  effect="plain"
                  :type="fcTagType(candidate.fc)"
                  >{{ candidate.fc }}</el-tag
                >
                <el-tag
                  v-if="candidate.existing"
                  size="small"
                  type="info"
                  effect="plain"
                  >已存在</el-tag
                >
                <div v-else class="member-actions">
                  <el-button
                    text
                    circle
                    type="danger"
                    title="移除"
                    @click="removeCandidate(candidate.id)"
                    >×</el-button
                  >
                </div>
              </div>
            </div>

            <el-empty
              v-if="!selectedCandidates.length && !invalidMembers.length"
              :image-size="64"
              description="从左侧 DataModel 勾选成员"
            />

            <div
              v-for="member in invalidMembers"
              :key="member.node_id"
              class="invalid-member"
            >
              <div>
                <el-tag size="small" type="danger">失效</el-tag>
                <code>{{ member.reference }}</code>
              </div>
              <p>{{ member.reason }}</p>
              <div class="repair-row">
                <el-select
                  v-model="repairSelections[member.node_id]"
                  filterable
                  clearable
                  placeholder="搜索并选择替代引用"
                >
                  <el-option
                    v-for="candidate in discovery?.candidates || []"
                    :key="candidate.id"
                    :label="`${candidate.reference} [${
                      candidate.selection_level === 'DO' ? 'DO整组' : 'DA精确'
                    } · ${candidate.fc}]`"
                    :value="candidate.id"
                    :disabled="candidate.existing"
                  />
                </el-select>
                <el-button
                  type="primary"
                  plain
                  :loading="repairingId === member.node_id"
                  :disabled="!repairSelections[member.node_id]"
                  @click="repairMember(member.node_id)"
                  >重新匹配</el-button
                >
                <el-button
                  type="danger"
                  plain
                  :loading="removingId === member.node_id"
                  @click="removeInvalidMember(member.node_id)"
                  >移除</el-button
                >
              </div>
            </div>
          </el-scrollbar>

          <footer class="preflight">
            <el-icon><CircleCheckFilled /></el-icon>
            <div>
              <strong>生成前预校验</strong>
              <small>候选项来自当前实例模型，自动校验 DO/DA 路径和 FC</small>
            </div>
          </footer>
        </section>
      </div>
    </div>

    <footer class="selector-page-footer">
      <div class="selector-footer">
        <span>
          将生成 <strong>{{ newCandidateIds.length }}</strong> 个 FCDA ·
          <template v-if="orderChanged">成员顺序已调整 ·</template>
          {{ discovery?.summary.invalid_count || 0 }} 个失效引用
        </span>
        <div>
          <el-button @click="emit('update:modelValue', false)">取消</el-button>
          <el-tooltip
            :content="saveButtonTooltip"
            placement="top"
            :show-after="350"
          >
            <span>
              <el-button
                type="primary"
                :loading="submitting"
                :disabled="!hasPendingChanges"
                @click="createMembers"
              >
                保存
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  reactive,
  ref,
  shallowRef,
  watch,
} from "vue";
import { CircleCheckFilled, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type TreeV2Instance } from "element-plus";
import Sortable from "sortablejs";
import { modelingApi } from "@/api/modelingApi";
import type {
  DataSetMemberCandidate,
  DataSetMemberDiscovery,
  ModelNode,
} from "@/types/modeling";

interface CandidateTreeNode {
  id: string;
  label: string;
  type: "ld" | "ln" | "do" | "candidate";
  disabled?: boolean;
  candidate?: DataSetMemberCandidate;
  children?: CandidateTreeNode[];
}

const props = defineProps<{
  modelValue: boolean;
  projectId: string;
  dataSet: ModelNode;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  changed: [dataSetId: string];
}>();

const loading = ref(false);
const submitting = ref(false);
const treeBuilding = ref(false);
const repairingId = ref("");
const removingId = ref("");
const discovery = shallowRef<DataSetMemberDiscovery>();
const keyword = ref("");
const fcFilter = ref("");
const onlyAvailable = ref(true);
const selectionLevel = ref<"DO" | "DA">("DO");
const selectionLevelOptions = [
  { label: "DO 整组", value: "DO" },
  { label: "DA 精确", value: "DA" },
];
const autoCompanions = ref(true);
const selectedIds = reactive(new Set<string>());
const selectedOrder = ref<string[]>([]);
const initialSelectedOrder = shallowRef<string[]>([]);
const repairSelections = reactive<Record<string, string>>({});
const candidateTree = shallowRef<CandidateTreeNode[]>([]);
const defaultExpandedKeys = shallowRef<string[]>([]);
const candidateById = shallowRef(new Map<string, DataSetMemberCandidate>());
const companionIdsByGroup = shallowRef(new Map<string, string[]>());
const existingCandidateIds = shallowRef(new Set<string>());
const visibleCandidateIds = shallowRef(new Set<string>());
const filteredCandidateCount = ref(0);
const fcOptions = shallowRef<string[]>([]);
const candidateTreeProps = {
  children: "children",
  label: "label",
  value: "id",
  disabled: "disabled",
};
const treeRef = ref<TreeV2Instance>();
const selectedListRef = ref<HTMLElement>();
const activeTreeWorkers = new Set<Worker>();
let selectedListSortable: Sortable | undefined;
let treeBuildRequest = 0;

const invalidMembers = computed(
  () =>
    discovery.value?.existing_members.filter((member) => !member.valid) || [],
);
const selectedCandidates = computed(() =>
  selectedOrder.value
    .map((id) => candidateById.value.get(id))
    .filter((candidate): candidate is DataSetMemberCandidate =>
      Boolean(candidate),
    ),
);
const newCandidateIds = computed(() =>
  selectedOrder.value.filter((id) => !existingCandidateIds.value.has(id)),
);
const orderChanged = computed(
  () =>
    selectedOrder.value.length !== initialSelectedOrder.value.length ||
    selectedOrder.value.some(
      (id, index) => id !== initialSelectedOrder.value[index],
    ),
);
const hasPendingChanges = computed(
  () => newCandidateIds.value.length > 0 || orderChanged.value,
);
const saveButtonTooltip = computed(() => {
  if (!hasPendingChanges.value) {
    return "当前没有需要保存的成员或顺序变更";
  }
  const changes = [];
  if (newCandidateIds.value.length) {
    changes.push(`新增 ${newCandidateIds.value.length} 个 FCDA`);
  }
  if (orderChanged.value) {
    changes.push("按照当前拖拽顺序写入 DataSet");
  }
  return `保存后将${changes.join("，并")}。`;
});

function buildCandidateTreeSync(
  candidates: DataSetMemberCandidate[],
  filters: {
    keyword: string;
    fc: string;
    onlyAvailable: boolean;
    selectionLevel: "DO" | "DA";
    selectedIds: string[];
  },
) {
  const selected = new Set(filters.selectedIds);
  const roots = new Map<string, CandidateTreeNode>();
  const logicalNodes = new Map<string, CandidateTreeNode>();
  const dataObjects = new Map<string, CandidateTreeNode>();
  const visibleIds: string[] = [];
  const groupIds: string[] = [];
  for (const candidate of candidates) {
    const matchesSearch =
      !filters.keyword ||
      candidate.reference.toLowerCase().includes(filters.keyword) ||
      candidate.description.toLowerCase().includes(filters.keyword);
    const matchesFc = !filters.fc || candidate.fc === filters.fc;
    const matchesLevel = candidate.selection_level === filters.selectionLevel;
    const matchesAvailability =
      !filters.onlyAvailable ||
      !candidate.existing ||
      selected.has(candidate.id);
    if (!matchesSearch || !matchesFc || !matchesLevel || !matchesAvailability) {
      continue;
    }

    visibleIds.push(candidate.id);
    let ld = roots.get(candidate.logical_device);
    if (!ld) {
      ld = {
        id: `ld:${candidate.logical_device}`,
        label: candidate.logical_device,
        type: "ld",
        children: [],
      };
      roots.set(candidate.logical_device, ld);
      groupIds.push(ld.id);
    }
    const lnId = `ln:${candidate.logical_device}/${candidate.logical_node}`;
    let ln = logicalNodes.get(lnId);
    if (!ln) {
      ln = {
        id: lnId,
        label: candidate.logical_node,
        type: "ln",
        children: [],
      };
      ld.children!.push(ln);
      logicalNodes.set(lnId, ln);
      groupIds.push(lnId);
    }
    if (candidate.selection_level === "DO") {
      ln.children!.push({
        id: candidate.id,
        label: candidate.data_object,
        type: "candidate",
        candidate,
        disabled: candidate.existing,
      });
      continue;
    }
    const doId = `do:${candidate.group_key}`;
    let dataObject = dataObjects.get(doId);
    if (!dataObject) {
      dataObject = {
        id: doId,
        label: candidate.data_object,
        type: "do",
        children: [],
      };
      ln.children!.push(dataObject);
      dataObjects.set(doId, dataObject);
      groupIds.push(doId);
    }
    dataObject.children!.push({
      id: candidate.id,
      label: candidate.data_attribute,
      type: "candidate",
      candidate,
      disabled: candidate.existing,
    });
  }
  return {
    tree: Array.from(roots.values()),
    visibleIds,
    groupIds,
  };
}

function buildCandidateTreeOffMainThread(
  candidates: DataSetMemberCandidate[],
  filters: {
    keyword: string;
    fc: string;
    onlyAvailable: boolean;
    selectionLevel: "DO" | "DA";
    selectedIds: string[];
  },
) {
  if (typeof Worker === "undefined") {
    return Promise.resolve(buildCandidateTreeSync(candidates, filters));
  }
  const workerSource = `
    self.onmessage = ({ data }) => {
      const { candidates, filters } = data;
      const selected = new Set(filters.selectedIds);
      const roots = new Map();
      const logicalNodes = new Map();
      const dataObjects = new Map();
      const visibleIds = [];
      const groupIds = [];
      for (const candidate of candidates) {
        const matchesSearch =
          !filters.keyword ||
          candidate.reference.toLowerCase().includes(filters.keyword) ||
          candidate.description.toLowerCase().includes(filters.keyword);
        const matchesFc = !filters.fc || candidate.fc === filters.fc;
        const matchesLevel = candidate.selection_level === filters.selectionLevel;
        const matchesAvailability =
          !filters.onlyAvailable || !candidate.existing || selected.has(candidate.id);
        if (!matchesSearch || !matchesFc || !matchesLevel || !matchesAvailability) continue;
        visibleIds.push(candidate.id);
        let ld = roots.get(candidate.logical_device);
        if (!ld) {
          ld = {
            id: "ld:" + candidate.logical_device,
            label: candidate.logical_device,
            type: "ld",
            children: [],
          };
          roots.set(candidate.logical_device, ld);
          groupIds.push(ld.id);
        }
        const lnId = "ln:" + candidate.logical_device + "/" + candidate.logical_node;
        let ln = logicalNodes.get(lnId);
        if (!ln) {
          ln = { id: lnId, label: candidate.logical_node, type: "ln", children: [] };
          ld.children.push(ln);
          logicalNodes.set(lnId, ln);
          groupIds.push(lnId);
        }
        if (candidate.selection_level === "DO") {
          ln.children.push({
            id: candidate.id,
            label: candidate.data_object,
            type: "candidate",
            candidate,
            disabled: candidate.existing,
          });
          continue;
        }
        const doId = "do:" + candidate.group_key;
        let dataObject = dataObjects.get(doId);
        if (!dataObject) {
          dataObject = {
            id: doId,
            label: candidate.data_object,
            type: "do",
            children: [],
          };
          ln.children.push(dataObject);
          dataObjects.set(doId, dataObject);
          groupIds.push(doId);
        }
        dataObject.children.push({
          id: candidate.id,
          label: candidate.data_attribute,
          type: "candidate",
          candidate,
          disabled: candidate.existing,
        });
      }
      self.postMessage({ tree: Array.from(roots.values()), visibleIds, groupIds });
    };
  `;
  return new Promise<ReturnType<typeof buildCandidateTreeSync>>(
    (resolve, reject) => {
      const workerUrl = URL.createObjectURL(
        new Blob([workerSource], { type: "text/javascript" }),
      );
      const worker = new Worker(workerUrl);
      activeTreeWorkers.add(worker);
      const cleanup = () => {
        worker.terminate();
        activeTreeWorkers.delete(worker);
        URL.revokeObjectURL(workerUrl);
      };
      worker.onmessage = ({ data }) => {
        cleanup();
        resolve(data);
      };
      worker.onerror = (event) => {
        cleanup();
        reject(new Error(event.message || "候选树构建失败"));
      };
      worker.postMessage({ candidates, filters });
    },
  );
}

watch(
  [keyword, fcFilter, onlyAvailable, selectionLevel],
  (_value, _previous, onCleanup) => {
    const timer = window.setTimeout(() => {
      if (!loading.value) void rebuildCandidateTree();
    }, 180);
    onCleanup(() => window.clearTimeout(timer));
  },
);

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) {
      destroySelectedListSortable();
      return;
    }
    await loadCandidates();
    await nextTick();
    setupSelectedListSortable();
  },
  { immediate: true },
);

async function loadCandidates() {
  loading.value = true;
  try {
    const result = await modelingApi.getDataSetMemberCandidates(
      props.projectId,
      props.dataSet.id,
    );
    discovery.value = result;
    await indexCandidates(result.candidates);
    selectedIds.clear();
    const existing = result.existing_members
      .map((member) => member.candidate_id)
      .filter((id): id is string => Boolean(id));
    existing.forEach((id) => selectedIds.add(id));
    if (result.existing_members.length) {
      selectionLevel.value = result.existing_members.some(
        (member) => !String(member.attributes.daName || ""),
      )
        ? "DO"
        : "DA";
    }
    existingCandidateIds.value = new Set(existing);
    selectedOrder.value = [...existing];
    initialSelectedOrder.value = [...existing];
    Object.keys(repairSelections).forEach(
      (key) => delete repairSelections[key],
    );
    await rebuildCandidateTree();
  } finally {
    loading.value = false;
  }
}

async function indexCandidates(candidates: DataSetMemberCandidate[]) {
  const byId = new Map<string, DataSetMemberCandidate>();
  const companions = new Map<string, string[]>();
  const functionalConstraints = new Set<string>();
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index];
    byId.set(candidate.id, candidate);
    if (candidate.fc) functionalConstraints.add(candidate.fc);
    if (candidate.is_companion) {
      const key = `${candidate.group_key}|${candidate.fc}`;
      const ids = companions.get(key) || [];
      ids.push(candidate.id);
      companions.set(key, ids);
    }
    if (index > 0 && index % 2000 === 0) await yieldToBrowser();
  }
  candidateById.value = byId;
  companionIdsByGroup.value = companions;
  fcOptions.value = Array.from(functionalConstraints).sort();
}

async function rebuildCandidateTree() {
  const requestId = ++treeBuildRequest;
  const candidates = discovery.value?.candidates || [];
  treeBuilding.value = true;
  try {
    const result = await buildCandidateTreeOffMainThread(candidates, {
      keyword: keyword.value.trim().toLowerCase(),
      fc: fcFilter.value,
      onlyAvailable: onlyAvailable.value,
      selectionLevel: selectionLevel.value,
      selectedIds: Array.from(selectedIds),
    });
    if (requestId !== treeBuildRequest) return;
    candidateTree.value = result.tree;
    visibleCandidateIds.value = new Set(result.visibleIds);
    filteredCandidateCount.value = result.visibleIds.length;
    const firstRoot = result.tree[0];
    defaultExpandedKeys.value = keyword.value.trim()
      ? result.groupIds
      : [
          firstRoot?.id,
          firstRoot?.children?.[0]?.id,
          firstRoot?.children?.[0]?.children?.[0]?.id,
        ].filter((id): id is string => Boolean(id));
    await nextTick();
    syncTreeChecks();
  } finally {
    if (requestId === treeBuildRequest) treeBuilding.value = false;
  }
}

function syncTreeChecks() {
  treeRef.value?.setCheckedKeys(Array.from(selectedIds));
}

function handleTreeCheck() {
  const checkedIds = new Set(treeRef.value?.getCheckedKeys(true) || []);
  const newlyChecked: string[] = [];
  for (const id of visibleCandidateIds.value) {
    if (existingCandidateIds.value.has(id)) continue;
    if (checkedIds.has(id)) {
      if (!selectedIds.has(id)) newlyChecked.push(id);
      selectedIds.add(id);
    } else {
      selectedIds.delete(id);
    }
  }

  if (autoCompanions.value && selectionLevel.value === "DA") {
    for (const id of [...newlyChecked]) {
      const candidate = candidateById.value.get(id);
      if (!candidate || candidate.is_companion) continue;
      const companionIds =
        companionIdsByGroup.value.get(
          `${candidate.group_key}|${candidate.fc}`,
        ) || [];
      for (const companionId of companionIds) {
        if (!selectedIds.has(companionId)) newlyChecked.push(companionId);
        selectedIds.add(companionId);
      }
    }
  }
  updateSelectionOrder(newlyChecked);
  void nextTick(syncTreeChecks);
}

function updateSelectionOrder(appendIds: string[] = []) {
  const next = selectedOrder.value.filter((id) => selectedIds.has(id));
  for (const id of appendIds) {
    if (selectedIds.has(id) && !next.includes(id)) next.push(id);
  }
  selectedOrder.value = next;
}

function clearNewSelections() {
  for (const id of newCandidateIds.value) selectedIds.delete(id);
  updateSelectionOrder();
  void nextTick(syncTreeChecks);
}

function removeCandidate(id: string) {
  if (existingCandidateIds.value.has(id)) return;
  selectedIds.delete(id);
  updateSelectionOrder();
  void nextTick(syncTreeChecks);
}

function yieldToBrowser() {
  return new Promise<void>((resolve) =>
    window.requestAnimationFrame(() => resolve()),
  );
}

onBeforeUnmount(() => {
  destroySelectedListSortable();
  for (const worker of activeTreeWorkers) worker.terminate();
  activeTreeWorkers.clear();
});

function destroySelectedListSortable() {
  selectedListSortable?.destroy();
  selectedListSortable = undefined;
}

function setupSelectedListSortable() {
  destroySelectedListSortable();
  if (!selectedListRef.value) return;
  selectedListSortable = Sortable.create(selectedListRef.value, {
    animation: 160,
    draggable: ".selected-member.is-sortable",
    handle: ".drag-handle",
    ghostClass: "is-drag-ghost",
    chosenClass: "is-drag-chosen",
    dragClass: "is-dragging",
    onEnd(event) {
      const oldIndex = event.oldDraggableIndex;
      const newIndex = event.newDraggableIndex;
      if (oldIndex == null || newIndex == null || oldIndex === newIndex) {
        return;
      }
      const reordered = [...selectedOrder.value];
      const [moved] = reordered.splice(oldIndex, 1);
      if (!moved) return;
      reordered.splice(newIndex, 0, moved);
      selectedOrder.value = reordered;
    },
  });
}

async function createMembers() {
  if (!hasPendingChanges.value) return;
  submitting.value = true;
  try {
    const result = await modelingApi.createDataSetMembers(
      props.projectId,
      props.dataSet.id,
      newCandidateIds.value,
      selectedOrder.value,
    );
    const messages = [];
    if (result.created_count)
      messages.push(`生成 ${result.created_count} 个 FCDA`);
    if (result.reordered_count) messages.push("成员顺序已保存");
    if (result.skipped_count) {
      messages.push(`跳过 ${result.skipped_count} 个重复项`);
    }
    ElMessage.success(messages.join("，") || "DataSet 成员已保存");
    emit("changed", props.dataSet.id);
    emit("update:modelValue", false);
  } finally {
    submitting.value = false;
  }
}

async function repairMember(nodeId: string) {
  const candidateId = repairSelections[nodeId];
  if (!candidateId) return;
  repairingId.value = nodeId;
  try {
    await modelingApi.repairDataSetMember(
      props.projectId,
      props.dataSet.id,
      nodeId,
      candidateId,
    );
    ElMessage.success("失效 FCDA 已重新匹配");
    emit("changed", props.dataSet.id);
    await loadCandidates();
  } finally {
    repairingId.value = "";
  }
}

async function removeInvalidMember(nodeId: string) {
  await ElMessageBox.confirm(
    "确认从 DataSet 中移除这个失效 FCDA？",
    "移除失效成员",
    { type: "warning" },
  );
  removingId.value = nodeId;
  try {
    await modelingApi.deleteNode(props.projectId, nodeId);
    ElMessage.success("失效 FCDA 已移除");
    emit("changed", props.dataSet.id);
    await loadCandidates();
  } finally {
    removingId.value = "";
  }
}

function fcTagType(fc: string): "primary" | "success" | "danger" | "info" {
  if (fc === "ST") return "success";
  if (fc === "CO") return "danger";
  if (fc === "MX") return "primary";
  return "info";
}
</script>

<style scoped>
.dataset-member-page {
  min-width: 0;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px 16px;
  overflow: hidden;
  background: var(--bg-muted);
  box-sizing: border-box;
}
.selector-page-header,
.selector-page-footer {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--panel-bg);
  box-shadow: 0 3px 12px rgba(15, 23, 42, 0.045);
  box-sizing: border-box;
}
.selector-page-header {
  min-height: 70px;
  padding: 0 18px;
}
.selector-page-footer {
  min-height: 66px;
  padding: 0 18px;
}
.selector-header-actions {
  display: flex;
  gap: 8px;
}
.selector-title,
.selector-title > div > div,
.selector-footer,
.selector-footer > div {
  display: flex;
  align-items: center;
}
.selector-title {
  min-width: 0;
  flex: 1;
  justify-content: space-between;
  gap: 24px;
  padding-right: 32px;
}
.selector-title > div > div {
  gap: 8px;
  margin-top: 5px;
}
.selector-title strong {
  color: #172033;
  font-size: 19px;
  font-weight: 700;
}
.selector-title small,
.selector-title > span {
  color: var(--text-secondary);
  font-size: 11px;
}
.member-selector {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.selector-columns {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(500px, 1.16fr) minmax(430px, 1fr);
  gap: 12px;
  min-height: 0;
}
.selector-card {
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 12px;
  background: var(--panel-bg);
  box-shadow: 0 3px 12px rgba(15, 23, 42, 0.045);
}
.selector-card > header {
  min-height: 55px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 15px;
  border-bottom: 1px solid var(--border-color);
  background: var(--panel-bg);
}
.selector-card > header strong,
.selector-card > header small {
  display: block;
}
.selector-card > header strong {
  font-size: 14px;
}
.selector-card > header small {
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 11px;
}
.candidate-filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 104px 72px;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--panel-bg);
}
.candidate-filters :deep(.el-input__wrapper),
.candidate-filters :deep(.el-select__wrapper) {
  min-height: 36px;
  border-radius: 7px;
  background: var(--bg-subtle);
  box-shadow: 0 0 0 1px var(--border-color) inset;
}
.candidate-summary,
.selection-options {
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 13px;
  border-top: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
  background: var(--bg-subtle);
  font-size: 11px;
}
.candidate-summary {
  justify-content: space-between;
}
.candidate-tree-scroll,
.selected-list-scroll {
  min-height: 0;
  flex: 1;
}
.candidate-tree-scroll {
  padding: 7px 8px;
  overflow: hidden;
  background: var(--panel-bg);
}
.candidate-tree-scroll :deep(.el-tree-v2) {
  background: transparent;
  color: var(--text-primary);
}
.candidate-tree-scroll :deep(.el-tree-node__content) {
  position: relative;
  height: 36px;
  margin: 1px 0;
  border: 1px solid transparent;
  border-radius: 6px;
}
.candidate-tree-scroll :deep(.el-tree-node__content:hover) {
  border-color: #dbeafe;
  background: var(--bg-subtle);
}
.candidate-tree-scroll
  :deep(.el-tree-node__content:has(.el-checkbox.is-checked)) {
  border-color: #bfdbfe;
  background: #eff6ff;
}
.candidate-tree-scroll :deep(.el-tree-node__expand-icon) {
  color: var(--text-secondary);
}
.candidate-tree-scroll :deep(.el-checkbox__inner) {
  width: 16px;
  height: 16px;
  border-color: var(--border-color);
  border-radius: 3px;
}
.candidate-tree-scroll
  :deep(.el-checkbox__input.is-checked .el-checkbox__inner),
.candidate-tree-scroll
  :deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner) {
  border-color: #0062ff;
  background: #0062ff;
}
.candidate-node {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 7px;
  padding-right: 8px;
}
.candidate-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.candidate-kind-mark {
  display: grid;
  place-items: center;
  width: 24px;
  height: 20px;
  flex: 0 0 24px;
  border: 1px solid #dbeafe;
  border-radius: 5px;
  color: #2563eb;
  background: #eff6ff;
  font:
    700 8px "Geist Mono",
    monospace;
}
.candidate-node small {
  margin-left: auto;
  color: var(--text-secondary);
  font:
    10px "Geist Mono",
    monospace;
}
.candidate-node em {
  color: var(--text-secondary);
  font-size: 10px;
  font-style: normal;
}
.level-ld .candidate-label,
.level-ln .candidate-label {
  color: var(--text-primary);
  font-weight: 700;
}
.level-ln .candidate-kind-mark {
  border-color: #ddd6fe;
  color: #7c3aed;
  background: #f5f3ff;
}
.level-do .candidate-label {
  color: var(--text-secondary);
  font-weight: 600;
}
.level-do .candidate-kind-mark {
  border-color: #fed7aa;
  color: #c2410c;
  background: #fff7ed;
}
.level-candidate .candidate-kind-mark {
  border-color: #ccfbf1;
  color: #0f766e;
  background: #f0fdfa;
}
.candidate-node.existing {
  opacity: 0.72;
}
.selection-options > small {
  margin-left: auto;
  color: var(--text-secondary);
}
.selected-list-scroll {
  padding: 8px 10px;
  background: var(--panel-bg);
}
.selected-list {
  min-height: 1px;
}
.selected-member {
  min-height: 58px;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  padding: 7px 9px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--panel-bg);
  box-sizing: border-box;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}
.selected-member:hover {
  border-color: #bfdbfe;
  box-shadow: 0 3px 9px rgba(37, 99, 235, 0.07);
}
.drag-handle {
  display: grid;
  place-items: center;
  width: 24px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  color: var(--text-secondary);
  background: transparent;
  cursor: grab;
  touch-action: none;
}
.drag-handle:hover {
  color: #0062ff;
  background: #e7f0ff;
}
.drag-handle:active {
  cursor: grabbing;
}
.drag-handle > span {
  width: 12px;
  height: 20px;
  background-image: radial-gradient(
    circle,
    currentColor 1.3px,
    transparent 1.5px
  );
  background-position: 0 0;
  background-size: 6px 6px;
}
.drag-handle.is-disabled {
  opacity: 0.28;
  cursor: not-allowed;
}
.selected-member.is-drag-chosen {
  border-color: #60a5fa;
}
.selected-member.is-drag-ghost {
  border: 1px dashed #0062ff;
  background: #eff6ff;
  opacity: 0.48;
}
.selected-member.is-dragging {
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.16);
  cursor: grabbing;
}
.selected-member code,
.invalid-member code {
  display: block;
  overflow: hidden;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
  font:
    600 11px "Geist Mono",
    monospace;
}
.selected-member small {
  display: block;
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 10px;
}
.member-actions {
  display: flex;
}
.member-actions .el-button {
  margin: 0;
}
.invalid-member {
  margin-top: 9px;
  padding: 11px;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  background: #fef2f2;
}
.invalid-member > div:first-child {
  display: flex;
  align-items: center;
  gap: 8px;
}
.invalid-member p {
  margin: 7px 0;
  color: #b91c1c;
  font-size: 11px;
}
.repair-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 7px;
}
.preflight {
  min-height: 50px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 14px;
  border-top: 1px solid #fde68a;
  color: #047857;
  background: #fffbeb;
}
.preflight strong,
.preflight small {
  display: block;
}
.preflight strong {
  color: var(--text-primary);
  font-size: 11px;
}
.preflight small {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 10px;
}
.selector-footer {
  justify-content: space-between;
  gap: 16px;
}
.selector-footer > span {
  color: var(--text-secondary);
  font:
    11px "Geist Mono",
    monospace;
}
.selector-footer > span strong {
  color: #0062ff;
}
.selector-footer > div {
  gap: 8px;
}
@media (max-width: 980px) {
  .selector-columns {
    grid-template-columns: 1fr;
  }
  .selector-card {
    min-height: 420px;
  }
}
</style>
