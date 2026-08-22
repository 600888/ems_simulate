<template>
  <el-dialog
    :model-value="modelValue"
    width="1280px"
    :close-on-click-modal="false"
    class="sim-config-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <template #header>
      <div class="sim-config-header">
        <span class="dialog-title">{{ t("simConfig.title") }}</span>
        <el-tag size="small" effect="plain" type="info">{{
          deviceName
        }}</el-tag>
      </div>
    </template>

    <div v-loading="loading" class="sim-config-body">
      <el-tabs v-model="activeTab" class="sim-tabs">
        <!-- 页签1：测点选择 -->
        <el-tab-pane :label="t('simConfig.tabSelect')" name="select">
          <div class="select-layout">
            <!-- 左侧测点树 -->
            <section class="left-panel">
              <el-input
                v-model="keyword"
                clearable
                class="search-input"
                :placeholder="t('simConfig.searchPlaceholder')"
              >
                <template #prefix
                  ><el-icon><Search /></el-icon
                ></template>
              </el-input>
              <div ref="treeWrapRef" class="tree-wrap">
                <el-tree-v2
                  v-if="filteredTree.length"
                  :key="treeKey"
                  :data="filteredTree"
                  :props="treeProps"
                  :height="treeHeight"
                  :item-size="36"
                  :default-expanded-keys="filteredExpandedKeys"
                  :expand-on-click-node="false"
                  class="sim-tree"
                >
                  <template #default="{ data }">
                    <!-- 分组行（61850 同款级联勾选：点击分组全选/取消组内测点） -->
                    <div v-if="!data.point_code" class="group-node">
                      <el-checkbox
                        class="node-checkbox"
                        :model-value="groupChecked(data)"
                        :indeterminate="groupIndeterminate(data)"
                        @change="
                          (v: string | number | boolean) =>
                            setGroupSelected(data, Boolean(v))
                        "
                      />
                      <span class="group-label">{{ data.label }}</span>
                      <span class="group-count">
                        {{
                          t("simConfig.itemCount", { count: data.leafCount })
                        }}
                      </span>
                    </div>
                    <!-- 测点叶子行 -->
                    <div v-else class="leaf-node">
                      <el-checkbox
                        class="node-checkbox"
                        :model-value="selectedCodes.has(data.point_code)"
                        @change="
                          (v: string | number | boolean) =>
                            setLeafSelected(data, Boolean(v))
                        "
                      />
                      <span
                        class="leaf-name"
                        :title="`${data.label} (${data.point_code})`"
                      >
                        {{ data.label }}
                      </span>
                      <span class="leaf-code" :title="data.point_code">{{
                        data.point_code
                      }}</span>
                    </div>
                  </template>
                </el-tree-v2>
                <el-empty
                  v-else-if="!loading"
                  :description="t('simConfig.noPoints')"
                  :image-size="64"
                />
              </div>
            </section>

            <!-- 转移按钮 -->
            <section class="transfer-btns">
              <el-button
                type="primary"
                class="transfer-btn"
                :disabled="totalLeafCount === 0"
                :title="t('simConfig.moveIn')"
                @click="moveAllIn"
                >&gt;&gt;</el-button
              >
              <el-button
                type="danger"
                plain
                class="transfer-btn"
                :disabled="!selectedLeaves.length"
                :title="t('simConfig.moveOut')"
                @click="moveAllOut"
                >&lt;&lt;</el-button
              >
            </section>

            <!-- 右侧已选测点 -->
            <section class="right-panel">
              <header class="right-title">
                <div class="selected-title-tools">
                  <span class="selected-count">{{
                    t("simConfig.selectedCount", {
                      count: selectedLeaves.length,
                    })
                  }}</span>
                  <el-input
                    v-model="selectedKeyword"
                    clearable
                    size="small"
                    class="selected-search"
                    :disabled="!selectedLeaves.length"
                    :placeholder="t('simConfig.selectedSearchPlaceholder')"
                  >
                    <template #prefix>
                      <el-icon><Search /></el-icon>
                    </template>
                  </el-input>
                </div>
                <el-button
                  v-if="selectedLeaves.length"
                  text
                  size="small"
                  type="danger"
                  @click="moveAllOut"
                  >{{ t("simConfig.clearAll") }}</el-button
                >
              </header>
              <div ref="selectedListRef" class="selected-list">
                <template v-if="filteredSelectedLeaves.length">
                  <div
                    v-for="leaf in pagedLeaves"
                    :key="leaf.point_code"
                    :class="[
                      'selected-row',
                      {
                        'is-fixed-value': leaf.simulate_method === 'FixedValue',
                        'is-no-simulation': leaf.simulate_method === 'None',
                      },
                    ]"
                  >
                    <span
                      class="s-name"
                      :title="`${leaf.label} (${leaf.point_code})`"
                      >{{ leaf.label }}</span
                    >
                    <span class="s-field-label">{{
                      t("simConfig.method")
                    }}</span>
                    <el-select
                      v-model="leaf.simulate_method"
                      size="small"
                      class="s-method"
                    >
                      <el-option
                        v-for="opt in simulateOptions"
                        :key="opt.value"
                        :label="opt.label"
                        :value="opt.value"
                      />
                    </el-select>
                    <span
                      v-if="
                        leaf.simulate_method !== 'FixedValue' &&
                        leaf.simulate_method !== 'None'
                      "
                      class="s-field-label"
                      >{{ t("simConfig.step") }}</span
                    >
                    <el-input-number
                      v-if="
                        leaf.simulate_method !== 'FixedValue' &&
                        leaf.simulate_method !== 'None'
                      "
                      v-model="leaf.step"
                      size="small"
                      :min="0.001"
                      :max="10000"
                      :step="0.1"
                      :controls="false"
                      class="s-step"
                    />
                    <span
                      v-if="leaf.simulate_method === 'FixedValue'"
                      class="s-field-label"
                      >{{ t("simConfig.fixedValue") }}</span
                    >
                    <el-input-number
                      v-if="leaf.simulate_method === 'FixedValue'"
                      v-model="leaf.fixed_value"
                      size="small"
                      :controls="false"
                      class="s-fixed"
                      :placeholder="t('simConfig.fixedValue')"
                    />
                    <el-button
                      text
                      circle
                      size="small"
                      type="danger"
                      class="s-del"
                      :title="t('common.delete')"
                      @click="removeSelected(leaf)"
                    >
                      <el-icon><Close /></el-icon>
                    </el-button>
                  </div>
                  <el-pagination
                    class="selected-pager"
                    size="small"
                    @current-change="(p: number) => (currentPage = p)"
                    @size-change="handlePageSizeChange"
                    :current-page="currentPage"
                    :page-sizes="[10, 20, 50, 100]"
                    :page-size="pageSize"
                    background
                    layout="total, sizes, prev, pager, next, jumper"
                    :total="filteredSelectedLeaves.length"
                  />
                </template>
                <el-empty
                  v-else
                  :description="
                    selectedLeaves.length
                      ? t('simConfig.noSearchResults')
                      : t('simConfig.noSelected')
                  "
                  :image-size="48"
                />
              </div>
            </section>
          </div>
        </el-tab-pane>

        <!-- 页签2：模拟数据 -->
        <el-tab-pane :label="t('simConfig.tabData')" name="data">
          <div ref="dataPanelRef" class="data-panel">
            <div class="data-toolbar">
              <span>{{
                t("simConfig.dataCount", { count: selectedLeaves.length })
              }}</span>
              <div class="data-toolbar-actions">
                <div class="auto-refresh-group">
                  <el-switch v-model="autoRefresh" />
                  <span class="auto-refresh-label">{{
                    t("simConfig.autoRefresh")
                  }}</span>
                  <el-select
                    v-model="pollInterval"
                    :disabled="!autoRefresh"
                    class="refresh-interval-select"
                  >
                    <el-option
                      v-for="opt in REFRESH_INTERVAL_OPTIONS"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                  </el-select>
                </div>
                <el-button
                  :icon="Refresh"
                  :disabled="!selectedLeaves.length"
                  @click="refreshValues"
                  >{{ t("simConfig.refresh") }}</el-button
                >
                <el-button
                  class="sim-toggle-btn"
                  :type="simRunning ? 'danger' : 'success'"
                  :loading="simToggling"
                  :disabled="
                    (!selectedLeaves.length && !simRunning) ||
                    (!deviceRunning && !simRunning)
                  "
                  @click="toggleSimulation"
                >
                  <el-icon v-if="!simToggling" style="margin-right: 4px">
                    <VideoPause v-if="simRunning" />
                    <CaretRight v-else />
                  </el-icon>
                  {{ simRunning ? t("device.stopSim") : t("device.startSim") }}
                </el-button>
              </div>
            </div>
            <el-table
              v-loading="refreshing"
              :data="pagedDataLeaves"
              size="default"
              class="data-table"
              :empty-text="t('simConfig.noSelected')"
            >
              <el-table-column
                type="index"
                :label="t('simConfig.colIndex')"
                width="56"
                align="center"
              />
              <el-table-column
                :label="t('simConfig.colName')"
                prop="label"
                min-width="180"
                show-overflow-tooltip
              />
              <el-table-column
                :label="t('simConfig.colCode')"
                prop="point_code"
                width="250"
                show-overflow-tooltip
              />
              <el-table-column
                :label="t('simConfig.colFrameType')"
                width="90"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="FRAME_TYPE_TAG_MAP[String(row.frame_type)] || 'info'"
                    effect="light"
                    size="small"
                  >
                    {{ frameLabel(row.frame_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('simConfig.colMethod')" width="130">
                <template #default="{ row }">{{
                  methodLabel(row.simulate_method)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('simConfig.colStep')"
                width="80"
                align="center"
              >
                <template #default="{ row }">{{
                  row.simulate_method === "FixedValue" ? "—" : row.step
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('simConfig.colFixedValue')"
                width="100"
                align="center"
              >
                <template #default="{ row }">{{
                  row.simulate_method === "FixedValue"
                    ? formatValue(row.fixed_value)
                    : "—"
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('simConfig.colValue')"
                width="140"
                align="center"
              >
                <template #default="{ row }">{{
                  formatValue(row.value)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('simConfig.colStatus')"
                width="110"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag
                    size="small"
                    effect="plain"
                    :type="isSimulating(row) ? 'success' : 'danger'"
                  >
                    {{
                      isSimulating(row)
                        ? t("simConfig.statusRunning")
                        : t("simConfig.statusStopped")
                    }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div class="pagination-wrapper">
              <el-pagination
                size="small"
                @current-change="(p: number) => (dataCurrentPage = p)"
                @size-change="handleDataSizeChange"
                :current-page="dataCurrentPage"
                :page-sizes="[10, 20, 50, 100]"
                :page-size="dataPageSize"
                background
                layout="total, sizes, prev, pager, next, jumper"
                :total="selectedLeaves.length"
              />
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">
        {{ t("common.cancel") }}
      </el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        {{ t("common.save") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  shallowReactive,
  shallowRef,
  watch,
} from "vue";
import { useI18n } from "vue-i18n";
import {
  Close,
  Refresh,
  Search,
  CaretRight,
  VideoPause,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import {
  startSimulation,
  stopSimulation,
  applySimulationConfig,
  type SimulationConfigItem,
} from "@/api/deviceApi";
import {
  getPointTree,
  type DeviceNode,
  type GroupNode,
  type PointLeaf,
} from "@/api/pointTreeApi";
import { showErrorOnce } from "@/api/http";
import { batchPointValues } from "@/api/pointApi";
import { FRAME_TYPE_TAG_MAP } from "@/constants/table";

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
  /** 设备通讯是否已开启；未开启时允许配置，但不允许从 Dialog 启动模拟 */
  deviceRunning?: boolean;
  /** 设备模拟是否运行中（页签2“状态”列展示） */
  simulationRunning?: boolean;
  /** 父组件暂存的已保存配置（打开时优先回显） */
  savedConfig: SimulationConfigItem[] | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  /** 保存配置：由父组件持有，点"开始模拟"时应用 */
  (e: "save", config: SimulationConfigItem[]): void;
  /** 模拟开始/停止状态变化（供父组件立即同步外部按钮） */
  (e: "simulation-changed", running: boolean): void;
}>();

// ===== 类型 =====

interface SimTreeLeaf {
  id: string;
  label: string;
  point_code: string;
  reg_addr: string;
  frame_type: number;
  value: any;
  enabled: boolean;
  simulate_method: string;
  step: number;
  fixed_value: number;
}

interface SimTreeGroup {
  id: string;
  label: string;
  leafCount: number;
  dlt645_prefix?: number | null;
  dlt645_settlement?: number | null;
  /** 组内全部叶子测点编码（用于组级联全选/状态计算） */
  leafCodes: string[];
  children: (SimTreeGroup | SimTreeLeaf)[];
}

// ===== 状态 =====

const loading = ref(false);
const saving = ref(false);
const keyword = ref("");
const selectedKeyword = ref("");
const activeTab = ref("select");
/** 树数据：shallowRef 避免对 ~2 万个测点做深层响应式代理（61850 同款优化） */
const treeData = shallowRef<SimTreeGroup[]>([]);
const selectedLeaves = ref<SimTreeLeaf[]>([]);
/** 勾选集合：shallowReactive 的 Set，行内复选框直接读取 .has()（O(1)） */
const selectedCodes = shallowReactive(new Set<string>());
/** 每组已勾选数量（增量维护，组行复选框据此显示全选/半选） */
const groupSelCount = reactive<Record<string, number>>({});
/** 编码 → 测点叶子 索引（O(1) 查找，替代全树遍历） */
const leafIndex = new Map<string, SimTreeLeaf>();
/** 节点 → 祖先分组 id 列表（最近的父组在前，勾选时 O(depth) 更新组状态） */
const ancestorsById = new Map<string, string[]>();
const defaultExpandedKeys = ref<string[]>([]);
const treeWrapRef = ref<HTMLElement>();
const treeHeight = ref(420);
const selectedListRef = ref<HTMLElement>();
const dataPanelRef = ref<HTMLElement>();
const refreshing = ref(false);

// ===== 页签2（模拟数据）分页 =====
const dataPageSize = ref(20);
const dataCurrentPage = ref(1);
/** 当前页模拟数据 */
const pagedDataLeaves = computed<SimTreeLeaf[]>(() => {
  const start = (dataCurrentPage.value - 1) * dataPageSize.value;
  return selectedLeaves.value.slice(start, start + dataPageSize.value);
});
function handleDataSizeChange(size: number): void {
  dataPageSize.value = size;
  dataCurrentPage.value = 1;
}
watch(
  () => selectedLeaves.value.length,
  () => {
    const maxPage = Math.max(
      1,
      Math.ceil(selectedLeaves.value.length / dataPageSize.value),
    );
    if (dataCurrentPage.value > maxPage) dataCurrentPage.value = maxPage;
  },
);

// ===== 页签2（模拟数据）自动刷新 =====
const autoRefresh = ref(true);
const pollInterval = ref(1000);
const REFRESH_INTERVAL_OPTIONS = [
  { value: 1000, label: "1s" },
  { value: 3000, label: "3s" },
  { value: 5000, label: "5s" },
  { value: 10000, label: "10s" },
];
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

// ===== 页签2（模拟数据）开启/停止模拟 =====
const simRunning = ref(Boolean(props.simulationRunning));
const simToggling = ref(false);
watch(
  () => props.simulationRunning,
  (v) => {
    simRunning.value = Boolean(v);
  },
);

/** 收集当前勾选的测点配置（与"保存"一致的来源） */
function collectCurrentConfig(): SimulationConfigItem[] {
  const config: SimulationConfigItem[] = [];
  walkLeaves(treeData.value, (leaf) => {
    if (selectedCodes.has(leaf.point_code)) {
      config.push({
        point_code: leaf.point_code,
        enabled: true,
        simulate_method: leaf.simulate_method,
        step: leaf.step,
        fixed_value: leaf.fixed_value,
      });
    }
  });
  return config;
}

/** 开启/停止模拟：与主界面按钮一致（开始前应用当前配置） */
async function toggleSimulation(): Promise<void> {
  if (simToggling.value) return;
  simToggling.value = true;
  try {
    if (simRunning.value) {
      await stopSimulation(props.deviceName);
      simRunning.value = false;
      emit("simulation-changed", false);
    } else {
      const config = collectCurrentConfig();
      await applySimulationConfig(props.deviceName, config);
      await startSimulation(props.deviceName);
      simRunning.value = true;
      emit("simulation-changed", true);
    }
  } catch (error) {
    console.error("toggle simulation failed:", error);
  } finally {
    simToggling.value = false;
  }
}

function startAutoRefresh(): void {
  stopAutoRefresh();
  if (!autoRefresh.value || !selectedLeaves.value.length) return;
  refreshTimer = setTimeout(async () => {
    try {
      await refreshValues();
    } catch (error) {
      console.error("auto refresh values failed:", error);
    } finally {
      startAutoRefresh();
    }
  }, pollInterval.value);
}

function stopAutoRefresh(): void {
  if (refreshTimer !== null) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

watch([autoRefresh, pollInterval], () => startAutoRefresh());
watch(
  () => selectedLeaves.value.length,
  () => {
    if (selectedLeaves.value.length) startAutoRefresh();
    else stopAutoRefresh();
  },
);

// ===== 右侧已选测点分页 =====
const pageSize = ref(20);
const currentPage = ref(1);
/** 仅过滤右侧已加入测点，不影响左侧树及实际已选集合 */
const filteredSelectedLeaves = computed<SimTreeLeaf[]>(() => {
  const kw = selectedKeyword.value.trim().toLowerCase();
  if (!kw) return selectedLeaves.value;
  return selectedLeaves.value.filter(
    (leaf) =>
      leaf.label.toLowerCase().includes(kw) ||
      leaf.point_code.toLowerCase().includes(kw),
  );
});
/** 当前页已选测点 */
const pagedLeaves = computed<SimTreeLeaf[]>(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredSelectedLeaves.value.slice(start, start + pageSize.value);
});
/** 每页条数切换：回到第一页 */
function handlePageSizeChange(size: number): void {
  pageSize.value = size;
  currentPage.value = 1;
}
/** 已选变化时校正页码（删除/移出后回退到有效页） */
watch(
  () => filteredSelectedLeaves.value.length,
  () => {
    const maxPage = Math.max(
      1,
      Math.ceil(filteredSelectedLeaves.value.length / pageSize.value),
    );
    if (currentPage.value > maxPage) currentPage.value = maxPage;
  },
);
watch(selectedKeyword, () => {
  currentPage.value = 1;
});

/** 已保存配置快照（保存后保持回显一致） */
let savedSnapshot: SimulationConfigItem[] | null = null;

const treeProps = { children: "children", label: "label", value: "id" };

const simulateOptions = computed(() => [
  { value: "None", label: t("simConfig.methodNone") },
  { value: "FixedValue", label: t("device.fixedValue") },
  { value: "Random", label: t("device.random") },
  { value: "AutoIncrement", label: t("device.autoIncrement") },
  { value: "AutoDecrement", label: t("device.autoDecrement") },
  { value: "SineWave", label: t("device.sineWave") },
  { value: "Ramp", label: t("device.ramp") },
  { value: "Pulse", label: t("device.pulse") },
]);

const TYPE_FRAME: Record<string, number> = { YC: 0, YX: 1, YK: 2, YT: 3 };
const FRAME_LABEL_KEY: Record<number, string> = {
  0: "table.frameTypeYC",
  1: "table.frameTypeYX",
  2: "table.frameTypeYK",
  3: "table.frameTypeYT",
};
const METHOD_LABEL_KEY: Record<string, string> = {
  None: "simConfig.methodNone",
  FixedValue: "device.fixedValue",
  Random: "device.random",
  AutoIncrement: "device.autoIncrement",
  AutoDecrement: "device.autoDecrement",
  SineWave: "device.sineWave",
  Ramp: "device.ramp",
  Pulse: "device.pulse",
};
/** DLT645 数据标识前缀标签（与侧边栏 dlt645Tree 一致） */
const DLT645_PREFIX_LABEL_KEY = [
  "sidebar.dlt645.energy",
  "sidebar.dlt645.maxDemand",
  "sidebar.dlt645.variables",
  "sidebar.dlt645.events",
  "sidebar.dlt645.paramVars",
];

function frameLabel(frame: number): string {
  return t(FRAME_LABEL_KEY[frame] ?? "");
}

function methodLabel(method: string): string {
  return t(METHOD_LABEL_KEY[method] ?? "") || method;
}

function formatValue(value: any): string {
  return value === undefined || value === null ? "—" : String(value);
}

function isSimulating(_leaf: SimTreeLeaf): boolean {
  return Boolean(props.simulationRunning);
}

const totalLeafCount = computed(() => countLeaves(treeData.value));

// ===== 打开/加载 =====

async function handleOpen(): Promise<void> {
  activeTab.value = "select";
  keyword.value = "";
  selectedKeyword.value = "";
  await loadTree();
  await nextTick();
  measureTree();
  // 回显仅限用户保存过的配置（数量可控）。
  // 不自动带入后端当前配置：默认状态为"全部测点参与模拟"（2 万点全选会
  // 一次性渲染海量行导致卡死）；用户未配置时保持全不选，点"开始模拟"
  // 仍走后端默认逻辑。
  if (savedSnapshot?.length) {
    mergeConfig(savedSnapshot);
  } else {
    moveAllOut();
  }
}

async function loadTree(): Promise<void> {
  loading.value = true;
  try {
    // 后端已按设备名过滤；DLT645 设备的遥测分组由后端完成
    const tree = await getPointTree(props.deviceName);
    const deviceNode = tree.find((n) => n.label === props.deviceName);
    treeData.value = [];
    defaultExpandedKeys.value = [];
    if (deviceNode) {
      const groups: SimTreeGroup[] = [];
      for (const [index, typeNode] of (deviceNode.children ?? []).entries()) {
        const group = buildTypeGroup(typeNode, index);
        if (group.children.length) {
          groups.push(group);
        }
      }
      treeData.value = groups;
      indexTree(groups);
      // 默认只展开"含子组的组"（叶子组折叠），避免 el-tree-v2 在 2 万
      // 展开节点上每次展开/收起全量重建 flattenTree 导致卡顿
      defaultExpandedKeys.value = collectExpandKeys(groups);
    }
  } catch (error) {
    showErrorOnce(t("simConfig.loadTreeFailed"));
    console.error("load point tree failed:", error);
  } finally {
    loading.value = false;
  }
}

// ===== 树构建（递归消费后端分组树） =====

function createLeaf(leaf: PointLeaf, frame: number): SimTreeLeaf {
  const currentValue = Number(leaf.value);
  return {
    id: leaf.code,
    label: leaf.name ?? leaf.code,
    point_code: leaf.code,
    reg_addr: String(leaf.reg_addr ?? ""),
    frame_type: frame,
    value: leaf.value,
    enabled: true,
    simulate_method: "Random",
    step: 1,
    fixed_value: Number.isFinite(currentValue) ? currentValue : 0,
  };
}

function buildTypeGroup(
  typeNode: {
    label: string;
    frame_type?: number | null;
    children: (GroupNode | PointLeaf)[];
  },
  index: number,
): SimTreeGroup {
  const frame = typeNode.frame_type ?? findFrameType(typeNode.children) ?? 0;
  const groupId = `root-${index}-${typeNode.label}`;
  const children = buildNodes(typeNode.children, frame, groupId);
  return {
    id: groupId,
    label: typeNode.frame_type == null ? typeNode.label : frameLabel(frame),
    leafCount: countLeaves(children),
    leafCodes: collectLeafCodes(children),
    children,
  };
}

/** 递归转换：PointLeaf → SimTreeLeaf，GroupNode → SimTreeGroup */
function buildNodes(
  nodes: (GroupNode | PointLeaf)[],
  inheritedFrame: number,
  parentId: string,
): (SimTreeGroup | SimTreeLeaf)[] {
  const result: (SimTreeGroup | SimTreeLeaf)[] = [];
  for (const [index, node] of nodes.entries()) {
    if ("type" in node) {
      result.push(createLeaf(node, TYPE_FRAME[node.type] ?? inheritedFrame));
    } else {
      result.push(buildGroup(node, inheritedFrame, parentId, index));
    }
  }
  return result;
}

function buildGroup(
  node: GroupNode,
  inheritedFrame: number,
  parentId: string,
  index: number,
): SimTreeGroup {
  const groupId = `${parentId}-${index}-${node.label}`;
  const children = buildNodes(node.children, inheritedFrame, groupId);
  return {
    id: groupId,
    label: resolveGroupLabel(node),
    leafCount: countLeaves(children),
    leafCodes: collectLeafCodes(children),
    dlt645_prefix: node.dlt645_prefix,
    dlt645_settlement: node.dlt645_settlement,
    children,
  };
}

/** DLT645 分组标签：优先按前缀/结算日翻译，与侧边栏一致 */
function resolveGroupLabel(node: GroupNode): string {
  if (node.dlt645_settlement != null) {
    return node.dlt645_settlement === 0
      ? t("sidebar.dlt645.current")
      : t("sidebar.dlt645.prevSettlement", { n: node.dlt645_settlement });
  }
  if (node.dlt645_prefix != null) {
    const key = DLT645_PREFIX_LABEL_KEY[node.dlt645_prefix];
    return key ? t(key) : node.label;
  }
  return node.label;
}

/** 找到子树中第一个测点的帧类型 */
function findFrameType(nodes: (GroupNode | PointLeaf)[]): number | null {
  for (const node of nodes) {
    if ("type" in node) return TYPE_FRAME[node.type] ?? 0;
    const frame = findFrameType(node.children ?? []);
    if (frame !== null) return frame;
  }
  return null;
}

function countLeaves(nodes: (SimTreeGroup | SimTreeLeaf)[]): number {
  let count = 0;
  for (const node of nodes) {
    if ("point_code" in node) count += 1;
    else count += countLeaves(node.children);
  }
  return count;
}

function collectGroupIds(nodes: (SimTreeGroup | SimTreeLeaf)[]): string[] {
  const ids: string[] = [];
  const visit = (list: (SimTreeGroup | SimTreeLeaf)[]) => {
    for (const node of list) {
      if (!("point_code" in node)) {
        ids.push(node.id);
        visit(node.children);
      }
    }
  };
  visit(nodes);
  return ids;
}

/**
 * 收集"需要默认展开"的组 id：仅展开仍含子组的组，直接装叶子的组折叠。
 * 这样 el-tree-v2 的展开集合保持很小，展开/收起与勾选都不会触发
 * 全量节点重算（2 万测点时尤其关键）。
 */
function collectExpandKeys(groups: SimTreeGroup[]): string[] {
  const keys: string[] = [];
  const visit = (nodes: (SimTreeGroup | SimTreeLeaf)[]) => {
    for (const node of nodes) {
      if ("point_code" in node) continue;
      if (node.children.some((c) => !("point_code" in c))) {
        keys.push(node.id);
        visit(node.children);
      }
    }
  };
  visit(groups);
  return keys;
}

/** 递归遍历树中所有测点叶子 */
function walkLeaves(
  nodes: (SimTreeGroup | SimTreeLeaf)[],
  cb: (leaf: SimTreeLeaf) => void,
): void {
  for (const node of nodes) {
    if ("point_code" in node) cb(node);
    else walkLeaves(node.children, cb);
  }
}

/** 收集组内全部叶子编码（一次遍历） */
function collectLeafCodes(nodes: (SimTreeGroup | SimTreeLeaf)[]): string[] {
  const codes: string[] = [];
  walkLeaves(nodes, (leaf) => codes.push(leaf.point_code));
  return codes;
}

/**
 * 建树后索引：填充 leafIndex（code→叶子）、ancestorsById（节点→祖先组）、
 * groupSelCount 初始值。之后勾选仅需 O(1)/O(depth)，不再全树遍历。
 */
function indexTree(groups: SimTreeGroup[]): void {
  leafIndex.clear();
  ancestorsById.clear();
  for (const k of Object.keys(groupSelCount)) delete groupSelCount[k];
  const walk = (nodes: (SimTreeGroup | SimTreeLeaf)[], ancestors: string[]) => {
    for (const node of nodes) {
      if ("point_code" in node) {
        leafIndex.set(node.point_code, node);
        ancestorsById.set(node.point_code, ancestors);
      } else {
        ancestorsById.set(node.id, ancestors);
        groupSelCount[node.id] = 0;
        walk(node.children, [node.id, ...ancestors]);
      }
    }
  };
  walk(groups, []);
}

// ===== 过滤 =====

/** 递归按关键字过滤（叶子对象复用，保持编辑状态） */
function filterGroups(
  nodes: (SimTreeGroup | SimTreeLeaf)[],
  kw: string,
): (SimTreeGroup | SimTreeLeaf)[] {
  const result: (SimTreeGroup | SimTreeLeaf)[] = [];
  for (const node of nodes) {
    if ("point_code" in node) {
      if (
        node.label.toLowerCase().includes(kw) ||
        node.point_code.toLowerCase().includes(kw)
      ) {
        result.push(node);
      }
    } else {
      const filtered = filterGroups(node.children, kw);
      if (filtered.length) {
        result.push({ ...node, children: filtered });
      }
    }
  }
  return result;
}

const filteredTree = computed<SimTreeGroup[]>(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return treeData.value;
  return filterGroups(treeData.value, kw) as SimTreeGroup[];
});

/** 树组件重建标记：搜索时重建以应用新的展开集合（el-tree-v2 展开为初始化态） */
const treeKey = ref(0);
/** 展开集合：搜索时展开全部匹配组让结果可见；否则按默认（只展开含子组的组） */
const filteredExpandedKeys = computed<string[]>(() => {
  if (keyword.value.trim()) {
    return collectGroupIds(filteredTree.value);
  }
  return defaultExpandedKeys.value;
});

watch(keyword, () => {
  // 防抖：连续输入时不反复重建 2 万节点树
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    treeKey.value++;
  }, 250);
});
let searchTimer: number | undefined;

// ===== 勾选同步（自管理选中态，避免 el-tree-v2 内部每次勾选全树遍历） =====

/** 组行复选框：全选状态 */
function groupChecked(group: SimTreeGroup): boolean {
  const c = groupSelCount[group.id] ?? 0;
  return c > 0 && c === group.leafCodes.length;
}

/** 组行复选框：半选状态 */
function groupIndeterminate(group: SimTreeGroup): boolean {
  const c = groupSelCount[group.id] ?? 0;
  return c > 0 && c < group.leafCodes.length;
}

/** 勾选/取消单个测点（O(depth)：仅更新自身 + 祖先组计数） */
function setLeafSelected(leaf: SimTreeLeaf, selected: boolean): void {
  const code = leaf.point_code;
  if (selected === selectedCodes.has(code)) return;
  if (selected) {
    selectedCodes.add(code);
    leaf.enabled = true;
    selectedLeaves.value.push(leaf);
    for (const gid of ancestorsById.get(code) ?? []) {
      groupSelCount[gid] = (groupSelCount[gid] ?? 0) + 1;
    }
  } else {
    selectedCodes.delete(code);
    selectedLeaves.value = selectedLeaves.value.filter(
      (l) => l.point_code !== code,
    );
    for (const gid of ancestorsById.get(code) ?? []) {
      groupSelCount[gid] = Math.max(0, (groupSelCount[gid] ?? 1) - 1);
    }
  }
}

/** 组级联：勾选/取消整组（O(子树)），并同步组自身/后代/祖先状态 */
function setGroupSelected(group: SimTreeGroup, selected: boolean): void {
  if (selected === groupChecked(group)) return;
  if (selected) {
    walkLeaves([group], (leaf) => {
      if (!selectedCodes.has(leaf.point_code)) {
        selectedCodes.add(leaf.point_code);
        leaf.enabled = true;
        selectedLeaves.value.push(leaf);
      }
    });
  } else {
    const codes = new Set(group.leafCodes);
    for (const code of codes) selectedCodes.delete(code);
    selectedLeaves.value = selectedLeaves.value.filter(
      (l) => !codes.has(l.point_code),
    );
  }
  // 组自身及后代组：整组全选/全不选
  const apply = (nodes: (SimTreeGroup | SimTreeLeaf)[]) => {
    for (const node of nodes) {
      if (!("point_code" in node)) {
        groupSelCount[node.id] = selected ? node.leafCodes.length : 0;
        apply(node.children);
      }
    }
  };
  apply([group]);
  // 祖先组：计数增减整组大小
  const delta = selected ? group.leafCodes.length : -group.leafCodes.length;
  for (const gid of ancestorsById.get(group.id) ?? []) {
    groupSelCount[gid] = (groupSelCount[gid] ?? 0) + delta;
  }
}

/** 按树顺序全量应用勾选集（用于配置回显/移入全部，仅一次 O(N)） */
function selectCodesInOrder(codes: Set<string>): void {
  selectedCodes.clear();
  selectedLeaves.value = [];
  for (const gid of Object.keys(groupSelCount)) groupSelCount[gid] = 0;
  walkLeaves(treeData.value, (leaf) => {
    if (codes.has(leaf.point_code)) {
      selectedCodes.add(leaf.point_code);
      leaf.enabled = true;
      selectedLeaves.value.push(leaf);
    }
  });
  rebuildGroupCounts();
}

/** 从勾选集重建每组计数（仅用于全量应用场景） */
function rebuildGroupCounts(): void {
  for (const gid of Object.keys(groupSelCount)) groupSelCount[gid] = 0;
  for (const code of selectedCodes) {
    for (const gid of ancestorsById.get(code) ?? []) {
      groupSelCount[gid] = (groupSelCount[gid] ?? 0) + 1;
    }
  }
}

/** 移入：勾选全部测点 */
function moveAllIn(): void {
  selectCodesInOrder(new Set(leafIndex.keys()));
  currentPage.value = 1;
}

/** 移出：清空全部已选 */
function moveAllOut(): void {
  selectedCodes.clear();
  selectedLeaves.value = [];
  for (const gid of Object.keys(groupSelCount)) groupSelCount[gid] = 0;
  currentPage.value = 1;
}

/** 移除单个已选测点 */
function removeSelected(leaf: SimTreeLeaf): void {
  setLeafSelected(leaf, false);
}

// ===== 配置回显 =====

function mergeConfig(configs: SimulationConfigItem[]): void {
  const enabledCodes = new Set<string>();
  for (const cfg of configs) {
    const leaf = leafIndex.get(cfg.point_code);
    if (!leaf) continue;
    leaf.simulate_method = cfg.simulate_method ?? leaf.simulate_method;
    leaf.step = cfg.step ?? leaf.step;
    leaf.fixed_value = cfg.fixed_value ?? leaf.fixed_value;
    leaf.enabled = cfg.enabled ?? true;
    if (leaf.enabled) enabledCodes.add(cfg.point_code);
  }
  selectCodesInOrder(enabledCodes);
}

// ===== 页签2：刷新当前值 =====

/** 刷新已选测点当前值（轻量批量接口，供手动/自动刷新） */
async function refreshValues(): Promise<void> {
  if (!selectedLeaves.value.length) return;
  refreshing.value = true;
  try {
    const codes = selectedLeaves.value.map((l) => l.point_code);
    const values = await batchPointValues(props.deviceName, codes);
    for (const leaf of selectedLeaves.value) {
      if (values[leaf.point_code] !== undefined) {
        leaf.value = values[leaf.point_code];
      }
    }
  } catch (error) {
    console.error("refresh simulation values failed:", error);
  } finally {
    refreshing.value = false;
  }
}

// ===== 保存 =====

async function handleSave(): Promise<void> {
  saving.value = true;
  try {
    const config: SimulationConfigItem[] = selectedLeaves.value.map((leaf) => ({
      point_code: leaf.point_code,
      enabled: true,
      simulate_method: leaf.simulate_method,
      step: leaf.step,
      fixed_value: leaf.fixed_value,
    }));
    savedSnapshot = config;
    emit("save", config);
    // 保存成功后不关闭对话框，顶部轻提示
    ElMessage.success(t("simConfig.saveSuccess"));
  } finally {
    saving.value = false;
  }
}

// ===== 树高度自适应 =====

function measureTree(): void {
  if (treeWrapRef.value) {
    treeHeight.value = Math.max(120, treeWrapRef.value.clientHeight - 2);
  }
}

let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  measureTree();
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(measureTree);
    if (treeWrapRef.value) resizeObserver.observe(treeWrapRef.value);
  }
});

