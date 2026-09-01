<template>
  <section class="sg-manager">
    <header class="workbench-header">
      <div>
        <h2>定值组管理</h2>
        <p>IEC 61850 SGCB · {{ selectedControlPath }}</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="reloadAll">
          读取设备
        </el-button>
        <el-button
          :icon="CircleCheck"
          :loading="confirming"
          :disabled="!detail?.writable || changedSettings.length === 0"
          @click="confirmChanges"
        >
          确认编辑
        </el-button>
        <el-button
          type="primary"
          :icon="SwitchButton"
          :loading="activating"
          :disabled="!detail?.edit_sg"
          @click="activateCurrentEditGroup"
        >
          激活组 {{ padGroup(detail?.edit_sg) }}
        </el-button>
      </div>
    </header>

    <div class="workbench-body">
      <aside class="tree-panel">
        <div class="panel-title">
          <span>定值控制块</span>
          <el-tag size="small" effect="plain">{{ controls.length }}</el-tag>
        </div>
        <el-input
          v-model="treeKeyword"
          :prefix-icon="Search"
          clearable
          placeholder="搜索 IED 或 SGCB"
        />
        <el-scrollbar class="tree-scroll">
          <div v-if="filteredControls.length" class="control-list">
            <button
              v-for="control in filteredControls"
              :key="control.ref"
              class="control-item"
              :class="{ active: selectedControl?.ref === control.ref }"
              @click="selectControl(control)"
            >
              <span class="control-icon"
                ><el-icon><SetUp /></el-icon
              ></span>
              <span class="control-copy">
                <strong>{{ control.name }}</strong>
                <small>{{ control.ld }} / {{ control.ln }}</small>
              </span>
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
          <el-empty v-else :image-size="68" description="未发现定值控制块" />
        </el-scrollbar>
      </aside>

      <main class="detail-panel" v-loading="detailLoading">
        <el-empty
          v-if="!selectedControl && !detailLoading"
          description="请从左侧选择定值控制块"
        />
        <template v-else-if="detail">
          <div class="detail-heading">
            <div>
              <div class="heading-row">
                <h3>{{ detail.name }}</h3>
                <el-tag v-if="detail.writable" type="success" size="small">
                  可写入
                </el-tag>
              </div>
              <p>{{ detail.ref }}</p>
            </div>
          </div>

          <div class="property-strip">
            <div class="property-cell">
              <span>定值组数量 (NumOfSG)</span>
              <strong>{{ detail.num_of_sg ?? "—" }}</strong>
            </div>
            <div class="property-cell current">
              <span>当前活动组 (ActSG)</span>
              <strong>{{ padGroup(detail.act_sg) }}</strong>
            </div>
            <div class="property-cell editing">
              <span>当前编辑组 (EditSG)</span>
              <strong>{{ padGroup(detail.edit_sg) }}</strong>
            </div>
            <div class="property-cell">
              <span>编辑确认 (CnfEdit)</span>
              <strong>{{ detail.cnf_edit ? "TRUE" : "FALSE" }}</strong>
            </div>
            <div class="property-cell">
              <span>最后激活时间</span>
              <strong>{{ formatTime(detail.last_activation_time) }}</strong>
            </div>
          </div>

          <div class="group-selector">
            <button
              class="group-page-button"
              title="上一页"
              aria-label="上一页定值组"
              :disabled="groupPage === 0"
              @click="groupPage--"
            >
              <el-icon><ArrowLeft /></el-icon>
            </button>
            <div ref="groupWindowRef" class="group-window">
              <button
                v-for="group in visibleGroupNumbers"
                :key="group"
                class="group-button"
                :class="{
                  current: group === detail.act_sg,
                  editing: group === detail.edit_sg,
                }"
                :title="groupTitle(group)"
                :disabled="selectingGroup"
                @click="chooseEditGroup(group)"
              >
                <span>定值组 {{ padGroup(group) }}</span>
                <small
                  v-if="group === detail.act_sg && group === detail.edit_sg"
                  class="current-editing-badge"
                >
                  当前/编辑
                </small>
                <small
                  v-else-if="group === detail.act_sg"
                  class="current-badge"
                >
                  当前
                </small>
                <small
                  v-else-if="group === detail.edit_sg"
                  class="editing-badge"
                >
                  编辑
                </small>
              </button>
            </div>
            <span v-if="groupPageCount > 1" class="group-page-status">
              {{ groupPage + 1 }}/{{ groupPageCount }}
            </span>
            <button
              class="group-page-button"
              title="下一页"
              aria-label="下一页定值组"
              :disabled="groupPage >= groupPageCount - 1"
              @click="groupPage++"
            >
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>

          <div class="settings-section">
            <div class="settings-toolbar">
              <div class="settings-title">
                <h3>定值参数</h3>
                <el-tag
                  v-if="changedSettings.length"
                  type="primary"
                  effect="light"
                >
                  {{ changedSettings.length }} 项已修改
                </el-tag>
              </div>
              <el-input
                v-model="settingKeyword"
                :prefix-icon="Search"
                clearable
                placeholder="搜索参数或对象引用"
              />
            </div>

            <div class="table-wrap">
              <el-table
                :data="filteredSettings"
                height="100%"
                stripe
                row-key="address"
                empty-text="未发现 FC=SG 定值参数"
              >
                <el-table-column label="对象引用" min-width="250">
                  <template #default="{ row }">
                    <code>{{ displayRef(row.ref) }}</code>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="description"
                  label="说明"
                  min-width="130"
                >
                  <template #default="{ row }">{{
                    row.description || "—"
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="unit"
                  label="单位"
                  width="78"
                  align="center"
                >
                  <template #default="{ row }">{{ row.unit || "—" }}</template>
                </el-table-column>
                <el-table-column
                  :label="`组 ${padGroup(detail.act_sg)}（当前）`"
                  width="150"
                >
                  <template #default="{ row }">
                    <span class="current-value">{{
                      formatValue(row.current_value)
                    }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  :label="`组 ${padGroup(detail.edit_sg)}（编辑）`"
                  width="170"
                >
                  <template #default="{ row }">
                    <el-input
                      v-model="editValues[row.address]"
                      :disabled="!detail.writable"
                      :class="{ changed: isChanged(row) }"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="变化" width="92" align="center">
                  <template #default="{ row }">
                    <span :class="['delta', { changed: isChanged(row) }]">
                      {{ deltaValue(row) }}
                    </span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <footer class="table-footer">
              <span>共 {{ filteredSettings.length }} 项 · FC=SG</span>
              <span><i></i>蓝色单元格为编辑组待确认值</span>
            </footer>
          </div>

          <div v-if="detail.edit_sg" class="activation-note">
            <el-icon><Warning /></el-icon>
            <div>
              <strong>
                激活定值组
                {{ padGroup(detail.edit_sg) }} 后，设备将立即应用已确认的定值。
              </strong>
              <span>
                设备在线 · 编辑组{{ detail.writable ? "可写" : "只读" }} ·
                {{ changedSettings.length }} 项偏离基线
              </span>
            </div>
          </div>
        </template>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  onActivated,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowLeft,
  ArrowRight,
  CircleCheck,
  Refresh,
  Search,
  SetUp,
  SwitchButton,
  Warning,
} from "@element-plus/icons-vue";
import {
  activateSettingGroup,
  confirmSettingGroup,
  getSettingGroupDetail,
  listSettingGroups,
  selectEditGroup,
  writeSettingValues,
  type SettingGroupControl,
  type SettingGroupDetail,
  type SettingValue,
} from "@/api/settingGroupApi";

