<template>
  <el-col class="device-container">
    <el-row class="nodes" :span="24">
      <TextNode label="服务器地址" :name="ip" />
      <TextNode label="端口号" :name="String(port)" />
      <TextNode label="通讯类型" :name="communicationType" />
      <TextNode label="设备状态" :name="deviceStatusStr" :status="deviceStatus" />
      <el-button
        type="primary"
        class="button device-button"
        :style="deviceButtonStyle"
        @click="toggleDevice"
        :disabled="isProcessing"
      >
        <el-icon v-if="!deviceStatus" class="icon"><CaretRight /></el-icon>
        <el-icon v-else class="icon"><Stopwatch /></el-icon>
        <span> {{ deviceButtonText }} </span>
      </el-button>
    </el-row>
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
        type="primary"
        class="button"
        :style="buttonStyle"
        @click="startFunction"
        :disabled="isProcessing || !deviceStatus"
      >
        <!-- 动态切换图标 -->
        <el-icon v-if="!simulationStatus" class="icon"><CaretRight /></el-icon>
        <el-icon v-else class="icon"><Stopwatch /></el-icon>
        <span> {{ buttonText }} </span>
      </el-button>
    </el-row>
    <Slave />
  </el-col>
</template>

<script lang="ts" setup>
import { ref, onMounted, computed, watch } from "vue";
import { useRoute } from "vue-router";
import TextNode from "@/components/TextNode.vue";
import Slave from "@/components/Slave.vue";
import {
  getDeviceInfo,
  startSimulation,
  stopSimulation,
  startDevice,
  stopDevice,
} from "@/api/deviceApi";
import { CaretRight, Stopwatch } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const route = useRoute();
const routeName = ref(route.name as string);

const deviceInfo = ref(new Map<string, any>());
const ip = ref<any>("");
const port = ref<any>("");
const communicationType = ref<any>("");
const deviceStatus = ref<boolean>(false);
const deviceStatusStr = ref<any>("");
const simulationStatus = ref<boolean>(false);
const simulationStatusStr = ref<any>("");
const isProcessing = ref<boolean>(false);
const simulateOptions = [
  {
    value: "Random",
    label: "随机模拟",
  },
  {
    value: "AutoIncrement",
    label: "自增模拟",
  },
  {
    value: "AutoDecrement",
    label: "自减模拟",
  },
  {
    value: "SineWave",
    label: "正弦波模拟",
  },
  {
    value: "Ramp",
    label: "斜坡模拟",
  },
  {
    value: "Pulse",
    label: "脉冲模拟",
  },
];
const currentSimulateMethod = ref<string>(simulateOptions[0].value);

const buttonStyle = computed(() => {
  if (simulationStatus.value) {
    return {
      backgroundColor: "#f44336",
    };
  } else {
    return {
      backgroundColor: "#4caf50",
    };
  }
});

// 设备按钮样式
const deviceButtonStyle = computed(() => {
  if (deviceStatus.value) {
    return {
      backgroundColor: "#f44336",
    };
  } else {
    return {
      backgroundColor: "#2196f3",
    };
  }
});

// 设备按钮文本
const deviceButtonText = computed(() => {
  if (deviceStatus.value) {
    return "停止设备";
  } else {
    return "开启设备";
  }
});

// 设备状态切换函数
const toggleDevice = async () => {
  isProcessing.value = true;
  try {
    if (deviceStatus.value) {
      // 停止设备
      const isSuccess = await stopDevice(routeName.value);
      if (isSuccess) {
        deviceStatus.value = false;
        deviceStatusStr.value = "停止";
        // 如果设备停止，同时停止模拟
        if (simulationStatus.value) {
          await stopSimulation(routeName.value);
          simulationStatus.value = false;
          simulationStatusStr.value = "停止";
        }
      } else {
        ElMessage.error("停止设备失败!");
      }
    } else {
      // 启动设备
      const isSuccess = await startDevice(routeName.value);
      if (isSuccess) {
        deviceStatus.value = true;
        deviceStatusStr.value = "运行中";
      } else {
        ElMessage.error("开启设备失败!");
      }
    }
  } catch (error) {
    console.error("Error toggling device status:", error);
  } finally {
    isProcessing.value = false;
  }
};

// 封装数据获取逻辑
const fetchDeviceInfo = async () => {
  try {
    const info = await getDeviceInfo(routeName.value);
    deviceInfo.value = info;

    ip.value = deviceInfo.value.get("ip") || null;
    port.value = deviceInfo.value.get("port") || null;
    communicationType.value = deviceInfo.value.get("type") || null;
    // 根据布尔值设置设备状态
    const serverStatus = deviceInfo.value.get("server_status");
    deviceStatus.value = serverStatus;
    deviceStatusStr.value = serverStatus === true ? "运行中" : "停止";
    // 根据布尔值设置模拟状态
    const simulationStatusValue = deviceInfo.value.get("simulation_status");
    simulationStatus.value = simulationStatusValue;
    simulationStatusStr.value = simulationStatusValue === true ? "运行中" : "停止";
  } catch (error) {
    console.error("Error fetching device info:", error);
  }
};

// 计算按钮文本
const buttonText = computed(() => {
  if (simulationStatus.value) {
    return "停止";
  } else {
    return "开始";
  }
});

// 定义 startFunction
const startFunction = async () => {
  isProcessing.value = true;
  try {
    if (simulationStatus.value) {
      // 如果设备或模拟正在运行，则停止它们
      const isSuccess = await stopSimulation(routeName.value);
      if (isSuccess) {
        simulationStatus.value = false;
        simulationStatusStr.value = "停止";
      }
    } else {
      // 否则，开始它们
      const isSuccess = await startSimulation(
        routeName.value,
        currentSimulateMethod.value
      );
      if (isSuccess) {
        simulationStatus.value = true;
        simulationStatusStr.value = "运行中";
      }
    }
  } catch (error) {
    console.error("Error starting/stopping device:", error);
  } finally {
    isProcessing.value = false;
  }
};

// 在组件挂载时首次获取数据
onMounted(async () => {
  await fetchDeviceInfo();
});

// 监听路由变化
watch(
  () => route.name,
  async (newRouteName) => {
    if (newRouteName) {
      routeName.value = newRouteName as string;
      await fetchDeviceInfo();
    }
  }
);
</script>

<style scoped>
.device-container {
  padding: 15px 20px;
  background-color: #ffffff;
  min-height: 100vh;
}

.nodes {
  display: flex;
  flex-direction: row;
  gap: 18px; /* 调整选项之间的间距 */
  margin: 8px 0;
  flex-wrap: wrap; /* 允许在小屏幕上换行 */
  align-items: center; /* 垂直居中对齐所有元素 */
  background-color: #ffffff;
  padding: 15px 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.button {
  margin: 0;
  width: 100px;
  height: 40px;
  padding: 10px;
  text-align: center;
  transition: all 0.3s ease; /* 添加背景色过渡效果 */
  border-radius: 6px;
  font-size: 15px;

  .icon {
    font-size: 20px;
    vertical-align: middle;
    margin-right: 5px;
  }
}

.device-button {
  width: 110px;
}

.simulation-select {
  margin: 0;
  width: 180px;
  text-align: center;
  border-radius: 6px;
}

/* 响应式布局调整 */
@media (max-width: 768px) {
  .nodes {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
    margin-left: 10px;
  }

  .button,
  .simulation-select {
    margin: 10px 0 0 0;
    width: 100%;
    max-width: 300px;
  }
}

@media (max-width: 480px) {
  .device-container {
    padding: 10px;
  }

  .button {
    height: 36px;
    font-size: 14px;
  }
}
</style>
