<template>
  <el-col class="device-container">
    <!-- 第一行：设备基本通讯信息 -->
    <el-row class="nodes" :span="24">
      <TextNode v-if="!isSerialMode" label="服务器地址" :name="ip" />
      <TextNode v-if="!isSerialMode" label="端口号" :name="String(port)" />
      <TextNode v-if="isSerialMode" label="串口号" :name="serialPort || '-'" />
      <TextNode v-if="isSerialMode" label="波特率" :name="String(baudrate)" />
      <TextNode label="通讯类型" :name="communicationType" />
      <TextNode label="设备状态" :name="deviceStatusStr" :status="deviceStatus" />
      
      <el-button
        :class="['button', deviceStatus ? 'btn-stop' : 'btn-primary-action']"
        @click="toggleDevice"
        :disabled="isDeviceProcessing"
        :loading="isDeviceProcessing"
      >
        <template #icon v-if="!isDeviceProcessing">
          <el-icon v-if="!deviceStatus" class="icon"><CaretRight /></el-icon>
          <el-icon v-else class="icon"><VideoPause /></el-icon>
        </template>
        <span> {{ deviceButtonText }} </span>
      </el-button>
      
      <el-button
        class="button btn-info"
        @click="showMessageDialog = true"
      >
        <el-icon class="icon"><Document /></el-icon>
        <span>查看报文</span>
      </el-button>
      <el-button
        v-if="isIec61850Client"
        class="button btn-export"
        @click="showExportDialog = true"
        :disabled="!deviceStatus"
      >
        <el-icon class="icon"><Download /></el-icon>
        <span>导出模型</span>
      </el-button>
    </el-row>

    <!-- 第二行：仿真模拟控制 -->
    <el-row class="nodes" :span="24">
      <TextNode label="模拟状态" :name="simulationStatusStr" :status="simulationStatus" />
      <el-select
        v-model="currentSimulateMethod"
        placeholder="模拟方式选择"
        size="large"
        class="simulation-select"
        :disabled="isClientDevice"
      >
        <el-option
          v-for="item in simulateOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-tooltip :content="isClientDevice ? '客户端设备不支持数据模拟' : ''" :disabled="!isClientDevice" placement="top">
        <span class="tooltip-wrapper">
          <el-button
            :class="['button', simulationStatus ? 'btn-stop' : 'btn-start']"
            @click="startFunction"
            :disabled="isSimProcessing || !deviceStatus || isClientDevice"
            :style="isClientDevice ? { opacity: 0.6, cursor: 'not-allowed' } : {}"
            :loading="isSimProcessing"
          >
            <template #icon v-if="!isSimProcessing">
              <el-icon v-if="!simulationStatus" class="icon"><CaretRight /></el-icon>
              <el-icon v-else class="icon"><VideoPause /></el-icon>
            </template>
            <span> {{ buttonText }} </span>
          </el-button>
        </span>
      </el-tooltip>
    </el-row>

    <!-- 第三行：从站/测点数据 -->
    <!-- IEC61850 连接进度条 -->
    <el-row v-if="iec61850Connecting" class="nodes progress-row" :span="24">
      <el-progress
        :percentage="iec61850ProgressPercent"
        :stroke-width="20"
        :text-inside="true"
        :format="() => iec61850PhaseText"
        striped
        striped-flow
        style="width: 100%"
      />
    </el-row>
    <Slave ref="slaveRef" />
    
    <!-- 报文查看对话框 -->
    <MessageViewDialog
      v-model="showMessageDialog"
      :device-name="routeName"
    />

    <!-- 模型导出对话框 -->
    <ModelExportDialog
      v-model="showExportDialog"
      :device-name="routeName"
    />
  </el-col>
</template>

<script lang="ts" setup>
import { ref, onMounted, onUnmounted, computed, watch, onActivated, onDeactivated } from "vue";
import { useRoute } from "vue-router";
import TextNode from "@/components/common/TextNode.vue";
import Slave from "@/components/device/Slave.vue";
import MessageViewDialog from "@/components/device/MessageViewDialog.vue";
import ModelExportDialog from "@/components/device/ModelExportDialog.vue";
import {
  getDeviceInfo,
  startSimulation,
  stopSimulation,
  startDevice,
  stopDevice,
  getIEC61850ConnectProgress,
} from "@/api/deviceApi";
import type { IEC61850ConnectProgress } from "@/api/deviceApi";
import { triggerSidebarRefresh } from "@/composables";
import { CaretRight, VideoPause, Document, Download } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const route = useRoute();

const getDeviceNameFromRoute = () => {
  return (route.params.deviceName as string) || '';
};

