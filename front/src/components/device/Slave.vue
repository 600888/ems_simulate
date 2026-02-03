<template>
  <div class="slave-container">
    <el-tabs v-model="activeName" class="modern-tabs" @tab-click="handleClick" :before-leave="beforeLeave">
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
            <el-button class="modern-btn add-btn" @click="showAddPointDialog = true" :icon="Plus">
              添加测点
            </el-button>
            <el-popconfirm
              title="确定清空当前从机的所有测点吗？此操作不可恢复！"
              confirm-button-text="确定"
              cancel-button-text="取消"
              @confirm="handleClearPoints"
            >
              <template #reference>
                <el-button class="modern-btn clear-btn" type="danger" :icon="Delete">
                  清空测点
                </el-button>
              </template>
            </el-popconfirm>
            <div v-if="needsAutoReadControls" class="auto-read-control">
              <span class="auto-read-label">自动读取</span>
              <el-switch
                v-model="isAutoRead"
                @change="handleAutoReadChange"
                active-color="#3b82f6"
                inactive-color="#94a3b8"
              />
              <span class="auto-read-label">间隔(ms)</span>
              <el-select
                v-model="readInterval"
                placeholder="间隔"
                allow-create
                filterable
                default-first-option
                style="width: 100px; margin-right: 12px;"
                @change="handleIntervalChange"
              >
                <el-option
                  v-for="item in intervalOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <el-button
                v-if="!isAutoRead"
                :type="isReading ? 'danger' : 'primary'"
                class="modern-btn"
                :class="isReading ? 'cancel-read-btn' : 'manual-read-btn'"
                @click="handleManualRead"
                :icon="isReading ? CircleCloseFilled : Download"
              >
                {{ isReading ? '取消读取' : '手动读取' }}
              </el-button>
            </div>
          </div>
        </div>

        <!-- 进度条区域 -->
        <div v-if="readProgress > 0" class="progress-container">
          <div class="progress-info">
            <span class="progress-text">{{ progressMessage }}</span>
            <span class="progress-percentage">{{ readProgress }}%</span>
          </div>
          <el-progress 
            :percentage="readProgress" 
            :format="formatProgress"
            :stroke-width="10"
            color="#3b82f6"
            striped
            striped-flow
          />
        </div>

        <!-- 数据表格区域 -->
        <DeviceTable
          v-if="slave === currentSlaveId"
          :slaveId="slave"
          :tableHeader="tableDataMap[slave]?.tableHeader || []"
          :tableData="tableDataMap[slave]?.tableData || []"
          :pageSize="pageSize"
          :pageIndex="pageIndex"
          :total="tableDataMap[slave]?.total || 0"
          :activeFilters="activeFilters"
          :protocolType="protocolType"
          @update:pageSize="handlePageSizeChange"
          @update:pageIndex="handlePageIndexChange"
          @update:activeFilters="handleFilterChange"
          @refresh="handleTableRefresh"
        />
      </el-tab-pane>
      
      <!-- 添加从机按钮（作为特殊 tab） -->
      <el-tab-pane name="add" :closable="false">
        <template #label>
          <span class="add-slave-tab">
            <el-icon><Plus /></el-icon>
            添加从机
          </span>
        </template>
      </el-tab-pane>
    </el-tabs>
    
    <!-- 添加测点对话框 -->
    <AddPointDialog
      v-model="showAddPointDialog"
      :deviceName="routeName"
      :slaveIdList="slaveIdList"
      :currentSlaveId="currentSlaveId"
      @success="handlePointAdded"
    />
    
    <!-- 添加从机对话框 -->
    <AddSlaveDialog
      v-model="showAddSlaveDialog"
      :deviceName="routeName"
      :existingSlaves="slaveIdList"
      @success="handleSlaveAdded"
    />
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, watch, onUnmounted, computed } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, type TabsPaneContext } from "element-plus";
import { Search, Refresh, Download, Plus, Delete, CircleCloseFilled } from "@element-plus/icons-vue";
import { getSlaveIdList, getDeviceTable, resetPointData, getDeviceInfo, getAutoReadStatus, startAutoRead, stopAutoRead, manualRead, clearPoints, readSinglePoint, instance } from "@/api/deviceApi";
import DeviceTable from "./Table.vue";
import AddPointDialog from "./AddPointDialog.vue";
import AddSlaveDialog from "./AddSlaveDialog.vue";