const props = defineProps<{ channelId: number }>();

const loading = ref(false);
const detailLoading = ref(false);
const confirming = ref(false);
const activating = ref(false);
const selectingGroup = ref(false);
const controls = ref<SettingGroupControl[]>([]);
const selectedControl = ref<SettingGroupControl | null>(null);
const detail = ref<SettingGroupDetail | null>(null);
const treeKeyword = ref("");
const settingKeyword = ref("");
const groupWindowRef = ref<HTMLElement | null>(null);
const groupsPerPage = ref(1);
const groupPage = ref(0);
const editValues = reactive<Record<string, string>>(Object.create(null));
let groupResizeObserver: ResizeObserver | null = null;

const selectedControlPath = computed(() =>
  selectedControl.value
    ? `${selectedControl.value.ld} / ${selectedControl.value.ln}`
    : "未选择控制块",
);

const filteredControls = computed(() => {
  const keyword = treeKeyword.value.trim().toLowerCase();
  if (!keyword) return controls.value;
  return controls.value.filter((item) =>
    `${item.name} ${item.ref} ${item.ld} ${item.ln}`
      .toLowerCase()
      .includes(keyword),
  );
});

const groupNumbers = computed(() => {
  const count = Number(detail.value?.num_of_sg || 0);
  return Array.from({ length: count }, (_, index) => index + 1);
});

