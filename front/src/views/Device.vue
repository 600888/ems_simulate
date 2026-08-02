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
            :class="[
              'button',
              deviceStatus ? 'btn-stop' : 'btn-primary-action',
            ]"
            @click="toggleDevice"
            :disabled="isDeviceProcessing || isDeviceStartDisabled"
            :loading="isDeviceProcessing"
          >
            <template #icon v-if="!isDeviceProcessing">
              <el-icon v-if="!deviceStatus" class="icon"
                ><CaretRight
              /></el-icon>
              <el-icon v-else class="icon"><VideoPause /></el-icon>
            </template>
            <span>
              {{
                $t(deviceStatus ? "device.stopDevice" : "device.startDevice")
              }}
            </span>
          </el-button>
        </span>
      </el-tooltip>
      <el-button class="button btn-info" @click="handleOpenMessageView">
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
            :name="
              modelLoaded
                ? $t('device.modelLoaded')
                : $t('device.modelNotLoaded')
            "
            :status="modelLoaded"
          />

          <!-- 加载模型：从数据库加载 -->
          <el-button
            class="button btn-load-model"
            @click="handleLoadModelFromDb"
            :disabled="isAnyModelProcessing"
            :loading="isModelProcessing"
            size="large"
          >
            <el-icon class="icon"><Refresh /></el-icon>
            <span>{{ $t("device.loadModel") }}</span>
          </el-button>

          <!-- 导入模型 -->
          <el-button
            class="button btn-import-model"
            :disabled="isAnyModelProcessing"
            :loading="modelImporting"
            size="large"
            @click="handleImportModel"
          >
            <el-icon class="icon"><Upload /></el-icon>
            <span>{{ $t("device.importModel") }}</span>
          </el-button>
          <IcdImportUpload
            ref="icdImportUploadRef"
            @file-change="onIcdFileChange"
            @import-start="onIcdImportStart"
            @import-success="onIcdImportSuccess"
            @import-error="onIcdImportError"
          />

          <!-- 远程发现模型（仅客户端） -->
          <el-button
            v-if="isIec61850Client"
            class="button btn-discover-model"
            :disabled="isAnyModelProcessing"
            :loading="modelDiscovering"
            size="large"
            @click="handleDiscoverModel"
          >
            <el-icon class="icon"><Search /></el-icon>
            <span>{{ $t("device.discoverModel") }}</span>
          </el-button>

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
                  <el-icon v-if="!simulationStatus" class="icon"
                    ><CaretRight
                  /></el-icon>
                  <el-icon v-else class="icon"><VideoPause /></el-icon>
                </template>
                <span>
                  {{
                    $t(simulationStatus ? "device.stopSim" : "device.startSim")
                  }}
                </span>
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </div>
    </el-row>

    <!-- 第三行：IEC61850 模型加载/导入/发现共用进度条 -->
    <el-row v-if="modelProgressVisible" class="nodes progress-row" :span="24">
      <el-progress
        :percentage="modelProgressPercent"
        :stroke-width="20"
        :show-text="false"
        striped
        striped-flow
        style="width: 100%"
      />
      <span class="model-progress-text">{{ modelProgressText }}</span>
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
  nextTick,
} from "vue";
import { useRoute } from "vue-router";
import TextNode from "@/components/common/TextNode.vue";
import Slave from "@/components/device/Slave.vue";
import MessageViewDialog from "@/components/device/MessageViewDialog.vue";
import { isTauri, openMessageWindow } from "@/utils/tauri";
import ModelExportDialog from "@/components/device/ModelExportDialog.vue";
import {
  getDeviceInfo,
  startSimulation,
  stopSimulation,
  startDevice,
  stopDevice,
  getIEC61850ConnectProgress,
  loadIEC61850Model,
  discoverIEC61850Model,
  checkIEC61850ModelCache,
  loadIEC61850ModelFromCache,
} from "@/api/deviceApi";
import type { IEC61850ConnectProgress } from "@/api/deviceApi";
import { triggerSidebarRefresh } from "@/composables";
import {
  acquireAutoRefreshPause,
  isAutoRefreshPaused,
} from "@/composables/autoRefreshGate";
import IcdImportUpload from "@/components/common/IcdImportUpload.vue";
import {
  CaretRight,
  VideoPause,
  Document,
  Download,
  Refresh,
  Search,
  Upload,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { HTTP_TIMEOUT_MODEL_DISCOVERY } from "@/constants";
import { showError, showErrorOnce } from "@/api/http";

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

const handleOpenMessageView = async () => {
  if (!isTauri()) {
    showMessageDialog.value = true;
    return;
  }
  try {
    await openMessageWindow(routeName.value);
  } catch (error) {
    console.error("打开独立报文窗口失败:", error);
    showError(error, t("messageView.openWindowFailed"));
  }
};
const showExportDialog = ref<boolean>(false);
const slaveRef = ref<any>(null);
const icdImportUploadRef = ref<InstanceType<typeof IcdImportUpload>>();
const modelPauseReleases = new Set<() => void>();

const acquireModelPause = (reason: string): (() => void) => {
  const releaseGate = acquireAutoRefreshPause(reason);
  const release = () => {
    releaseGate();
    modelPauseReleases.delete(release);
  };
  modelPauseReleases.add(release);
  return release;
};

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
    type &&
    (type.includes("Dlt645") || type.startsWith("ModbusRtu")) &&
    serialPort.value
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
  return (
    type &&
    (String(type) === "Iec61850Client" || String(type) === "Iec61850Server")
  );
});