const route = useRoute();
const routeName = ref(route.params.deviceName as string);
const activeName = ref("");
const slaveIdList = ref<number[]>([]);
const currentSlaveId = ref(1);
const tableDataMap = ref<Record<number, { tableHeader: string[]; tableData: any[][]; total: number }>>({});
const searchQuery = ref<Record<number, string>>({});
const pageSize = ref(10);
const pageIndex = ref(1);
const total = ref(0);
const activeFilters = ref<Record<string, number>>({});
const protocolType = ref<number | string>(1);
const connType = ref<number>(2); // 默认为服务端
const isAutoRead = ref<boolean>(false);

// 判断是否需要显示自动读取控件 
// Modbus 客户端/主站 (conn_type 0 或 1) 需要主动轮询，需要显示
// IEC104 客户端虽然是 conn_type=1，但数据是服务端推送的，不需要显示
// 注：表格每秒刷新对所有设备都生效，这里只控制自动读取按钮的显示
const needsAutoReadControls = computed(() => {
  // IEC104 协议类型不需要自动读取控件（数据由服务端推送）
  const protocolStr = String(protocolType.value);
  if (protocolStr === 'Iec104Client' || protocolStr === 'Iec104Server') {
    return false;
  }
  // 只有客户端/主站模式 (conn_type 0 或 1) 显示自动读取控件
  return connType.value === 0 || connType.value === 1;
});
const showAddPointDialog = ref<boolean>(false);
const showAddSlaveDialog = ref<boolean>(false);

const pointTypes = computed<number[]>(() => Object.values(activeFilters.value).flat() as number[]);

const handlePageIndexChange = (idx: number) => { 
  pageIndex.value = idx; 
  handleSearch(currentSlaveId.value);
};
const handlePageSizeChange = (size: number) => { 
  pageSize.value = size; 
  handleSearch(currentSlaveId.value);
};
const handleFilterChange = (filters: Record<string, number>) => {
  activeFilters.value = filters;
  fetchDeviceTable(routeName.value, currentSlaveId.value, searchQuery.value[currentSlaveId.value] || "", pageIndex.value, pageSize.value);
};
const handleTableRefresh = () => handleSearch(currentSlaveId.value);

const fetchSlaveList = async () => {
  try {
    const deviceInfo = await getDeviceInfo(routeName.value);
    if (deviceInfo) {
      protocolType.value = deviceInfo.get("type") ?? 1;
      // 确保 conn_type 是数字类型
      connType.value = Number(deviceInfo.get("conn_type") ?? 2);
    }
  } catch (e) { console.warn("设备信息获取失败"); }
  
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
    // 确保初始化对象
    if (!tableDataMap.value[sid]) {
      tableDataMap.value[sid] = { tableHeader: [], tableData: [], total: 0 };
    }
    
    tableDataMap.value[sid] = {
      tableHeader: data.get("head_data"),
      tableData: data.get("table_data"),
      total: data.get("total"),
    };
    
    // 如果是当前显示的从机，同时更新全局 total 以防万一（但我们将主要改为从 map 中取值）
    if (sid === currentSlaveId.value) {
      total.value = data.get("total");
    }
  }
};

const fetchAllDeviceTables = async () => {
  for (const slave of slaveIdList.value) {
    await fetchDeviceTable(routeName.value, slave, "", pageIndex.value, pageSize.value);
  }
};

// 阻止切换到 "add" tab
const beforeLeave = (activeName: string, oldActiveName: string) => {
  if (activeName === "add") {
    showAddSlaveDialog.value = true;
    return false; // 阻止切换
  }
  return true;
};

