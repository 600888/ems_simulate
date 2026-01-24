<template>
  <div class="slave-container">
    <el-tabs v-model="activeName" class="modern-tabs" @tab-click="handleClick">
      <el-tab-pane
        v-for="slave in slaveIdList"
        :key="slave"
        :label="`从机 ${slave}`"
        :name="slave.toString()"
      >
        <!-- 搜索与控制栏 -->
        <div class="search-bar">
          <div class="search-left">
            <el-input
              v-model="searchQuery[slave]"
              placeholder="搜索测点名称..."
              class="modern-input"
              clearable
              @keyup.enter="handleSearch(slave)"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button type="primary" class="modern-btn search-btn" @click="handleSearch(slave)">
              搜索
            </el-button>
            <el-button class="modern-btn reset-btn" @click="resetPoint" :icon="Refresh">
              重置测点值
            </el-button>
            <div class="auto-read-control">
              <span class="auto-read-label">自动读取</span>
              <el-switch
                v-model="isAutoRead"
                @change="handleAutoReadChange"
                active-color="#3b82f6"
                inactive-color="#94a3b8"
              />
              <el-button
                v-if="!isAutoRead"
                class="modern-btn manual-read-btn"
                @click="handleManualRead"
                :icon="Download"
              >
                手动读取
              </el-button>
            </div>
          </div>
        </div>

        <!-- 数据表格区域 -->
        <DeviceTable
          v-if="slave === currentSlaveId"
          :slaveId="slave"
          :tableHeader="tableDataMap[slave]?.tableHeader || []"
          :tableData="tableDataMap[slave]?.tableData || []"
          :pageSize="pageSize"
          :pageIndex="pageIndex"
          :total="total"
          :activeFilters="activeFilters"
          :protocolType="protocolType"
          @update:pageSize="handlePageSizeChange"
          @update:pageIndex="handlePageIndexChange"
          @update:activeFilters="handleFilterChange"
          @refresh="handleTableRefresh"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, watch, onUnmounted, computed } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, type TabsPaneContext } from "element-plus";
import { Search, Refresh, Download } from "@element-plus/icons-vue";
import { getSlaveIdList, getDeviceTable, resetPointData, getDeviceInfo, getAutoReadStatus, startAutoRead, stopAutoRead, manualRead } from "@/api/deviceApi";
import DeviceTable from "./Table.vue";

const route = useRoute();
const routeName = ref(route.name as string);
const activeName = ref("");
const slaveIdList = ref<number[]>([]);
const currentSlaveId = ref(1);
const tableDataMap = ref<Record<number, { tableHeader: string[]; tableData: any[][] }>>({});
const searchQuery = ref<Record<number, string>>({});
const pageSize = ref(10);
const pageIndex = ref(1);
const total = ref(0);
const activeFilters = ref<Record<string, number>>({});
const protocolType = ref<number | string>(1);
const isAutoRead = ref<boolean>(true);

const pointTypes = computed<number[]>(() => Object.values(activeFilters.value).flat() as number[]);

const handlePageIndexChange = (idx: number) => { pageIndex.value = idx; };
const handlePageSizeChange = (size: number) => { pageSize.value = size; };
const handleFilterChange = (filters: Record<string, number>) => {
  activeFilters.value = filters;
  fetchDeviceTable(routeName.value, currentSlaveId.value, searchQuery.value[currentSlaveId.value] || "", pageIndex.value, pageSize.value);
};
const handleTableRefresh = () => handleSearch(currentSlaveId.value);

const fetchSlaveList = async () => {
  try {
    const deviceInfo = await getDeviceInfo(routeName.value);
    if (deviceInfo) protocolType.value = deviceInfo.get("type") ?? 1;
  } catch (e) { console.warn("协议类型获取失败"); }
  
  slaveIdList.value = await getSlaveIdList(routeName.value);
  if (slaveIdList.value.length > 0) {
    currentSlaveId.value = slaveIdList.value[0];
    activeName.value = slaveIdList.value[0].toString();
    await fetchAllDeviceTables();
  }
};

const fetchDeviceTable = async (name: string, sid: number, q: string, pi: number, ps: number) => {
  const data = await getDeviceTable(name, sid, q, pi, ps, pointTypes.value);
  if (data) {
    tableDataMap.value[sid] = {
      tableHeader: data.get("head_data"),
      tableData: data.get("table_data"),
    };
    total.value = data.get("total");
  }
};

const fetchAllDeviceTables = async () => {
  for (const slave of slaveIdList.value) {
    await fetchDeviceTable(routeName.value, slave, "", pageIndex.value, pageSize.value);
  }
};

const handleClick = (tab: TabsPaneContext) => {
  if (tab.index !== undefined) {
    currentSlaveId.value = slaveIdList.value[parseInt(tab.index)];
    fetchDeviceTable(routeName.value, currentSlaveId.value, "", pageIndex.value, pageSize.value);
  }
};

const handleSearch = (slave: number) => {
  fetchDeviceTable(routeName.value, slave, searchQuery.value[slave] || "", pageIndex.value, pageSize.value);
};

