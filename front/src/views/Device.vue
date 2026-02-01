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
    <Slave />
    
    <!-- 报文查看对话框 -->
    <MessageViewDialog
      v-model="showMessageDialog"
      :device-name="routeName"
    />
  </el-col>
</template>

<script lang="ts" setup>
import { ref, onMounted, onUnmounted, computed, watch } from "vue";
import { useRoute } from "vue-router";
import TextNode from "@/components/common/TextNode.vue";
import Slave from "@/components/device/Slave.vue";
import MessageViewDialog from "@/components/device/MessageViewDialog.vue";
import {
  getDeviceInfo,
  startSimulation,
  stopSimulation,
  startDevice,
  stopDevice,
} from "@/api/deviceApi";
import { CaretRight, VideoPause, Document } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const route = useRoute();

const getDeviceNameFromRoute = () => {
  return (route.params.deviceName as string) || '';
};

const routeName = ref(getDeviceNameFromRoute());
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

const isSerialMode = computed(() => {
  const type = communicationType.value;
  return type && (type.includes('Dlt645') || type === 'ModbusRtu') && serialPort.value;
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
        deviceStatus.value = true;
        deviceStatusStr.value = "运行中";
      } else {
        ElMessage.error("启动设备失败");
      }
    }
  } catch (error: any) { 
    console.error(error);
    ElMessage.error(error.message || "操作失败");
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
    const simuStatus = info.get("simulation_status");
    simulationStatus.value = simuStatus;
    simulationStatusStr.value = simuStatus === true ? "运行中" : "停止";
  } catch (error: any) { 
    console.error(error); 
    ElMessage.error("获取设备信息失败: " + (error.message || "未知错误"));
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
const STATUS_POLL_INTERVAL = 5000; // 5秒轮询一次

// 仅获取状态（不更新其他信息，减少开销）
const fetchDeviceStatus = async () => {
  try {
    const info = await getDeviceInfo(routeName.value);
    const serverStatus = info.get("server_status");
    // 只有状态变化时才更新
    if (deviceStatus.value !== serverStatus) {
      deviceStatus.value = serverStatus;
      deviceStatusStr.value = serverStatus === true ? "运行中" : "停止";
      // 状态变化提示
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
  startStatusPolling();
});

onUnmounted(() => {
  stopStatusPolling();
});

watch(() => route.fullPath, async () => {
  const newName = getDeviceNameFromRoute();
  
  if (newName) {
    if (routeName.value !== newName) {
      routeName.value = newName;
      // 重置数据
      deviceInfo.value = new Map<string, any>();
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

@media (max-width: 768px) {
  .nodes { flex-direction: column; align-items: stretch; }
  .button, .simulation-select { width: 100%; }
}
</style>