onBeforeUnmount(() => {
  stopAutoRefresh();
  resizeObserver?.disconnect();
  resizeObserver = null;
});
</script>

<style scoped>
.sim-config-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dialog-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
}
.sim-config-body {
  display: flex;
  flex-direction: column;
}
.sim-tabs {
  --el-tabs-header-height: 42px;
}
.sim-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.sim-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: var(--border-color, #e5e7eb);
}

/* ===== 页签1：测点选择 ===== */
.select-layout {
  display: flex;
  gap: 10px;
  height: 640px;
}

.left-panel {
  width: 360px;
  min-width: 360px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--border-radius-base, 12px);
  background: var(--panel-bg, #fff);
  overflow: hidden;
}
.search-input {
  margin: 10px;
  width: calc(100% - 20px);
}
.search-input :deep(.el-input__wrapper) {
  border-radius: 8px;
}
.tree-wrap {
  flex: 1;
  min-height: 0;
  padding: 0 6px 8px;
}
.sim-tree {
  width: 100%;
}
.sim-tree :deep(.el-tree-node__content) {
  height: 36px;
}
.sim-tree :deep(.el-checkbox__inner) {
  width: 16px;
  height: 16px;
  border-radius: 3px;
}
.sim-tree :deep(.el-checkbox__input.is-checked .el-checkbox__inner),
.sim-tree :deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner) {
  background-color: var(--color-primary, #3b82f6);
  border-color: var(--color-primary, #3b82f6);
}
.group-node,
.leaf-node {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 36px;
  padding-right: 8px;
  box-sizing: border-box;
}
.node-checkbox {
  margin-right: 0;
  flex: none;
}
.node-checkbox :deep(.el-checkbox__input) {
  display: inline-flex;
}
.group-label {
  font-weight: 600;
  color: var(--text-primary, #1f2937);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.group-count {
  margin-left: auto;
  flex: none;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-secondary, #909399);
}
.leaf-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.leaf-code {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-secondary, #909399);
}

/* 转移按钮 */
.transfer-btns {
  width: 48px;
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.transfer-btn {
  width: 40px;
  height: 40px;
  padding: 0;
  margin: 0;
  font-size: 16px;
  line-height: 1;
}

/* 右侧已选 */
.right-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--border-radius-base, 12px);
  background: var(--panel-bg, #fff);
  overflow: hidden;
}
.right-title {
  flex: none;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary, #1f2937);
}
.selected-title-tools {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}
.selected-count {
  flex: none;
  white-space: nowrap;
}
.selected-search {
  width: 240px;
  font-weight: 400;
}
.right-title .el-button {
  font-weight: 400;
}
.selected-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
  box-sizing: border-box;
}
.selected-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 64px 128px 40px 88px 24px;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  background: var(--panel-bg, #fff);
  box-sizing: border-box;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}
.selected-row.is-fixed-value {
  grid-template-columns: minmax(0, 1fr) 64px 128px 40px 88px 24px;
}
.selected-row.is-no-simulation {
  grid-template-columns: minmax(0, 1fr) 64px 128px 24px;
}
.selected-row:hover {
  border-color: #bfdbfe;
  box-shadow: 0 3px 9px rgba(37, 99, 235, 0.07);
}
.selected-pager {
  margin-top: 10px;
  justify-content: flex-start;
}
.s-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  color: var(--text-primary, #1f2937);
}
.s-method {
  width: 100%;
}
.s-field-label {
  color: var(--text-secondary, #606266);
  font-size: 13px;
  text-align: right;
  white-space: nowrap;
}
.s-step {
  width: 100%;
}
.s-fixed {
  width: 100%;
}
.s-del {
  margin: 0;
  width: 24px;
}

/* ===== 页签2：模拟数据 ===== */
.data-panel {
  display: flex;
  flex-direction: column;
  height: 640px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: var(--border-radius-base, 12px);
  overflow: hidden;
}
.data-toolbar {
  flex: none;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  background: var(--table-header-bg, #e8edf3);
  font-size: 14px;
  color: var(--text-primary, #1f2937);
}
.data-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.auto-refresh-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.auto-refresh-label {
  font-size: 14px;
  color: var(--text-primary, #1f2937);
  white-space: nowrap;
}
.refresh-interval-select {
  width: 70px;
  min-width: 70px;
}
.data-table {
  flex: 1;
  min-height: 0;
}
.data-table :deep(th.el-table__cell) {
  background-color: var(--table-header-bg, #e8edf3);
  color: var(--text-primary, #1f2937);
  font-weight: 600;
}
.data-table :deep(td.el-table__cell) {
  height: 40px;
}
.pagination-wrapper {
  flex: none;
  padding: 10px 14px;
  display: flex;
  justify-content: flex-start;
  border-top: 1px solid var(--border-color, #e5e7eb);
  background-color: var(--panel-bg, #fff);
}
</style>