// IEC61850: 模型未加载时不允许开启设备（禁用启动按钮）
const isDeviceStartDisabled = computed(() => {
  return isIec61850Protocol.value && !deviceStatus.value && !modelLoaded.value;
});

// 模拟按钮禁用的工具提示
const simTooltipText = computed(() => {
  if (isClientDevice.value) return t("device.clientNoSim");
  if (isIec61850Protocol.value && !modelLoaded.value)
    return t("device.modelNotLoaded");
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
const modelLoading = ref(false);
const modelImporting = ref(false);
const modelDiscovering = ref(false);
const modelImportElapsed = ref(0);
let modelImportElapsedTimer: number | null = null;
const channelId = ref<number | null>(null);
const isAnyModelProcessing = computed(
  () =>
    isModelProcessing.value ||
    modelLoading.value ||
    modelImporting.value ||
    modelDiscovering.value ||
    iec61850Connecting.value,
);

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
let iec61850ProgressStartedAt = 0;
const iec61850PhaseLabel: Record<string, string> = {
  idle: t("device.preparing"),
  connecting: t("device.connectingServer"),
  discovering: t("device.discoveringModel"),
  done: t("device.connectDone"),
  failed: t("device.connectFailed"),
};

const isIec61850Client = computed(() => {
  return (
    communicationType.value &&
    String(communicationType.value) === "Iec61850Client"
  );
});

const iec61850ProgressPercent = computed(() => {
  if (!iec61850ConnectProgress.value) return 0;
  const value = Number(iec61850ConnectProgress.value.progress);
  return Number.isFinite(value) ? Math.min(Math.max(value, 0), 100) : 0;
});

const iec61850PhaseText = computed(() => {
  if (!iec61850ConnectProgress.value) return "";
  return iec61850PhaseLabel[iec61850ConnectProgress.value.phase] || "";
});

const modelProgressVisible = computed(
  () =>
    iec61850Connecting.value ||
    modelLoading.value ||
    modelImporting.value ||
    modelDiscovering.value,
);
const modelProgressPercent = computed(() => {
  if (modelLoading.value) return 50;
  if (modelImporting.value) return 50;
  return iec61850ProgressPercent.value;
});
const modelProgressText = computed(() => {
  if (modelLoading.value) {
    return `${t("device.loadModel")} (${modelImportElapsed.value}s)`;
  }
  if (modelImporting.value) {
    return `${t("addDevice.icdImporting")} (${modelImportElapsed.value}s)`;
  }
  if (!iec61850ConnectProgress.value) {
    return `${t("device.preparing")} 0% (${iec61850Elapsed.value}s)`;
  }
  return `${iec61850PhaseText.value} ${Math.round(modelProgressPercent.value)}% (${
    iec61850Elapsed.value
  }s)`;
});

let iec61850ProgressTimer: number | null = null;
let iec61850ProgressMode: "connect" | "discover" = "connect";
let iec61850ProgressRunId = 0;

const startIec61850ProgressPolling = (
  mode: "connect" | "discover" = "connect",
  initialProgress: IEC61850ConnectProgress | null = null,
) => {
  stopIec61850ProgressPolling();
  const runId = ++iec61850ProgressRunId;
  const initialActive =
    initialProgress?.active ?? initialProgress?.connecting ?? false;
  let observedCurrentDiscovery = mode === "discover" && initialActive;
  let observedOperationId = observedCurrentDiscovery
    ? initialProgress?.operation_id
    : undefined;
  let pollInFlight = false;
  iec61850ProgressMode = mode;
  iec61850Connecting.value = true;
  iec61850ConnectProgress.value = initialProgress || {
    phase: mode === "discover" ? "discovering" : "connecting",
    progress: 10,
    connecting: mode === "connect",
    active: true,
    operation: mode,
  };
  iec61850Elapsed.value = initialProgress?.elapsed_seconds || 0;
  iec61850ProgressStartedAt = Date.now() - iec61850Elapsed.value * 1000;
  iec61850ElapsedTimer = window.setInterval(() => {
    iec61850Elapsed.value = Math.max(
      iec61850Elapsed.value,
      Math.floor((Date.now() - iec61850ProgressStartedAt) / 1000),
    );
  }, 250);
  const pollProgress = async () => {
    if (pollInFlight) return;
    pollInFlight = true;
    try {
      const progress = await getIEC61850ConnectProgress(routeName.value);
      if (runId !== iec61850ProgressRunId) return;
      if (progress) {
        const active = progress.active ?? progress.connecting;
        const operationMatches =
          !progress.operation || progress.operation === mode;
        if (mode === "discover" && !observedCurrentDiscovery) {
          if (
            operationMatches &&
            active &&
            (progress.phase === "connecting" ||
              progress.phase === "discovering")
          ) {
            observedCurrentDiscovery = true;
            observedOperationId = progress.operation_id;
          } else {
            // 发现接口和进度接口并发启动时，先读到的可能是上一次任务快照。
            return;
          }
        }
        if (
          observedOperationId !== undefined &&
          progress.operation_id !== undefined &&
          progress.operation_id !== observedOperationId
        ) {
          return;
        }
        iec61850ConnectProgress.value = progress;
        if (progress.elapsed_seconds !== undefined) {
          iec61850Elapsed.value = Math.max(
            iec61850Elapsed.value,
            progress.elapsed_seconds,
          );
        }
        if (progress.phase === "done" || progress.phase === "failed") {
          stopIec61850ProgressPolling();
          if (iec61850ProgressMode === "connect" && progress.phase === "done") {
            deviceStatus.value = true;
            lastNotifyServerStatus = true;
            stableServerStatus = true;
            statusUnstableCount = STATUS_STABLE_THRESHOLD;
            ElMessage.success(t("device.iec61850DeviceConnectSuccess"));
            slaveRef.value?.reloadDatas();
            triggerSidebarRefresh(routeName.value);
          } else if (iec61850ProgressMode === "connect") {
            deviceStatus.value = false;
            lastNotifyServerStatus = false;
            stableServerStatus = false;
            statusUnstableCount = STATUS_STABLE_THRESHOLD;
            if (progress.error_code === "model_mismatch") {
              modelLoaded.value = false;
              triggerSidebarRefresh(routeName.value);
            }
            showErrorOnce(
              progress.message?.trim() ||
                t("device.iec61850DeviceConnectFailed"),
            );
          }
        }
      }
    } finally {
      pollInFlight = false;
    }
  };
  void pollProgress();
  iec61850ProgressTimer = window.setInterval(pollProgress, 500);
};

const stopIec61850ProgressPolling = () => {
  iec61850ProgressRunId++;
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
        showErrorOnce(t("device.stopDeviceFailed"));
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
        showErrorOnce(t("device.startDeviceFailed"));
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
  if (!routeName.value) return;
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

    // IEC61850 客户端：恢复正在执行的连接或发现任务（切页回来后继续显示同一计时）。
    if (String(communicationType.value) === "Iec61850Client") {
      const progress = await getIEC61850ConnectProgress(routeName.value);
      const active = progress?.active ?? progress?.connecting ?? false;
      if (progress && active) {
        const mode = progress.operation === "discover" ? "discover" : "connect";
        startIec61850ProgressPolling(mode, progress);
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
  const releaseAutoRefreshPause = acquireModelPause("iec61850-model-load");
  isModelProcessing.value = true;
  modelLoading.value = true;
  modelImportElapsed.value = 0;
  modelImportElapsedTimer = window.setInterval(() => {
    modelImportElapsed.value++;
  }, 1000);
  try {
    const result = await loadIEC61850Model(routeName.value);
    if (result) {
      modelLoaded.value = true;
      const path = result.icd_path || "";
      const msg = path
        ? t("device.modelLoadSuccessWithPath", {
            msg: t("device.modelLoadSuccess"),
            path,
          })
        : t("device.modelLoadSuccess");
      ElMessage.success(msg);
      triggerSidebarRefresh(routeName.value);
    } else {
      showErrorOnce(t("device.modelLoadFailed"));
    }
  } catch (error: any) {
    console.error(error);
    // 后端返回的错误消息已由全局拦截器处理
  } finally {
    releaseAutoRefreshPause();
    isModelProcessing.value = false;
    modelLoading.value = false;
    if (modelImportElapsedTimer) {
      clearInterval(modelImportElapsedTimer);
      modelImportElapsedTimer = null;
    }
  }
};

// IEC61850 模型导入：文件选择回调
const onIcdFileChange = () => {
  // 文件选中后自动开始导入
  if (!channelId.value) {
    showErrorOnce(t("device.modelLoadFailed"));
    return;
  }
  icdImportUploadRef.value
    ?.importIcd(channelId.value, "model_only")
    .catch(() => {});
};

// IEC61850 模型导入：点击按钮打开文件选择框
const handleImportModel = () => {
  icdImportUploadRef.value?.openFileDialog();
};

const handleDiscoverModel = async () => {
  // 1. 先检查是否有可用的模型缓存
  let useCache = false;
  try {
    const cacheInfo = await checkIEC61850ModelCache(routeName.value);
    if (cacheInfo?.cache_exists) {
      // 缓存存在，询问用户是否使用缓存还是重新发现
      const action = await ElMessageBox.confirm(
        t("device.cacheExistsMessage"),
        t("device.cacheExistsTitle"),
        {
          confirmButtonText: t("device.useCache"),
          cancelButtonText: t("device.redoDiscovery"),
          distinguishCancelAndClose: true,
          type: "info",
          roundButton: true,
        },
      ).catch((action: string | null) => action);

      if (action === "confirm") {
        useCache = true;
      } else if (action === "close") {
        // 点击右上角关闭按钮只关闭询问框，不应触发重新发现。
        return;
      }
    }
  } catch (e) {
    // 检查缓存出错时静默处理，继续正常的发现流程
    console.warn("检查模型缓存失败，将继续在线发现", e);
  }

  const releaseAutoRefreshPause = acquireModelPause("iec61850-model-discovery");

  if (useCache) {
    // 2. 使用缓存加载
    modelDiscovering.value = true;
    try {
      const success = await loadIEC61850ModelFromCache(routeName.value);
      if (success) {
        modelLoaded.value = true;
        ElMessage.success(
          t("device.modelLoadSuccess") + ` (${t("device.fromCache")})`,
        );
        await slaveRef.value?.reloadDatas();
        triggerSidebarRefresh(routeName.value);
      } else {
        showErrorOnce(t("device.modelLoadFailed"));
      }
    } catch (error) {
      console.error(error);
      // HTTP 拦截器已经展示后端的具体错误，避免再次弹出通用错误。
    } finally {
      releaseAutoRefreshPause();
      modelDiscovering.value = false;
    }
    return;
  }

  // 3. 重新发现（MMS 在线遍历）
  modelDiscovering.value = true;
  // 先让初始进度真正绘制一帧，避免极快任务在浏览器首次渲染前就结束。
  await nextTick();
  await new Promise<void>((resolve) =>
    window.requestAnimationFrame(() => resolve()),
  );
  // 先发起发现请求，让后端先开始跟踪进度（避免首次轮询的竞态条件）
  const discoverPromise = discoverIEC61850Model(
    routeName.value,
    HTTP_TIMEOUT_MODEL_DISCOVERY,
  );
  // 等后端 _begin_progress 执行完毕，确保首次轮询能通过守卫
  await new Promise<void>((resolve) => window.setTimeout(resolve, 100));
  // 启动进度轮询（此时后端已 active，首次轮询即可通过守卫）
  startIec61850ProgressPolling("discover");
  try {
    const success = await discoverPromise;
    if (success) {
      iec61850ConnectProgress.value = {
        phase: "done",
        progress: 100,
        connecting: false,
        active: false,
        operation: "discover",
        elapsed_seconds: iec61850Elapsed.value,
      };
      modelLoaded.value = true;
      ElMessage.success(t("device.modelLoadSuccess"));
      await slaveRef.value?.reloadDatas();
      triggerSidebarRefresh(routeName.value);
    } else {
      if (iec61850ConnectProgress.value) {
        iec61850ConnectProgress.value.phase = "failed";
      }
      showErrorOnce(t("device.modelLoadFailed"));
    }
  } catch (error) {
    console.error(error);
    if (iec61850ConnectProgress.value) {
      iec61850ConnectProgress.value.phase = "failed";
    }
  } finally {
    // 最终状态至少保留一帧，避免成功时直接从处理中跳到隐藏。
    await nextTick();
    await new Promise<void>((resolve) => window.setTimeout(resolve, 100));
    modelDiscovering.value = false;
    stopIec61850ProgressPolling();
    releaseAutoRefreshPause();
  }
};

let releaseModelImportPause: (() => void) | null = null;

const stopModelImportProgress = () => {
  if (modelImportElapsedTimer) {
    clearInterval(modelImportElapsedTimer);
    modelImportElapsedTimer = null;
  }
  releaseModelImportPause?.();
  releaseModelImportPause = null;
  modelImporting.value = false;
};

const onIcdImportStart = () => {
  stopModelImportProgress();
  releaseModelImportPause = acquireModelPause("iec61850-model-import");
  modelImporting.value = true;
  modelImportElapsed.value = 0;
  modelImportElapsedTimer = window.setInterval(() => {
    modelImportElapsed.value++;
  }, 1000);
};

// IEC61850 模型导入：成功回调
const onIcdImportSuccess = () => {
  stopModelImportProgress();
  modelLoaded.value = true;
  ElMessage.success(t("device.modelLoadSuccess"));
  triggerSidebarRefresh(routeName.value);
};

// IEC61850 模型导入：失败回调
const onIcdImportError = () => {
  stopModelImportProgress();
  // 导入请求错误已由 HTTP 拦截器展示，这里只负责结束进度状态。
};

// 状态轮询定时器
let statusPollTimer: number | null = null;
let statusPollInFlight = false;
const STATUS_POLL_INTERVAL = 1000; // 1秒轮询一次

// 连接状态防抖：避免因连接状态抖动（如客户端重连过程中反复连接成功又断开）导致不停弹窗
let lastNotifyServerStatus: boolean | null = null; // 上一次弹窗通知时的连接状态
let stableServerStatus: boolean | null = null; // 当前稳定的连接状态
let statusUnstableCount = 0; // 状态不稳定计数（连续变化的次数）
const STATUS_STABLE_THRESHOLD = 3; // 连续3次状态一致才认为状态稳定
let prevServerStatus: boolean | null = null; // 上一次轮询的连接状态（用于检测即时变化，如 IEC 61850 测点刷新）

// 仅获取状态（不更新其他信息，减少开销）
const fetchDeviceStatus = async () => {
  if (!routeName.value) return;
  if (statusPollInFlight) return;
  // 导入 ICD 文件期间暂停轮询，避免设备重建设置 404 导致弹窗误报断连
  if (isAutoRefreshPaused.value) return;
  statusPollInFlight = true;
  try {
    const info = await getDeviceInfo(routeName.value);
    const serverStatus = info.get("server_status");

    // 同步显示参数（波特率可能在运行中被"更改通信速率"命令更新）
    baudrate.value = info.get("baudrate") || 9600;

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
      !iec61850Connecting.value &&
      lastNotifyServerStatus !== serverStatus
    ) {
      lastNotifyServerStatus = serverStatus;
      if (serverStatus === true) {
        ElMessage.success(
          t("device.deviceConnected", { name: routeName.value }),
        );
      } else {
        ElMessage.warning(
          t("device.deviceDisconnected", { name: routeName.value }),
        );
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
  } finally {
    statusPollInFlight = false;
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
  stopModelImportProgress();
  for (const release of [...modelPauseReleases]) release();
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
  { immediate: true },
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
    flex: 3 1 0;
  }

  .sim-section {
    min-width: 0;
    flex: 2 1 0;
  }

  .model-controls,
  .sim-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }

  .model-controls {
    flex-wrap: nowrap;

    .button {
      min-width: 96px;
      padding-right: 12px;
      padding-left: 12px;
      flex-shrink: 0;
    }
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
  background-color: #6366f1;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.btn-discover-model {
  background-color: #14b8a6;
  box-shadow: 0 4px 12px rgba(20, 184, 166, 0.25);
}

.progress-row {
  position: relative;

  .model-progress-text {
    position: absolute;
    left: 50%;
    top: 50%;
    z-index: 1;
    transform: translate(-50%, -50%);
    max-width: calc(100% - 32px);
    overflow: hidden;
    color: var(--el-text-color-primary);
    font-size: 12px;
    line-height: 18px;
    white-space: nowrap;
    text-overflow: ellipsis;
    text-shadow:
      0 0 3px var(--el-bg-color),
      0 0 3px var(--el-bg-color);
    pointer-events: none;
  }

  .model-import-progress-hint {
    width: 100%;
    margin: -4px 0 0;
    color: var(--text-secondary);
    font-size: 12px;
    text-align: center;
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
    flex-direction: column;

    .model-section,
    .sim-section {
      padding: 12px 16px;
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

    .model-controls {
      flex-wrap: wrap;
    }

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
