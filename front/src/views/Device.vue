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
        :disabled="isProcessing"
      >
        <el-icon v-if="!deviceStatus" class="icon"><CaretRight /></el-icon>
        <el-icon v-else class="icon"><VideoPause /></el-icon>
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
      >
        <el-option
          v-for="item in simulateOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-button
        :class="['button', simulationStatus ? 'btn-stop' : 'btn-start']"
        @click="startFunction"
        :disabled="isProcessing || !deviceStatus"
      >
        <el-icon v-if="!simulationStatus" class="icon"><CaretRight /></el-icon>
        <el-icon v-else class="icon"><VideoPause /></el-icon>
        <span> {{ buttonText }} </span>
      </el-button>
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
import { ref, onMounted, computed, watch } from "vue";
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
const routeName = ref(route.name as string);

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
const isProcessing = ref<boolean>(false);
const showMessageDialog = ref<boolean>(false);

const isSerialMode = computed(() => {
  const type = communicationType.value;
  return type && (type.includes('Dlt645') || type === 'ModbusRtu') && serialPort.value;
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

const toggleDevice = async () => {
  isProcessing.value = true;
  try {
    if (deviceStatus.value) {
      if (await stopDevice(routeName.value)) {
        deviceStatus.value = false;
        deviceStatusStr.value = "停止";
        if (simulationStatus.value) {
          await stopSimulation(routeName.value);
          simulationStatus.value = false;
          simulationStatusStr.value = "停止";
        }
      }
    } else {
      if (await startDevice(routeName.value)) {
        deviceStatus.value = true;
        deviceStatusStr.value = "运行中";
      }
    }
  } catch (error) { console.error(error); }
  finally { isProcessing.value = false; }
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
  } catch (error) { console.error(error); }
};

const startFunction = async () => {
  isProcessing.value = true;
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
  finally { isProcessing.value = false; }
};

onMounted(() => { fetchDeviceInfo(); });
watch(() => route.name, async (newVal) => {
  if (newVal) { routeName.value = newVal as string; await fetchDeviceInfo(); }
});
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