const groupPageCount = computed(() =>
  Math.max(1, Math.ceil(groupNumbers.value.length / groupsPerPage.value)),
);

const visibleGroupNumbers = computed(() => {
  const start = groupPage.value * groupsPerPage.value;
  return groupNumbers.value.slice(start, start + groupsPerPage.value);
});

const filteredSettings = computed(() => {
  const keyword = settingKeyword.value.trim().toLowerCase();
  const settings = detail.value?.settings || [];
  if (!keyword) return settings;
  return settings.filter((item) =>
    `${item.ref} ${item.code} ${item.description}`
      .toLowerCase()
      .includes(keyword),
  );
});

const changedSettings = computed(() =>
  (detail.value?.settings || []).filter((item) => isChanged(item)),
);

function padGroup(group: number | null | undefined) {
  return group == null ? "—" : String(group).padStart(2, "0");
}

function groupTitle(group: number) {
  const states = [];
  if (group === detail.value?.act_sg) states.push("当前组");
  if (group === detail.value?.edit_sg) states.push("编辑组");
  return `定值组 ${padGroup(group)}${states.length ? ` · ${states.join(" · ")}` : ""}`;
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function formatTime(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return new Date(value).toLocaleTimeString([], { hour12: false });
  }
  return String(value);
}

function displayRef(value: string) {
  return value.includes("/") ? value.split("/", 2)[1] : value;
}

function isChanged(row: SettingValue) {
  return editValues[row.address] !== formatValue(row.current_value);
}

function deltaValue(row: SettingValue) {
  if (!isChanged(row)) return "—";
  const current = Number(row.current_value);
  const editing = Number(editValues[row.address]);
  if (Number.isFinite(current) && Number.isFinite(editing)) {
    const delta = editing - current;
    return `${delta > 0 ? "+" : ""}${Number(delta.toFixed(6))}`;
  }
  return "已修改";
}

function resetEditValues(nextDetail: SettingGroupDetail) {
  for (const key of Object.keys(editValues)) delete editValues[key];
  for (const setting of nextDetail.settings) {
    editValues[setting.address] = formatValue(
      setting.edit_value ?? setting.current_value,
    );
  }
}

async function loadDetail(control = selectedControl.value) {
  if (!control || !props.channelId) return;
  detailLoading.value = true;
  try {
    const result = await getSettingGroupDetail(props.channelId, control.ref);
    if (selectedControl.value?.ref !== control.ref || !result) return;
    detail.value = { ...result, ...control };
    resetEditValues(detail.value);
  } finally {
    detailLoading.value = false;
  }
}

async function reloadAll() {
  if (!props.channelId) return;
  const previousRef = selectedControl.value?.ref;
  loading.value = true;
  try {
    controls.value = await listSettingGroups(props.channelId);
    selectedControl.value =
      controls.value.find((item) => item.ref === previousRef) ||
      controls.value[0] ||
      null;
    detail.value = null;
    await loadDetail();
  } finally {
    loading.value = false;
  }
}

async function selectControl(control: SettingGroupControl) {
  if (selectedControl.value?.ref === control.ref) return;
  selectedControl.value = control;
  detail.value = null;
  await loadDetail(control);
}

async function chooseEditGroup(group: number) {
  if (!detail.value || group === detail.value.edit_sg || selectingGroup.value)
    return;
  if (changedSettings.value.length) {
    await ElMessageBox.confirm(
      "切换编辑组会丢弃当前未确认修改，是否继续？",
      "切换编辑组",
      {
        type: "warning",
        confirmButtonText: "继续切换",
        cancelButtonText: "取消",
      },
    );
  }
  selectingGroup.value = true;
  try {
    if (await selectEditGroup(props.channelId, detail.value.ref, group)) {
      ElMessage.success(`已选择定值组 ${padGroup(group)} 进行编辑`);
      await loadDetail();
    }
  } finally {
    selectingGroup.value = false;
  }
}

