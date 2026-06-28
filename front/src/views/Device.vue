<template>
  <el-col class="device-container">
    <!-- 第一行：设备基本通讯信息 + 启动/停止 + 查看报文 -->
    <el-row class="nodes row-device-info" :span="24">
      <TextNode
        v-if="!isSerialMode"
        iconType="address"
        :label="$t('device.serverAddress')"
        :name="ip"
      />
      <TextNode
        v-if="!isSerialMode"
        iconType="port"
        :label="$t('device.port')"
        :name="String(port)"
      />
      <TextNode
        v-if="isSerialMode"
        iconType="serial"
        :label="$t('device.serialPort')"
        :name="serialPort || '-'"
      />
      <TextNode
        v-if="isSerialMode"
        iconType="baud"
        :label="$t('device.baudRate')"
        :name="String(baudrate)"
      />
      <TextNode
        iconType="comm"
        :label="$t('device.commType')"
        :name="communicationType"
      />
      <TextNode
        iconType="device-status"
        :label="$t('device.deviceStatus')"
        :name="deviceStatusStr"
        :status="deviceStatus"
      />
      <el-tooltip
        :content="isDeviceStartDisabled ? $t('device.modelNotLoaded') : ''"
        :disabled="!isDeviceStartDisabled"
        placement="top"
      >
        <span class="tooltip-wrapper">
          <el-button
            :class="['button', deviceStatus ? 'btn-stop' : 'btn-primary-action']"
            @click="toggleDevice"
            :disabled="isDeviceProcessing || isDeviceStartDisabled"
            :loading="isDeviceProcessing"
          >
            <template #icon v-if="!isDeviceProcessing">
              <el-icon v-if="!deviceStatus" class="icon"><CaretRight /></el-icon>
              <el-icon v-else class="icon"><VideoPause /></el-icon>
            </template>
            <span>
              {{ $t(deviceStatus ? "device.stopDevice" : "device.startDevice") }}
            </span>
          </el-button>
        </span>
      </el-tooltip>
      <el-button class="button btn-info" @click="showMessageDialog = true">
        <el-icon class="icon"><Document /></el-icon>
        <span>{{ $t("device.viewMessages") }}</span>
      </el-button>
    </el-row>

    <!-- 第二行：IEC61850 模型管理 + 仿真模拟控制 -->
    <el-row class="nodes row-model-sim" :span="24">
      <!-- IEC61850 模型区域 -->
      <div v-if="isIec61850Protocol" class="model-section">
        <div class="model-controls">
          <!-- 模型状态 -->
          <TextNode
            iconType="model"
            :label="$t('device.modelStatus')"
            :name="modelLoaded ? $t('device.modelLoaded') : $t('device.modelNotLoaded')"
            :status="modelLoaded"
          />

          <!-- 加载模型：从数据库加载 -->
          <el-button
            class="button btn-load-model"
            @click="handleLoadModelFromDb"
            :disabled="isModelProcessing"
            :loading="isModelProcessing"
            size="large"
          >
            <el-icon class="icon"><FolderOpened /></el-icon>
            <span>{{ $t("device.loadModel") }}</span>
          </el-button>

          <!-- 导入模型 -->
          <el-button
            class="button btn-import-model"
            :disabled="isModelProcessing"
            size="large"
            @click="handleImportModel"
          >
            <el-icon class="icon"><Upload /></el-icon>
            <span>{{ $t("device.importModel") }}</span>
          </el-button>
          <IcdImportUpload
            ref="icdImportUploadRef"
            @file-change="onIcdFileChange"
            @import-success="onIcdImportSuccess"
            @import-error="onIcdImportError"
          />

          <!-- 导出模型（仅客户端） -->
          <el-button
            v-if="isIec61850Client"
            class="button btn-export"
            @click="showExportDialog = true"
            :disabled="!deviceStatus"
            size="large"
          >
            <el-icon class="icon"><Download /></el-icon>
            <span>{{ $t("device.exportModel") }}</span>
          </el-button>
        </div>
      </div>

      <!-- 分隔线 -->
      <div v-if="isIec61850Protocol" class="section-divider" />

      <!-- 仿真模拟区域 -->
      <div class="sim-section">
        <div class="sim-controls">
          <TextNode
            iconType="sim-status"
            :label="$t('device.simulationStatus')"
            :name="simulationStatusStr"
            :status="simulationStatus"
          />
          <el-select
            v-model="currentSimulateMethod"
            :placeholder="$t('device.selectSimMethod')"
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
          <!-- 模拟工具提示 -->
          <el-tooltip
            :content="simTooltipText"
            :disabled="!simTooltipDisabled"
            placement="top"
          >
            <span class="tooltip-wrapper">
              <el-button
                :class="['button', simulationStatus ? 'btn-stop' : 'btn-start']"
                @click="startFunction"
                :disabled="
                  isSimProcessing ||
                  !deviceStatus ||
                  isClientDevice ||
                  (isIec61850Protocol && !modelLoaded)
                "
                :loading="isSimProcessing"
              >
                <template #icon v-if="!isSimProcessing">
                  <el-icon v-if="!simulationStatus" class="icon"><CaretRight /></el-icon>
                  <el-icon v-else class="icon"><VideoPause /></el-icon>
                </template>
                <span>
                  {{ $t(simulationStatus ? "device.stopSim" : "device.startSim") }}
                </span>
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </div>
    </el-row>

    <!-- 第三行：IEC61850 连接进度条 -->
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
    <MessageViewDialog v-model="showMessageDialog" :device-name="routeName" />

    <!-- 模型导出对话框 -->
    <ModelExportDialog v-model="showExportDialog" :device-name="routeName" />
  </el-col>