const handleClick = (tab: TabsPaneContext) => {
  if (tab.paneName === "add") {
    return; // beforeLeave 已处理
  }
  
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

const handleClearPoints = async () => {
  const deletedCount = await clearPoints(routeName.value, currentSlaveId.value);
  if (deletedCount >= 0) {
    ElMessage.success(`清空成功，共删除 ${deletedCount} 个测点`);
    handleSearch(currentSlaveId.value);
  } else {
    ElMessage.error("清空测点失败");
  }
};

// Watch for route param changes


watch(() => route.fullPath, async () => {
    // 强制刷新：当 query 参数变化（如添加了 t=timestamp）或路径变化时触发
    if (route.params.deviceName) {
      if (routeName.value !== route.params.deviceName) {
          stopAutoRefresh();
          routeName.value = route.params.deviceName as string;
          pageIndex.value = 1; 
          pageSize.value = 10;
          isAutoRead.value = false;
          await stopAutoRead(routeName.value);
          await fetchSlaveList();
          startAutoRefresh();
      } else {
        // 同一设备，仅刷新数据
        handleSearch(currentSlaveId.value);
      }
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
    ElMessage.success("已启用自动读取");
  } else {
    await stopAutoRead(routeName.value);
    ElMessage.success("已停止自动读取");
  }
};

const isReading = ref(false);
const cancelRead = ref(false);
const readInterval = ref(100);
const intervalOptions = ref([
  { label: '10ms', value: 10 },
  { label: '50ms', value: 50 },
  { label: '100ms', value: 100 },
  { label: '200ms', value: 200 },
  { label: '500ms', value: 500 },
  { label: '1000ms', value: 1000 },
  { label: '2000ms', value: 2000 },
  { label: '5000ms', value: 5000 },
]);

const handleIntervalChange = (val: string | number) => {
  const numVal = Number(val);
  if (!isNaN(numVal) && numVal > 0) {
    const exists = intervalOptions.value.some(opt => opt.value === numVal);
    if (!exists) {
      intervalOptions.value.push({
        label: `${numVal}ms`,
        value: numVal
      });
      // Sort options optional, but good for UX? Maybe not needed if user just wants it added.
      intervalOptions.value.sort((a, b) => a.value - b.value);
    }
    readInterval.value = numVal;
  }
};

const handleManualRead = async () => {
  if (isReading.value) {
    cancelRead.value = true;
    return;
  }

  isReading.value = true;
  cancelRead.value = false;
  readProgress.value = 0;
  progressMessage.value = "正在获取测点列表...";

  try {
    // 1. 获取所有测点 (使用较大的 pageSize)
    const data = await getDeviceTable(routeName.value, currentSlaveId.value, "", 1, 10000, pointTypes.value);
    const allRows = data.get("table_data") || [];
    const totalPoints = allRows.length;

    if (totalPoints === 0) {
      ElMessage.warning("当前从机没有测点");
      isReading.value = false;
      return;
    }

    progressMessage.value = "开始读取...";
    
    // 2. 循环读取
    for (let i = 0; i < totalPoints; i++) {
      if (cancelRead.value) {
        progressMessage.value = "读取已取消";
        ElMessage.warning("操作已取消");
        break;
      }

      const row = allRows[i];
      const pointCode = row[6]; // 测点编码在第7列 (索引6)
      const pointName = row[5];
      
      progressMessage.value = `正在读取 [${i + 1}/${totalPoints}]: ${pointName}`;
      
      try {
        const value = await readSinglePoint(routeName.value, pointCode);
        
        if (value !== null) {   
          if (tableDataMap.value[currentSlaveId.value]) {
             const currentTableData = tableDataMap.value[currentSlaveId.value].tableData;
             const displayRow = currentTableData.find(r => r[6] === pointCode);
             if (displayRow) {
               displayRow[8] = value; // 真实值
               displayRow[12] = "成功"; // 状态
               // 暂时无法更新寄存器值(row[7])因为 readSinglePoint 只返回真实值
               // 如果需要寄存器值，可能需要后端接口支持返回更多信息
             }
          }
        }
      } catch (e) {
        console.warn(`读取测点 ${pointCode} 失败`);
      }

      if (readInterval.value > 0) {
        await new Promise(resolve => setTimeout(resolve, readInterval.value));
      }

      readProgress.value = Math.floor(((i + 1) / totalPoints) * 100);
    }
    
    if (!cancelRead.value) {
      progressMessage.value = "读取完成";
      ElMessage.success("读取完成");
    }

  } catch (e) {
    console.error(e);
    ElMessage.error("手动读取过程中出错");
  } finally {
    if (cancelRead.value) {
       // If cancelled, reset immediately
       isReading.value = false;
       readProgress.value = 0;
    } else {
       // If finished normally, show 100% for a moment
       setTimeout(() => {
           isReading.value = false;
           readProgress.value = 0;
       }, 1000);
    }
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
  // 获取当前自动读取状态
  await fetchAutoReadStatus();
  // 始终开启表格刷新以支持主动上报协议的数据显示
  startAutoRefresh();
  
  // 连接 WebSocket
  // connectWebSocket();
});


const readProgress = ref(0);
const progressMessage = ref("");
let websocket: WebSocket | null = null;
let wsReconnectTimer: any = null;

// import { instance } from "@/api/deviceApi"; // Moved to top

const connectWebSocket = () => {
    if (websocket) return;

    // 获取 baseURL
    let baseURL = instance.defaults.baseURL || '/';
    if (baseURL.startsWith('/')) {
        // 如果是相对路径，拼接到当前 host
        baseURL = window.location.origin + baseURL;
    }

    // 替换 http/https 为 ws/wss
    const wsBase = baseURL.replace(/^http/, 'ws');
    // 去除末尾斜杠
    const wsUrl = `${wsBase.replace(/\/$/, '')}/device/ws/${routeName.value}`; 
    
    console.log("Connecting to WebSocket:", wsUrl); // Debug log
    
    websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
        console.log("WebSocket connected");
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
    };

    websocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'progress') {
                readProgress.value = data.progress;
                progressMessage.value = data.message;
                
                // 实时刷新表格数据
                // 收到进度更新说明有新数据被读取，立即刷新当前显示的表格
                handleSearch(currentSlaveId.value);
                
                if (data.progress >= 100) {
                    setTimeout(() => {
                        readProgress.value = 0;
                        progressMessage.value = "";
                    }, 2000);
                }
            }
        } catch (e) {
            console.error("WebSocket message error:", e);
        }
    };

    websocket.onclose = () => {
        console.log("WebSocket disconnected");
        websocket = null;
        // 尝试重连
        wsReconnectTimer = setTimeout(() => {
            connectWebSocket();
        }, 3000);
    };
    
    websocket.onerror = (err) => {
         console.error("WebSocket error:", err);
         websocket?.close();
    };
};

const formatProgress = (percentage: number) => {
    return percentage === 100 ? '完成' : `${percentage}%`;
};

const handlePointAdded = () => {
  fetchDeviceTable(routeName.value, currentSlaveId.value, searchQuery.value[currentSlaveId.value] || "", pageIndex.value, pageSize.value);
};

const handleSlaveAdded = async () => {
  await fetchSlaveList();
};

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

.add-slave-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #8b5cf6;
  font-weight: 600;
  
  .el-icon {
    font-size: 14px;
  }
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
  &.cancel-read-btn {
    background-color: var(--el-color-danger, #f56c6c);
    color: white;
    border: none;
    padding: 0 16px;
    &:hover { background-color: #f78989; transform: translateY(-1px); }
  }
  &.add-btn {
    background-color: #6366f1;
    color: white;
    border: none;
    &:hover { background-color: #4f46e5; transform: translateY(-1px); }
  }
  &.add-slave-btn {
    background-color: #8b5cf6;
    color: white;
    border: none;
    &:hover { background-color: #7c3aed; transform: translateY(-1px); }
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

.progress-container {
  margin-bottom: 20px;
  padding: 0 10px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.progress-percentage {
  font-weight: 600;
  color: var(--color-primary);
}
</style>