async function confirmChanges() {
  if (!detail.value || !changedSettings.value.length) return;
  await ElMessageBox.confirm(
    `将写入并确认 ${changedSettings.value.length} 项定值，是否继续？`,
    "确认编辑",
    {
      type: "warning",
      confirmButtonText: "写入并确认",
      cancelButtonText: "取消",
    },
  );
  confirming.value = true;
  try {
    const values = changedSettings.value.map((item) => ({
      address: item.address,
      value: editValues[item.address],
    }));
    const written = await writeSettingValues(
      props.channelId,
      detail.value.ref,
      values,
    );
    if (!written) return;
    if (await confirmSettingGroup(props.channelId, detail.value.ref)) {
      ElMessage.success("编辑定值已确认");
      await loadDetail();
    }
  } finally {
    confirming.value = false;
  }
}

async function activateCurrentEditGroup() {
  if (!detail.value?.edit_sg) return;
  const group = detail.value.edit_sg;
  await ElMessageBox.confirm(
    `激活定值组 ${padGroup(group)} 后设备将立即应用已确认定值。`,
    "激活定值组",
    {
      type: "warning",
      confirmButtonText: "确认激活",
      cancelButtonText: "取消",
    },
  );
  activating.value = true;
  try {
    if (await activateSettingGroup(props.channelId, detail.value.ref, group)) {
      ElMessage.success(`定值组 ${padGroup(group)} 已激活`);
      await loadDetail();
    }
  } finally {
    activating.value = false;
  }
}

watch(() => props.channelId, reloadAll);
watch(
  () =>
    [
      detail.value?.ref,
      detail.value?.num_of_sg,
      detail.value?.edit_sg,
      groupsPerPage.value,
    ] as const,
  ([controlRef, , editGroup], [previousRef]) => {
    if (controlRef !== previousRef) groupPage.value = 0;
    const focusGroup = Number(editGroup || detail.value?.act_sg || 1);
    groupPage.value = Math.min(
      Math.floor((focusGroup - 1) / groupsPerPage.value),
      groupPageCount.value - 1,
    );
  },
);
watch(
  groupWindowRef,
  (element, previousElement) => {
    if (!groupResizeObserver) return;
    if (previousElement) groupResizeObserver.unobserve(previousElement);
    if (element) groupResizeObserver.observe(element);
  },
  { flush: "post" },
);
onMounted(() => {
  reloadAll();
  if (typeof ResizeObserver === "undefined") return;
  groupResizeObserver = new ResizeObserver(([entry]) => {
    const availableWidth = Math.max(0, entry.contentRect.width);
    groupsPerPage.value = Math.max(1, Math.floor((availableWidth + 6) / 132));
  });
  if (groupWindowRef.value) groupResizeObserver.observe(groupWindowRef.value);
});
onBeforeUnmount(() => {
  groupResizeObserver?.disconnect();
  groupResizeObserver = null;
});
onActivated(() => props.channelId && reloadAll());
</script>

<style scoped lang="scss">
.sg-manager {
  --sg-border: var(--border-color, #dfe5ec);
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--sg-border);
  border-radius: 6px;
  background: var(--panel-bg);
}

.workbench-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 74px;
  padding: 0 18px;
  border-bottom: 1px solid var(--sg-border);
  background: var(--bg-subtle);

  h2 {
    margin: 0 0 4px;
    color: var(--text-primary);
    font-size: 18px;
  }
  p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 12px;
  }
}

.header-actions {
  display: flex;
  gap: 8px;
}
.workbench-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.tree-panel {
  display: flex;
  flex: 0 0 270px;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding: 16px;
  border-right: 1px solid var(--sg-border);
  background: var(--bg-subtle);
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-primary);
  font-weight: 700;
}
.tree-scroll {
  flex: 1;
  min-height: 0;
}
.control-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.control-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text-primary);
  background: transparent;
  cursor: pointer;
  text-align: left;

  &:hover {
    background: var(--bg-muted);
  }
  &.active {
    border-color: #bfdbfe;
    background: #eff6ff;
    color: #2563eb;
  }
}
.control-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  background: #e8edf3;
}
.control-copy {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}
.control-copy strong,
.control-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.control-copy small {
  color: var(--text-secondary);
  font-size: 11px;
}