// 记录组件创建时的初始设备名，避免被其他页面的路由变化触发
const initialDeviceName = getDeviceNameFromRoute();
const routeName = ref(initialDeviceName);
const deviceInfo = ref(new Map<string, any>());
const ip = ref<any>("");
const port = ref<any>("");
const serialPort = ref<string | null>(null);
const baudrate = ref<number>(9600);
const communicationType = ref<any>("");
const deviceStatus = ref<boolean>(false);
const deviceStatusStr = ref<any>("");
const simulationStatus = ref<boolean>(false);
const simulationStatusStr = ref<any>("");
const showMessageDialog = ref<boolean>(false);
const showExportDialog = ref<boolean>(false);
const slaveRef = ref<any>(null);

const isSerialMode = computed(() => {
  const type = communicationType.value;
  return type && (type.includes('Dlt645') || type.startsWith('ModbusRtu')) && serialPort.value;
});

const isClientDevice = computed(() => {
  const type = communicationType.value;
  // 检查是否为客户端类型 (包含 Client 且不包含 Server)
  // ModbusTcpClient, Iec104Client, Dlt645Client
  return String(type).includes('Client');
});

const simulateOptions = [
  { value: "Random", label: "随机模拟" },
  { value: "AutoIncrement", label: "自增模拟" },
  { value: "AutoDecrement", label: "自减模拟" },
  { value: "SineWave", label: "正弦波模拟" },
  { value: "Ramp", label: "斜坡模拟" },
  { value: "Pulse", label: "脉冲模拟" },
];
const currentSimulateMethod = ref<string>(simulateOptions[0].value);

const deviceButtonText = computed(() => deviceStatus.value ? "停止设备" : "开启设备");
const buttonText = computed(() => simulationStatus.value ? "停止" : "开始");

const isDeviceProcessing = ref<boolean>(false);
const isSimProcessing = ref<boolean>(false);

// IEC61850 连接进度
const iec61850Connecting = ref(false);
const iec61850ConnectProgress = ref<IEC61850ConnectProgress | null>(null);
const iec61850PhaseLabel: Record<string, string> = {
  idle: '准备中...',
  connecting: '正在连接服务器...',
  discovering: '正在发现数据模型...',
  done: '连接完成',
  failed: '连接失败',
};

const isIec61850Client = computed(() => {
  return communicationType.value && String(communicationType.value) === 'Iec61850Client';
});

const iec61850ProgressPercent = computed(() => {
  if (!iec61850ConnectProgress.value) return 0;
  return iec61850ConnectProgress.value.progress || 0;
});

const iec61850PhaseText = computed(() => {
  if (!iec61850ConnectProgress.value) return '';
  return iec61850PhaseLabel[iec61850ConnectProgress.value.phase] || '';
});

let iec61850ProgressTimer: number | null = null;

const startIec61850ProgressPolling = () => {
  stopIec61850ProgressPolling();
  iec61850Connecting.value = true;
  iec61850ConnectProgress.value = null;
  iec61850ProgressTimer = window.setInterval(async () => {
    const progress = await getIEC61850ConnectProgress(routeName.value);
    if (progress) {
      iec61850ConnectProgress.value = progress;
      if (progress.phase === 'done' || progress.phase === 'failed') {
        stopIec61850ProgressPolling();
        if (progress.phase === 'done') {
          deviceStatus.value = true;
          deviceStatusStr.value = '运行中';
          ElMessage.success('IEC 61850 设备连接成功');
          slaveRef.value?.reloadDatas();
          triggerSidebarRefresh(routeName.value);
        } else {
          ElMessage.error('IEC 61850 设备连接失败');
        }
      }
    }
  }, 500);
};

const stopIec61850ProgressPolling = () => {
  if (iec61850ProgressTimer) {
    clearInterval(iec61850ProgressTimer);
    iec61850ProgressTimer = null;
  }
  iec61850Connecting.value = false;
};

const toggleDevice = async () => {
  isDeviceProcessing.value = true;
  try {
    if (deviceStatus.value) {
      if (await stopDevice(routeName.value)) {
        deviceStatus.value = false;
        deviceStatusStr.value = "停止";
        if (simulationStatus.value) {
          // 设备停止时，仿真自动停止，但不触发仿真按钮的loading
          simulationStatus.value = false;
          simulationStatusStr.value = "停止";
        }
      } else {
        ElMessage.error("停止设备失败");
      }
    } else {
      if (await startDevice(routeName.value)) {
        if (isIec61850Client.value) {
          // IEC61850: 后台连接中，启动进度轮询
          deviceStatusStr.value = "连接中";
          startIec61850ProgressPolling();
        } else {
          deviceStatus.value = true;
          deviceStatusStr.value = "运行中";
          ElMessage.success("启动设备成功");
        }
      } else {
        ElMessage.error("启动设备失败");
      }
    }
  } catch (error: any) {
    console.error(error);
    // error message is handled by global interceptor
  }
  finally { isDeviceProcessing.value = false; }
};

