<template>
  <el-tabs v-model="activeName" type="card" class="tabs" @tab-click="handleClick">
    <el-tab-pane
      v-for="slave in slaveIdList"
      :key="slave"
      :label="`从机${slave}`"
      :name="slave.toString()"
    >
      <div class="search-bar">
        <el-input
          v-model="searchQuery[slave]"
          placeholder="请输入搜索内容"
          style="width: 200px; margin-right: 15px"
        />
        <el-button type="primary" @click="handleSearch(slave)">
          <el-icon style="vertical-align: middle">
            <Search />
          </el-icon>
          <span style="vertical-align: middle"> 搜索 </span>
        </el-button>
        <el-button class="custom-reset-btn" @click="resetPoint">
          <el-icon class="icon"><Refresh /></el-icon>
          <span style="text"> {{ "重置测点值" }} </span>
        </el-button>
      </div>
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
</template>

<script lang="ts" setup name="Slave">
import { ref, onMounted, watch, onUnmounted, computed } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, type TabsPaneContext } from "element-plus";
import { getSlaveIdList, getDeviceTable, resetPointData, getDeviceInfo } from "@/api/deviceApi";
import DeviceTable from "./Table.vue";

const route = useRoute();
const routeName = ref(route.name as string);
const activeName = ref("");
const slaveIdList = ref<number[]>([]);
const currentSlaveId = ref(1);
const tableDataMap = ref<{
  [key: number]: { tableHeader: string[]; tableData: any[][];};
}>({});
const searchQuery = ref<{ [key: number]: string }>({});
const pageSize = ref(10);
const pageIndex = ref(1);
const total = ref(0);
const activeFilters = ref<Record<string, number>>({});
const protocolType = ref<number>(1); // 默认 Modbus TCP
const pointTypes = computed<number[]>(() => {
  return Object.values(activeFilters.value).flat() as number[];
});

const handlePageIndexChange = (newPageIndex: number) => {
  pageIndex.value = newPageIndex;
};

const handlePageSizeChange = (newPageSize: number) => {
  pageSize.value = newPageSize;
};

const handleFilterChange = (filters: Record<string, number>) => {
  activeFilters.value = filters;
  const searchValue = searchQuery.value[currentSlaveId.value] || "";
  fetchDeviceTable(routeName.value, currentSlaveId.value, searchValue, pageIndex.value, pageSize.value);
};

const handleTableRefresh = () => {
  handleSearch(currentSlaveId.value);
};

// 从 localStorage 中恢复数据
const restoreData = () => {
  const savedSlaveIdList = localStorage.getItem("slaveIdList");
  const savedTableDataMap = localStorage.getItem("tableDataMap");

  if (savedSlaveIdList) {
    slaveIdList.value = JSON.parse(savedSlaveIdList);
  }
  if (savedTableDataMap) {
    tableDataMap.value = JSON.parse(savedTableDataMap);
  }
};

// 保存数据到 localStorage
const saveData = () => {
  localStorage.setItem("slaveIdList", JSON.stringify(slaveIdList.value));
  localStorage.setItem("tableDataMap", JSON.stringify(tableDataMap.value));
};

// 封装数据获取逻辑
const fetchSlaveList = async () => {
  // 先获取设备信息以获取协议类型
  try {
    const deviceInfo = await getDeviceInfo(routeName.value);
    protocolType.value = deviceInfo.get("type") ?? 1;
  } catch (e) {
    console.warn("获取设备协议类型失败，使用默认值");
  }
  
  slaveIdList.value = await getSlaveIdList(routeName.value);
  if (slaveIdList.value.length > 0) {
    currentSlaveId.value = slaveIdList.value[0];
    activeName.value = slaveIdList.value[0].toString(); // 设置默认激活的 Tab
    await fetchAllDeviceTables();
    saveData(); // 保存数据
  }
};

const fetchDeviceTable = async (
  deviceName: string,
  slaveId: number,
  pointName: string | null,
  pageIndex: number,
  pageSize: number
) => {
  const data = await getDeviceTable(deviceName, slaveId, pointName, pageIndex, pageSize, pointTypes.value);
  tableDataMap.value[slaveId] = {
    tableHeader: data.get("head_data"),
    tableData: data.get("table_data"),
  };
  total.value = data.get("total");
  // saveData(); // 保存数据
};

const fetchAllDeviceTables = async () => {
  for (const slave of slaveIdList.value) {
    await fetchDeviceTable(routeName.value, slave, null, pageIndex.value, pageSize.value);
  }
};

const handleClick = (tab: TabsPaneContext, event: Event) => {
  if (tab.index !== undefined) {
    const index = parseInt(tab.index);
    if (index >= 0 && index < slaveIdList.value.length) {
      currentSlaveId.value = slaveIdList.value[index];
      fetchDeviceTable(routeName.value, currentSlaveId.value, null, pageIndex.value, pageSize.value);
    }
  }
};

const handleSearch = (slave: number) => {
  // console.log(`搜索从机${slave}，关键字：${searchQuery.value[slave]}`);
  const searchValue = searchQuery.value[slave];
  if (searchValue) {
    fetchDeviceTable(routeName.value, slave, searchValue, pageIndex.value, pageSize.value);
  } else {
    fetchDeviceTable(routeName.value, slave, "", pageIndex.value, pageSize.value);
  }
};

const resetPoint = async () => {
  const isSucess = await resetPointData(routeName.value);
  if (isSucess) {
    handleSearch(currentSlaveId.value);
    ElMessage({
      message: "重置测点值成功!",
      type: "success",
    });
  } else {
    ElMessage({
      message: "重置测点值失败!",
      type: "error",
    });
  }
};

// 监听路由变化
watch(
  () => route.name,
  async (newRouteName) => {
    if (newRouteName) {
      routeName.value = newRouteName as string;
      await fetchSlaveList();
      pageIndex.value = 1;
      pageSize.value = 10;
    }
  }
);

// 根据模拟状态每秒刷新表格
const timer = ref<number | null>(null); // 修改这里
// 启动定时刷新
const startAutoRefresh = () => {
  if (timer.value !== null) return; // 避免重复启动

  timer.value = setInterval(() => {
    const searchValue = searchQuery.value[currentSlaveId.value] || "";
    fetchDeviceTable(routeName.value, currentSlaveId.value, searchValue, pageIndex.value, pageSize.value);
  }, 1000);
};

// 停止定时刷新
const stopAutoRefresh = () => {
  if (timer.value !== null) {
    clearInterval(timer.value);
    timer.value = null;
  }
};

// 组件挂载时启动定时刷新
onMounted(async () => {
  // restoreData(); // 恢复数据
  await fetchSlaveList();
  startAutoRefresh();
});

// 组件卸载时清理定时器
onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped>
/* 使用深度选择器穿透scoped限制 */
:deep(.custom-reset-btn) {
  background-color: #ff6d33 !important;
  border-color: #ff6d33 !important;
  color: white !important;
}
/* 处理悬停状态 */
:deep(.custom-reset-btn:hover) {
  background-color: #ff8d66 !important;
  border-color: #ff8d66 !important;
}
/* 处理点击状态 */
:deep(.custom-reset-btn:active) {
  background-color: #e65c2b !important;
  border-color: #e65c2b !important;
}

.tabs {
  margin-top: 20px;
  margin-right: 20px;
}
.tabs .el-tabs__content {
  color: #6b778c;
  font-size: 32px;
  font-weight: 600;
  margin-bottom: 0px;
}

.search-bar {
  margin-top: 0px;
  margin-bottom: 10px;
}
</style>