.detail-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 16px;
  overflow: hidden;
}
.detail-heading {
  display: flex;
  align-items: center;
  min-height: 48px;
}
.heading-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.heading-row h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 17px;
}
.detail-heading p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.property-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin: 10px 0 12px;
  border: 1px solid var(--sg-border);
  border-radius: 5px;
  overflow: hidden;
}
.property-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 11px 13px;
  border-right: 1px solid var(--sg-border);
  background: var(--bg-subtle);
}
.property-cell:last-child {
  border-right: 0;
}
.property-cell span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.property-cell strong {
  color: var(--text-primary);
  font-size: 15px;
}
.property-cell.current {
  background: #f0fdf4;
}
.property-cell.current strong {
  color: #059669;
}
.property-cell.editing {
  background: #eff6ff;
}
.property-cell.editing strong {
  color: #2563eb;
}

.group-selector {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin-bottom: 12px;
}
.group-window {
  display: flex;
  flex: 1;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}
.group-button {
  display: flex;
  flex: 0 0 126px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  height: 34px;
  padding: 0 8px;
  overflow: hidden;
  border: 1px solid var(--sg-border);
  border-radius: 4px;
  color: var(--text-secondary);
  background: var(--panel-bg);
  cursor: pointer;
  font-size: 13px;
}
.group-button:hover {
  border-color: #93c5fd;
  color: #2563eb;
}
.group-button.current {
  border-color: #86efac;
  color: #047857;
  background: #f0fdf4;
}
.group-button.editing {
  border-color: #60a5fa;
  color: #2563eb;
  background: #eff6ff;
  box-shadow: 0 0 0 1px #bfdbfe inset;
}
.group-button > span {
  flex: none;
  white-space: nowrap;
}
.group-button small {
  flex: none;
  padding: 1px 5px;
  border-radius: 8px;
  color: #fff;
  font-size: 11px;
  line-height: 16px;
  white-space: nowrap;
}
.group-button .current-badge {
  background: #059669;
}
.group-button .editing-badge {
  background: #2563eb;
}
.group-button .current-editing-badge {
  padding-inline: 3px;
  background: #2563eb;
  font-size: 10px;
}
.group-page-button {
  display: grid;
  flex: 0 0 28px;
  place-items: center;
  width: 28px;
  height: 34px;
  padding: 0;
  border: 1px solid var(--sg-border);
  border-radius: 4px;
  color: var(--text-secondary);
  background: var(--panel-bg);
  cursor: pointer;
}
.group-page-button:hover:not(:disabled) {
  border-color: #93c5fd;
  color: #2563eb;
  background: #eff6ff;
}
.group-page-button:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}
.group-page-status {
  flex: none;
  min-width: 28px;
  color: var(--text-secondary);
  font-size: 10px;
  text-align: center;
}

.settings-section {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--sg-border);
  border-radius: 5px;
  overflow: hidden;
}
.settings-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 52px;
  padding: 0 12px;
  border-bottom: 1px solid var(--sg-border);
  background: var(--bg-subtle);
}
.settings-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.settings-title h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 14px;
}
.settings-toolbar .el-input {
  width: 280px;
}
.table-wrap {
  flex: 1;
  min-height: 220px;
}
code {
  color: var(--text-primary);
  font-family: "Roboto Mono", Consolas, monospace;
  font-size: 12px;
}
.current-value {
  color: #047857;
  font-family: "Roboto Mono", Consolas, monospace;
}
:deep(.el-input.changed .el-input__wrapper) {
  background: #eff6ff;
  box-shadow: 0 0 0 1px #93c5fd inset;
}
.delta {
  color: var(--text-secondary);
  font-family: "Roboto Mono", Consolas, monospace;
  font-size: 12px;
}
.delta.changed {
  color: #2563eb;
  font-weight: 700;
}
.table-footer {
  display: flex;
  justify-content: space-between;
  padding: 7px 12px;
  border-top: 1px solid var(--sg-border);
  color: var(--text-secondary);
  font-size: 11px;
}
.table-footer i {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 2px;
  background: #bfdbfe;
}
.activation-note {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #fde68a;
  border-radius: 4px;
  color: #92400e;
  background: #fff7e6;
}
.activation-note > .el-icon {
  font-size: 20px;
}
.activation-note div {
  display: flex;
  flex: 1;
  justify-content: space-between;
  gap: 20px;
  font-size: 12px;
}
.activation-note span {
  color: #a16207;
}

@container (max-width: 980px) {
  .workbench-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
    padding: 12px 16px;
  }
  .tree-panel {
    flex-basis: 230px;
  }
  .property-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .property-cell {
    border-bottom: 1px solid var(--sg-border);
  }
  .activation-note div {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