const fetchDeviceInfo = async () => {
  try {
    const info = await getDeviceInfo(routeName.value);
    deviceInfo.value = info;
    ip.value = info.get("ip") || null;
    port.value = info.get("port") || null;
    serialPort.value = info.get("serial_port") || null;
    baudrate.value = info.get("baudrate") || 9600;
    communicationType.value = info.get("type") || null;
    const serverStatus = info.get("server_status");
    deviceStatus.value = serverStatus;
    deviceStatusStr.value = serverStatus === true ? "运行中" : "停止";
    // 初始化防抖状态，避免初始加载时误弹通知
    lastNotifyServerStatus = serverStatus;
    stableServerStatus = serverStatus;
    prevServerStatus = serverStatus;
    statusUnstableCount = STATUS_STABLE_THRESHOLD;
    const simuStatus = info.get("simulation_status");
    simulationStatus.value = simuStatus;
    simulationStatusStr.value = simuStatus === true ? "运行中" : "停止";

    // IEC61850 客户端：如果设备未运行，检查是否正在后台连接中
    if (!serverStatus && String(communicationType.value) === 'Iec61850Client') {
      const progress = await getIEC61850ConnectProgress(routeName.value);
      if (progress && progress.connecting) {
        // 正在连接中，启动进度轮询
        iec61850Connecting.value = true;
        deviceStatusStr.value = '连接中';
        iec61850ConnectProgress.value = progress;
        startIec61850ProgressPolling();
      }
    }
  } catch (error: any) { 
    console.error(error); 
    // error message is handled by global interceptor
  }
};

const startFunction = async () => {
  isSimProcessing.value = true;
  try {
    if (simulationStatus.value) {
      if (await stopSimulation(routeName.value)) {
        simulationStatus.value = false;
        simulationStatusStr.value = "停止";
      }
    } else {
      if (await startSimulation(routeName.value, currentSimulateMethod.value)) {
        simulationStatus.value = true;
        simulationStatusStr.value = "运行中";
      }
    }
  } catch (error) { console.error(error); }
  finally { isSimProcessing.value = false; }
};

// 状态轮询定时器
let statusPollTimer: number | null = null;
const STATUS_POLL_INTERVAL = 1000; // 1秒轮询一次

// 连接状态防抖：避免因连接状态抖动（如客户端重连过程中反复连接成功又断开）导致不停弹窗
let lastNotifyServerStatus: boolean | null = null;  // 上一次弹窗通知时的连接状态
let stableServerStatus: boolean | null = null;       // 当前稳定的连接状态
let statusUnstableCount = 0;                          // 状态不稳定计数（连续变化的次数）
const STATUS_STABLE_THRESHOLD = 3;                    // 连续3次状态一致才认为状态稳定
let prevServerStatus: boolean | null = null;          // 上一次轮询的连接状态（用于检测即时变化，如 IEC 61850 测点刷新）

// 仅获取状态（不更新其他信息，减少开销）
const fetchDeviceStatus = async () => {
  try {
    const info = await getDeviceInfo(routeName.value);
    const serverStatus = info.get("server_status");

    // 更新显示状态（不受防抖影响，UI 始终反映最新值）
    // IEC61850 连接中时，不覆盖"连接中"状态（后端 is_running 在连接完成前为 false）
    if (iec61850Connecting.value) {
      // 连接完成后才更新设备状态
      if (serverStatus === true) {
        deviceStatus.value = true;
        deviceStatusStr.value = "运行中";
      }
    } else {
      deviceStatus.value = serverStatus;
      deviceStatusStr.value = serverStatus === true ? "运行中" : "停止";
    }

    // IEC 61850 客户端：检测到连接从 false 变为 true 时立即刷新测点表格
    // （不需要等防抖，因为测点发现完成后数据立即可用）
    if (serverStatus === true && prevServerStatus === false) {
      if (communicationType.value && String(communicationType.value) === "Iec61850Client") {
        slaveRef.value?.reloadDatas();
        stopIec61850ProgressPolling();
        triggerSidebarRefresh(routeName.value);
      }
    }
    // 注意：不在 serverStatus === false 时停止进度轮询
    // 因为 IEC61850 后台连接期间 is_running 仍为 false，这属于正常状态
    // 进度轮询会通过 getIEC61850ConnectProgress 的 phase 自动判断完成或失败
    prevServerStatus = serverStatus;

    // 防抖逻辑：只有状态稳定后才弹出通知
    if (serverStatus !== stableServerStatus) {
      // 状态发生变化，开始计数
      statusUnstableCount = 1;
      stableServerStatus = serverStatus;
    } else {
      // 状态未变化，累加计数
      statusUnstableCount++;
    }

    // 状态已稳定（连续 N 次一致），且与上次通知状态不同时才弹窗
    if (statusUnstableCount >= STATUS_STABLE_THRESHOLD && lastNotifyServerStatus !== serverStatus) {
      lastNotifyServerStatus = serverStatus;
      if (serverStatus === true) {
        ElMessage.success(`设备 ${routeName.value} 已连接`);
      } else {
        ElMessage.warning(`设备 ${routeName.value} 连接已断开`);
      }
    }

    const simuStatus = info.get("simulation_status");
    if (simulationStatus.value !== simuStatus) {
      simulationStatus.value = simuStatus;
      simulationStatusStr.value = simuStatus === true ? "运行中" : "停止";
      // 模拟状态变化提示
      if (simuStatus === true) {
        ElMessage.info(`设备 ${routeName.value} 模拟已启动`);
      } else {
        ElMessage.info(`设备 ${routeName.value} 模拟已停止`);
      }
    }
  } catch (error) { /* 静默处理轮询错误 */ }
};