</template>

<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import {
  ref,
  onMounted,
  onUnmounted,
  computed,
  watch,
  onActivated,
  onDeactivated,
} from "vue";
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
  loadIEC61850Model,
} from "@/api/deviceApi";
import type { IEC61850ConnectProgress } from "@/api/deviceApi";
import { triggerSidebarRefresh } from "@/composables";
import IcdImportUpload from "@/components/common/IcdImportUpload.vue";
import {
  CaretRight,
  VideoPause,
  Document,
  Download,
  FolderOpened,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const route = useRoute();
const { t } = useI18n();

const getDeviceNameFromRoute = () => {
  return (route.params.deviceName as string) || "";
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
const simulationStatus = ref<boolean>(false);
const showMessageDialog = ref<boolean>(false);
const showExportDialog = ref<boolean>(false);
const slaveRef = ref<any>(null);
const icdImportUploadRef = ref<InstanceType<typeof IcdImportUpload>>();

// 设备状态文字：使用 computed 确保语言切换时自动刷新
const deviceStatusStr = computed(() => {
  if (iec61850Connecting.value) return t("device.connecting");
  return deviceStatus.value ? t("common.running") : t("common.stopped");
});

// 模拟状态文字：使用 computed 确保语言切换时自动刷新
const simulationStatusStr = computed(() => {
  return simulationStatus.value ? t("common.running") : t("common.stopped");
});

const isSerialMode = computed(() => {
  const type = communicationType.value;
  return (
    type && (type.includes("Dlt645") || type.startsWith("ModbusRtu")) && serialPort.value
  );
});

const isClientDevice = computed(() => {
  const type = communicationType.value;
  // 检查是否为客户端类型 (包含 Client 且不包含 Server)
  // ModbusTcpClient, Iec104Client, Dlt645Client
  return String(type).includes("Client");
});

// IEC61850 协议检测
const isIec61850Protocol = computed(() => {
  const type = communicationType.value;
  return type && (String(type) === "Iec61850Client" || String(type) === "Iec61850Server");
});

// IEC61850: 模型未加载时不允许开启设备（禁用启动按钮）
const isDeviceStartDisabled = computed(() => {
  return isIec61850Protocol.value && !deviceStatus.value && !modelLoaded.value;
});

// 模拟按钮禁用的工具提示
const simTooltipText = computed(() => {
  if (isClientDevice.value) return t("device.clientNoSim");
  if (isIec61850Protocol.value && !modelLoaded.value) return t("device.modelNotLoaded");
  if (!deviceStatus.value) return t("device.deviceNotStarted");
  return "";
});
const simTooltipDisabled = computed(() => {
  // 当按钮因任何原因禁用时，显示提示
  return (
    isClientDevice.value ||
    !deviceStatus.value ||
    (isIec61850Protocol.value && !modelLoaded.value)
  );
});

// IEC61850 模型加载状态
const modelLoaded = ref(false);
const isModelProcessing = ref(false);
const channelId = ref<number | null>(null);

const simulateOptions = computed(() => [
  { value: "Random", label: t("device.random") },
  { value: "AutoIncrement", label: t("device.autoIncrement") },
  { value: "AutoDecrement", label: t("device.autoDecrement") },
  { value: "SineWave", label: t("device.sineWave") },
  { value: "Ramp", label: t("device.ramp") },
  { value: "Pulse", label: t("device.pulse") },
]);
const currentSimulateMethod = ref<string>("Random");

const isDeviceProcessing = ref<boolean>(false);
const isSimProcessing = ref<boolean>(false);

// IEC61850 连接进度
const iec61850Connecting = ref(false);
const iec61850ConnectProgress = ref<IEC61850ConnectProgress | null>(null);
const iec61850Elapsed = ref(0);
let iec61850ElapsedTimer: number | null = null;
const iec61850PhaseLabel: Record<string, string> = {
  idle: t("device.preparing"),
  connecting: t("device.connectingServer"),
  discovering: t("device.discoveringModel"),
  done: t("device.connectDone"),
  failed: t("device.connectFailed"),
};

const isIec61850Client = computed(() => {
  return communicationType.value && String(communicationType.value) === "Iec61850Client";
});

const iec61850ProgressPercent = computed(() => {
  if (!iec61850ConnectProgress.value) return 0;
  return iec61850ConnectProgress.value.progress || 0;
});

const iec61850PhaseText = computed(() => {
  if (!iec61850ConnectProgress.value) return "";
  const label = iec61850PhaseLabel[iec61850ConnectProgress.value.phase] || "";
  const phase = iec61850ConnectProgress.value.phase;
  if (phase === "idle" || phase === "connecting" || phase === "discovering") {
    return `${label} (${iec61850Elapsed.value}s)`;
  }
  return label;
});

let iec61850ProgressTimer: number | null = null;

const startIec61850ProgressPolling = () => {
  stopIec61850ProgressPolling();
  iec61850Connecting.value = true;
  iec61850ConnectProgress.value = null;
  iec61850Elapsed.value = 0;
  iec61850ElapsedTimer = window.setInterval(() => {
    iec61850Elapsed.value++;
  }, 1000);
  iec61850ProgressTimer = window.setInterval(async () => {
    const progress = await getIEC61850ConnectProgress(routeName.value);
    if (progress) {
      iec61850ConnectProgress.value = progress;
      if (progress.phase === "done" || progress.phase === "failed") {
        stopIec61850ProgressPolling();
        if (progress.phase === "done") {
          deviceStatus.value = true;
          ElMessage.success(t("device.iec61850DeviceConnectSuccess"));
          slaveRef.value?.reloadDatas();
          triggerSidebarRefresh(routeName.value);
        } else {
          ElMessage.error(t("device.iec61850DeviceConnectFailed"));
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
  if (iec61850ElapsedTimer) {
    clearInterval(iec61850ElapsedTimer);
    iec61850ElapsedTimer = null;
  }
  iec61850Connecting.value = false;
};

const toggleDevice = async () => {
  isDeviceProcessing.value = true;
  try {
    if (deviceStatus.value) {
      if (await stopDevice(routeName.value)) {
        deviceStatus.value = false;
        if (simulationStatus.value) {
          // 设备停止时，仿真自动停止，但不触发仿真按钮的loading
          simulationStatus.value = false;
        }
      } else {
        ElMessage.error(t("device.stopDeviceFailed"));
      }
    } else {
      if (await startDevice(routeName.value)) {
        if (isIec61850Client.value) {
          // IEC61850: 后台连接中，启动进度轮询
          startIec61850ProgressPolling();
        } else {
          deviceStatus.value = true;
          ElMessage.success(t("device.startDeviceSuccess"));
        }
      } else {
        ElMessage.error(t("device.startDeviceFailed"));
      }
    }
  } catch (error: any) {
    console.error(error);
    // error message is handled by global interceptor
  } finally {
    isDeviceProcessing.value = false;
  }
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
    channelId.value = info.get("channel_id") ?? null;
    const serverStatus = info.get("server_status");
    deviceStatus.value = serverStatus;
    // 初始化防抖状态，避免初始加载时误弹通知
    lastNotifyServerStatus = serverStatus;
    stableServerStatus = serverStatus;
    prevServerStatus = serverStatus;
    statusUnstableCount = STATUS_STABLE_THRESHOLD;
    const simuStatus = info.get("simulation_status");
    simulationStatus.value = simuStatus;

    // IEC61850 客户端：如果设备未运行，检查是否正在后台连接中
    if (!serverStatus && String(communicationType.value) === "Iec61850Client") {
      const progress = await getIEC61850ConnectProgress(routeName.value);
      if (progress && progress.connecting) {
        // 正在连接中，启动进度轮询
        iec61850Connecting.value = true;
        iec61850ConnectProgress.value = progress;
        startIec61850ProgressPolling();
      }
    }

    // IEC61850: 直接从 info 中读取模型加载状态
    if (isIec61850Protocol.value) {
      modelLoaded.value = info.get("iec61850_model_loaded") === true;
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
      }
    } else {
      if (await startSimulation(routeName.value, currentSimulateMethod.value)) {
        simulationStatus.value = true;
      }
    }
  } catch (error) {
    console.error(error);
  } finally {
    isSimProcessing.value = false;
  }
};

// IEC61850 模型加载：从数据库加载
const handleLoadModelFromDb = async () => {
  isModelProcessing.value = true;
  try {
    const success = await loadIEC61850Model(routeName.value);
    if (success) {
      modelLoaded.value = true;
      ElMessage.success(t("device.modelLoadSuccess"));
      triggerSidebarRefresh(routeName.value);
    } else {
      ElMessage.error(t("device.modelLoadFailed"));
    }
  } catch (error: any) {
    console.error(error);
    // 后端返回的错误消息已由全局拦截器处理
  } finally {
    isModelProcessing.value = false;
  }
};

// IEC61850 模型导入：文件选择回调
const onIcdFileChange = () => {
  // 文件选中后自动开始导入
  if (!channelId.value) {
    ElMessage.error(t("device.modelLoadFailed"));
    return;
  }
  icdImportUploadRef.value?.importIcd(channelId.value).catch(() => {});
};

// IEC61850 模型导入：点击按钮打开文件选择框
const handleImportModel = () => {
  icdImportUploadRef.value?.openFileDialog();
};

// IEC61850 模型导入：成功回调
const onIcdImportSuccess = () => {
  modelLoaded.value = true;
  ElMessage.success(t("device.modelLoadSuccess"));
  triggerSidebarRefresh(routeName.value);
};

// IEC61850 模型导入：失败回调
const onIcdImportError = () => {
  ElMessage.error(t("device.modelLoadFailed"));
};

// 状态轮询定时器
let statusPollTimer: number | null = null;
const STATUS_POLL_INTERVAL = 1000; // 1秒轮询一次

// 连接状态防抖：避免因连接状态抖动（如客户端重连过程中反复连接成功又断开）导致不停弹窗
let lastNotifyServerStatus: boolean | null = null; // 上一次弹窗通知时的连接状态
let stableServerStatus: boolean | null = null; // 当前稳定的连接状态
let statusUnstableCount = 0; // 状态不稳定计数（连续变化的次数）
const STATUS_STABLE_THRESHOLD = 3; // 连续3次状态一致才认为状态稳定
let prevServerStatus: boolean | null = null; // 上一次轮询的连接状态（用于检测即时变化，如 IEC 61850 测点刷新）

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
      }
    } else {
      deviceStatus.value = serverStatus;
    }

    // IEC 61850 客户端：检测到连接从 false 变为 true 时立即刷新测点表格
    // （不需要等防抖，因为测点发现完成后数据立即可用）
    if (serverStatus === true && prevServerStatus === false) {
      if (
        communicationType.value &&
        String(communicationType.value) === "Iec61850Client"
      ) {
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
    if (
      statusUnstableCount >= STATUS_STABLE_THRESHOLD &&
      lastNotifyServerStatus !== serverStatus
    ) {
      lastNotifyServerStatus = serverStatus;
      if (serverStatus === true) {
        ElMessage.success(t("device.deviceConnected", { name: routeName.value }));
      } else {
        ElMessage.warning(t("device.deviceDisconnected", { name: routeName.value }));
      }
    }

    const simuStatus = info.get("simulation_status");
    if (simulationStatus.value !== simuStatus) {
      simulationStatus.value = simuStatus;
      // 模拟状态变化提示
      if (simuStatus === true) {
        ElMessage.info(t("device.simStarted", { name: routeName.value }));
      } else {
        ElMessage.info(t("device.simStopped", { name: routeName.value }));
      }
    }
  } catch (error) {
    /* 静默处理轮询错误 */
  }
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

watch(
  () => route.path,
  async () => {
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
  },
  { immediate: true }
);
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

/* 第一行：保持默认 inline 流式布局 */
.row-device-info {
  display: flex;
  flex-wrap: wrap;
}

/* 第二行：模型 + 模拟双栏布局 */
.row-model-sim {
  display: flex;
  flex-wrap: nowrap;
  gap: 0;
  align-items: stretch;
  padding: 0;
  overflow: hidden;

  .model-section,
  .sim-section {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px 20px;
    flex: 1;
  }

  .model-section {
    min-width: 0;
  }

  .sim-section {
    min-width: 0;
  }

  .model-controls,
  .sim-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }

  .section-divider {
    width: 1px;
    background: linear-gradient(
      180deg,
      transparent 0%,
      var(--sidebar-border) 15%,
      var(--sidebar-border) 85%,
      transparent 100%
    );
    flex-shrink: 0;
  }
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

.btn-load-model {
  background-color: #8b5cf6;
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.25);
}

.btn-import-model {
  background-color: #f59e0b;
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.25);
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
@include bp.respond-to("medium-down") {
  .device-container {
    padding: 12px 16px;
  }
  .nodes {
    padding: 10px 16px;
    gap: 10px;
  }
  .row-model-sim {
    .model-section,
    .sim-section {
      padding: 12px 16px;
    }
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
@include bp.respond-to("small") {
  .device-container {
    padding: 10px 12px;
  }
  .nodes {
    flex-direction: column;
    align-items: stretch;
    padding: 10px 14px;
    gap: 8px;
  }
  .row-device-info {
    flex-direction: column;
    align-items: stretch;
  }
  .row-model-sim {
    flex-direction: column;
    .model-section,
    .sim-section {
      padding: 12px 14px;
    }
    .section-divider {
      width: 100%;
      height: 1px;
      background: linear-gradient(
        90deg,
        transparent 0%,
        var(--sidebar-border) 15%,
        var(--sidebar-border) 85%,
        transparent 100%
      );
    }
  }
  .button,
  .simulation-select {
    width: 100%;
  }
}
</style>