const resetPoint = async () => {
  if (await resetPointData(routeName.value)) {
    ElMessage.success("重置成功");
    handleSearch(currentSlaveId.value);
  } else {
    ElMessage.error("重置失败");
  }
};

watch(() => route.name, async (newVal) => {
  if (newVal) {
    routeName.value = newVal as string;
    pageIndex.value = 1; pageSize.value = 10;
    await fetchSlaveList();
  }
});

const timer = ref<any>(null);
const startAutoRefresh = () => {
  if (timer.value) return;
  timer.value = setInterval(() => {
    fetchDeviceTable(routeName.value, currentSlaveId.value, searchQuery.value[currentSlaveId.value] || "", pageIndex.value, pageSize.value);
  }, 1000);
};

const stopAutoRefresh = () => {
  if (timer.value) {
    clearInterval(timer.value);
    timer.value = null;
  }
};

const handleAutoReadChange = async (enabled: boolean) => {
  if (enabled) {
    await startAutoRead(routeName.value);
    startAutoRefresh();
    ElMessage.success("已启用自动读取");
  } else {
    await stopAutoRead(routeName.value);
    stopAutoRefresh();
    ElMessage.success("已停止自动读取");
  }
};

const handleManualRead = async () => {
  const success = await manualRead(routeName.value);
  if (success) {
    await fetchDeviceTable(routeName.value, currentSlaveId.value, searchQuery.value[currentSlaveId.value] || "", pageIndex.value, pageSize.value);
    ElMessage.success("手动读取成功");
  } else {
    ElMessage.error("手动读取失败");
  }
};

const fetchAutoReadStatus = async () => {
  const status = await getAutoReadStatus(routeName.value);
  isAutoRead.value = status;
  if (status) {
    startAutoRefresh();
  }
};

onMounted(async () => {
  await fetchSlaveList();
  await fetchAutoReadStatus();
});
onUnmounted(() => { stopAutoRefresh(); });
</script>

<style lang="scss" scoped>
.slave-container {
  margin-top: 16px;
  background-color: var(--panel-bg);
  padding: 24px 20px 20px;
  border-radius: var(--border-radius-base);
  box-shadow: var(--box-shadow-base);
  border: 1px solid var(--sidebar-border);
}

.modern-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 24px;
    border: none !important;
    
    .el-tabs__nav-wrap {
      &::after { display: none !important; }
    }
    
    .el-tabs__nav {
      border: none !important;
      display: flex;
      gap: 12px;
    }
    
    .el-tabs__item {
      /* 定义确定无疑的四边线 */
      border-top: 1.5px solid var(--sidebar-border) !important;
      border-right: 1.5px solid var(--sidebar-border) !important;
      border-bottom: 1.5px solid var(--sidebar-border) !important;
      border-left: 1.5px solid var(--sidebar-border) !important;
      border-radius: 8px !important;
      color: var(--text-secondary);
      font-weight: 600;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      background: rgba(var(--color-primary-rgb, 59, 130, 246), 0.03);
      height: 38px;
      line-height: 35px;
      padding: 0 24px !important;
      box-sizing: border-box;
      box-shadow: none !important;
      outline: none !important;
      
      /* 清除可能干扰的伪元素 */
      &::before, &::after {
        display: none !important;
      }
      
      &.is-active {
        background: var(--color-primary) !important;
        color: white !important;
        /* 强制锁定激活态的每一条边线 */
        border-top: 1.5px solid var(--color-primary) !important;
        border-right: 1.5px solid var(--color-primary) !important;
        border-bottom: 1.5px solid var(--color-primary) !important;
        border-left: 1.5px solid var(--color-primary) !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25) !important;
        /* 移除上移动画，避免上边线被遮挡 */
        transform: none;
      }
      
      &:hover:not(.is-active) {
        color: var(--color-primary);
        border-top: 1.5px solid var(--color-primary) !important;
        border-right: 1.5px solid var(--color-primary) !important;
        border-bottom: 1.5px solid var(--color-primary) !important;
        border-left: 1.5px solid var(--color-primary) !important;
        background: var(--item-hover-bg);
      }

      &.is-focus {
        box-shadow: none !important;
      }
    }
    
    .el-tabs__active-bar {
      display: none !important;
    }
  }
}

.search-bar {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
}

.search-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.modern-btn {
  height: 34px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 0.3s;
  
  &.search-btn { padding: 0 20px; }
  &.reset-btn {
    background-color: var(--color-warning);
    color: white;
    border: none;
    &:hover { background-color: #d97706; transform: translateY(-1px); }
  }
  &.manual-read-btn {
    background-color: var(--color-success, #10b981);
    color: white;
    border: none;
    padding: 0 16px;
    &:hover { background-color: #059669; transform: translateY(-1px); }
  }
  &:hover { transform: translateY(-1px); opacity: 0.9; }
}

.auto-read-control {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 8px;
  padding-left: 16px;
  border-left: 1px solid var(--sidebar-border);
  height: 34px;
}

.auto-read-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}
</style>
