<template>
  <el-dialog
    v-model="visible"
    :title="t('log.viewer')"
    width="80%"
    top="5vh"
    class="log-viewer-dialog"
    destroy-on-close
    @closed="handleClose"
  >
    <div class="log-layout">
      <!-- 左侧 Sidebar：设备列表 -->
      <div class="log-sidebar">
        <div class="sidebar-header">{{ t("log.deviceList") }}</div>
        <div class="sidebar-device-list">
          <div
            class="sidebar-device-item"
            :class="{ active: filterDevice === '' }"
            @click="selectDevice('')"
          >
            <el-icon :size="14"><Monitor /></el-icon>
            <span>{{ t("log.device.all") }}</span>
          </div>
          <div
            v-for="dev in devices"
            :key="dev"
            class="sidebar-device-item"
            :class="{ active: filterDevice === dev }"
            @click="selectDevice(dev)"
          >
            <el-icon :size="14"><Connection /></el-icon>
            <span>{{ dev }}</span>
          </div>
        </div>
      </div>

      <!-- 右侧主内容区 -->
      <div class="log-main">
        <div class="log-filter-bar">
          <el-select
            v-model="filterModule"
            :placeholder="t('log.module.all')"
            class="filter-select"
            @change="handleModuleChange"
          >
            <el-option :label="t('log.module.all')" value="" />
            <el-option
              v-for="mod in modules"
              :key="mod"
              :label="t(`log.module.${mod}`)"
              :value="mod"
            />
          </el-select>

          <el-select
            v-model="filterLevel"
            :placeholder="t('log.levelFilter.all')"
            class="filter-select filter-level"
            @change="handleSearch"
          >
            <el-option :label="t('log.levelFilter.all')" value="" />
            <el-option v-for="lv in levels" :key="lv" :label="lv" :value="lv">
              <span class="level-option">
                <span
                  class="level-dot"
                  :style="{ background: levelTagTypeColor(lv) }"
                ></span>
                {{ lv }}
              </span>
            </el-option>
          </el-select>

          <el-input
            v-model="keyword"
            :placeholder="t('log.search')"
            class="filter-search"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-button :icon="Refresh" @click="handleSearch">
            {{ t("common.refresh") }}
          </el-button>

          <div class="auto-refresh-toggle">
            <el-switch v-model="autoRefresh" />
            <span class="toggle-label">{{ t("log.autoRefresh") }}</span>
          </div>
        </div>

        <div class="log-content" ref="logContentRef">
          <el-table
            :data="logs"
            stripe
            style="width: 100%"
            height="100%"
            size="small"
            :empty-text="t('log.empty')"
          >
            <el-table-column prop="time" :label="t('log.time')" width="200" />
            <el-table-column :label="t('log.levelCol')" width="90">
              <template #default="{ row }">
                <el-tag
                  v-if="row.level"
                  :type="levelTagType(row.level)"
                  size="small"
                  effect="light"
                >
                  {{ row.level }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="content"
              :label="t('log.content')"
              min-width="400"
            />
          </el-table>
        </div>

        <div class="log-footer">
          <span class="log-total">{{ t("log.total", { count: total }) }}</span>
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            layout="sizes, prev, pager, next, jumper"
            background
            @size-change="handleSizeChange"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";
import { Search, Refresh, Monitor, Connection } from "@element-plus/icons-vue";
import { getLogModules, getLogDevices, queryLogs } from "@/api/logApi";
import type { LogEntry } from "@/api/logApi";

const { t } = useI18n();

const props = defineProps<{
  visible: boolean;
}>();

const emit = defineEmits<{
  (e: "update:visible", val: boolean): void;
}>();

const visible = ref(props.visible);
watch(
  () => props.visible,
  (val) => {
    visible.value = val;
    if (val) {
      init();
    }
  },
);

// 筛选状态
const modules = ref<string[]>([]);
const devices = ref<string[]>([]);
const levels = ["DEBUG", "INFO", "WARNING", "ERROR"];
const filterModule = ref("");
const filterDevice = ref("");
const filterLevel = ref("");
const keyword = ref("");

// 日志等级 -> Element Plus tag type 映射
const levelTagTypeMap: Record<string, string> = {
  DEBUG: "info",
  INFO: "success",
  WARNING: "warning",
  ERROR: "danger",
};

function levelTagType(level: string): string {
  return levelTagTypeMap[level.toUpperCase()] || "info";
}

// 等级对应的颜色值（用于下拉选项中的圆点）
const levelDotColorMap: Record<string, string> = {
  DEBUG: "#909399",
  INFO: "#67C23A",
  WARNING: "#E6A23C",
  ERROR: "#F56C6C",
};

function levelTagTypeColor(level: string): string {
  return levelDotColorMap[level.toUpperCase()] || "#909399";
}

// 日志数据
const logs = ref<LogEntry[]>([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(100);

// 自动刷新
const autoRefresh = ref(true);
let refreshTimer: ReturnType<typeof setInterval> | null = null;

const logContentRef = ref<HTMLElement | null>(null);

async function init() {
  await Promise.all([loadModules(), loadDevices()]);
  await loadLogs();
  if (autoRefresh.value) {
    startAutoRefresh();
  }
}

async function loadModules() {
  try {
    const res = await getLogModules();
    modules.value = res.modules || [];
  } catch {
    // 静默失败
  }
}

async function loadDevices() {
  try {
    const res = await getLogDevices();
    devices.value = res.devices || [];
  } catch {
    // 静默失败
  }
}

async function loadLogs() {
  try {
    const res = await queryLogs({
      module: filterModule.value,
      device: filterDevice.value,
      level: filterLevel.value,
      offset: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
      keyword: keyword.value,
    });
    logs.value = res.logs || [];
    total.value = res.total || 0;
  } catch {
    // 静默失败
  }
}

function selectDevice(device: string) {
  filterDevice.value = device;
  currentPage.value = 1;
  loadLogs();
}

function handleModuleChange() {
  filterDevice.value = "";
  currentPage.value = 1;
  loadLogs();
}

function handleSearch() {
  currentPage.value = 1;
  loadLogs();
}

function handlePageChange(page: number) {
  currentPage.value = page;
  loadLogs();
}

function handleSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
  loadLogs();
}

function handleClose() {
  stopAutoRefresh();
  emit("update:visible", false);
}

// 自动刷新
watch(autoRefresh, (val) => {
  if (val) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

function startAutoRefresh() {
  stopAutoRefresh();
  refreshTimer = setInterval(() => {
    loadLogs();
  }, 5000);
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped lang="scss">
.log-viewer-dialog {
  :deep(.el-dialog__body) {
    padding: 16px 20px;
  }
}

.log-layout {
  display: flex;
  gap: 16px;
  height: 68vh;
  max-height: calc(90vh - 72px);
  min-height: 0;
  overflow: hidden;
}

// ===== Sidebar 样式 =====
.log-sidebar {
  width: 180px;
  flex-shrink: 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;

  .sidebar-header {
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    background-color: var(--el-fill-color-light);
    border-bottom: 1px solid var(--el-border-color-light);
    user-select: none;
  }

  .sidebar-device-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding-bottom: 4px;
  }

  .sidebar-device-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    font-size: 13px;
    color: var(--el-text-color-regular);
    cursor: pointer;
    transition: background-color 0.15s;
    user-select: none;

    &:hover {
      background-color: var(--el-fill-color-light);
    }

    &.active {
      color: var(--el-color-primary);
      background-color: var(--el-color-primary-light-9);
      font-weight: 500;
    }
  }
}

// ===== 主内容区样式 =====
.log-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.log-filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;

  .filter-select {
    width: 150px;
  }

  .filter-level {
    width: 130px;
  }

  .filter-search {
    width: 200px;
  }

  .auto-refresh-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;

    .toggle-label {
      font-size: 13px;
      color: var(--text-secondary);
      white-space: nowrap;
    }
  }
}

.log-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;

  :deep(.el-table th.el-table__cell) {
    background-color: var(--el-fill-color-light);
    font-weight: 600;
  }

  :deep(.el-table .cell) {
    font-family: "Consolas", "Monaco", monospace;
    font-size: 13px;
  }
}

.log-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;

  .log-total {
    font-size: 13px;
    color: var(--text-secondary);
  }
}

.level-option {
  display: flex;
  align-items: center;
  gap: 6px;
}

.level-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