// 启动状态轮询
const startStatusPolling = () => {
  if (statusPollTimer) return;
  statusPollTimer = window.setInterval(fetchDeviceStatus, STATUS_POLL_INTERVAL);
};

// 停止状态轮询
const stopStatusPolling = () => {
  if (statusPollTimer) {
    clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
};

onMounted(() => {
  // fetchDeviceInfo(); // 交给 watcher 处理，避免重复或时序问题
});

onActivated(() => {
  startStatusPolling();
});

onDeactivated(() => {
  stopStatusPolling();
});

onUnmounted(() => {
  stopStatusPolling();
  stopIec61850ProgressPolling();
});

watch(() => route.fullPath, async () => {
  const newName = getDeviceNameFromRoute();
  
  if (newName && newName === initialDeviceName) {
    if (routeName.value !== newName) {
      routeName.value = newName;
      // 重置数据
      deviceInfo.value = new Map<string, any>();
      // 重置连接状态防抖
      lastNotifyServerStatus = null;
      stableServerStatus = null;
      prevServerStatus = null;
      statusUnstableCount = 0;
    }
    await fetchDeviceInfo();
  }
}, { immediate: true });
</script>

<style lang="scss" scoped>
.device-container {
  padding: 16px 20px;
  background-color: var(--bg-main);
  min-height: 100%;
}

.nodes {
  display: flex;
  flex-direction: row;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
  align-items: center;
  background-color: var(--panel-bg);
  padding: 12px 20px;
  border-radius: var(--border-radius-base);
  box-shadow: var(--box-shadow-base);
  border: 1px solid var(--sidebar-border);
  transition: all 0.3s ease;
}

.button {
  margin: 0;
  min-width: 110px;
  height: 42px;
  border-radius: 10px;
  font-weight: 600;
  border: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: #ffffff;
  
  &:hover {
    transform: translateY(-2px);
    filter: brightness(1.1);
  }

  .icon {
    font-size: 18px;
    margin-right: 6px;
  }
}

.btn-stop {
  background-color: var(--color-danger);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.25);
}

.btn-start {
  background-color: var(--color-success);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
}

.btn-primary-action {
  background-color: var(--color-primary);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
}

.btn-info {
  background-color: #6366f1;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.btn-export {
  background-color: #0ea5e9;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.25);
}

.progress-row {
  :deep(.el-progress-bar__innerText) {
    font-size: 12px;
    color: #fff;
  }
}

.simulation-select {
  margin: 0;
  width: 200px;
  :deep(.el-input__wrapper) {
    border-radius: 10px;
    background-color: transparent;
    box-shadow: 0 0 0 1px var(--sidebar-border) inset;
  }
  :deep(.el-input__inner) {
    text-align: center;
    font-weight: 500;
  }
}

/* 响应式适配：medium 及以下断点缩小间距 */
@include bp.respond-to('medium-down') {
  .device-container {
    padding: 12px 16px;
  }
  .nodes {
    padding: 10px 16px;
    gap: 10px;
  }
  .button {
    min-width: 100px;
    height: 38px;
    font-size: 13px;
  }
  .simulation-select {
    width: 170px;
  }
}

/* small 断点：按钮和选择器全宽，单列布局 */
@include bp.respond-to('small') {
  .device-container {
    padding: 10px 12px;
  }
  .nodes {
    flex-direction: column;
    align-items: stretch;
    padding: 10px 14px;
    gap: 8px;
  }
  .button, .simulation-select {
    width: 100%;
  }
}
</style>
