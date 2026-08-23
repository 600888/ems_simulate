/**
 * 自动刷新与读取控制 composable
 * 从 Slave.vue 中提取的自动刷新、手动读取逻辑
 * 支持暂停（导入文件时暂停自动轮询）
 */

import {
  ref,
  computed,
  onActivated,
  onDeactivated,
  onUnmounted,
  watch,
} from "vue";
import { useI18n } from "vue-i18n";
import { isAutoRefreshPaused } from "@/composables/autoRefreshGate";
import { ElMessage } from "element-plus";
import { showErrorOnce } from "@/api/http";
import {
  getAutoReadStatus,
  startAutoRead,
  stopAutoRead,
  manualRead,
  getManualReadStatus,
  stopManualRead,
  getDeviceInfo,
} from "@/api/deviceApi";
import type { AutoReadConfig, AutoReadStatus } from "@/api/deviceApi";
import { TABLE_REFRESH_INTERVAL, READ_PROGRESS_DELAY } from "@/constants";
import {
  isDlt645Protocol,
  isIec61850Protocol,
  isIec104Protocol,
} from "@/constants/protocol";

interface AutoReadOptions {
  routeName: Ref<string>;
  currentSlaveId: Ref<number>;
  searchQuery: Ref<Record<number, string>>;
  pageIndex: Ref<number>;
  pageSize: Ref<number>;
  pointTypes: Ref<number[]>;
  orderBy: Ref<string | null>;
  orderDirection: Ref<string | null>;
  protocolType: Ref<number | string>;
  connType: Ref<number>;
  channelId: Ref<number | null>;
  iec61850Category: Ref<string>;
  iec61850Item: Ref<string>;
  dlt645Prefix: Ref<number | null>;
  dlt645Settlement: Ref<number | null>;
  tableDataMap: Ref<
    Record<number, { tableHeader: string[]; tableData: any[][]; total: number }>
  >;
  total: Ref<number>;
  fetchDeviceTable: (
    name: string,
    sid: number,
    q: string,
    pi: number,
    ps: number,
  ) => Promise<void>;
}

import type { Ref } from "vue";

export function useAutoRead(options: AutoReadOptions) {
  const {
    routeName,
    currentSlaveId,
    searchQuery,
    pageIndex,
    pageSize,
    pointTypes,
    orderBy,
    orderDirection,
    protocolType,
    connType,
    channelId,
    iec61850Category,
    iec61850Item,
    dlt645Prefix,
    dlt645Settlement,
    tableDataMap,
    total,
    fetchDeviceTable,
  } = options;

  const { t } = useI18n();

  const isAutoRead = ref(false);
  const timer = ref<any>(null);
  let refreshInFlight = false;
  const isReading = ref(false);
  const cancelRead = ref(false);
  const successCount = ref(0);
  const failCount = ref(0);
  const readProgress = ref(0);
  const progressMessage = ref("");

  const readInterval = ref(10);
  const intervalOptions = ref([
    { label: "1ms", value: 1 },
    { label: "5ms", value: 5 },
    { label: "10ms", value: 10 },
    { label: "50ms", value: 50 },
    { label: "100ms", value: 100 },
    { label: "200ms", value: 200 },
    { label: "500ms", value: 500 },
    { label: "1000ms", value: 1000 },
    { label: "2000ms", value: 2000 },
    { label: "5000ms", value: 5000 },
  ]);

  const readMode = ref<"batch" | "single">("batch");
  const readModeOptions = [
    { label: t("autoRead.batch"), value: "batch" },
    { label: t("autoRead.single"), value: "single" },
  ];
  const isDlt645 = computed(() => isDlt645Protocol(protocolType.value));

  // DataSet 页面使用独立状态，避免开关设备级自动读取。
  const datasetAutoRead = ref(false);
  const datasetReading = ref(false);
  const datasetReadInterval = ref(1000);
  const datasetIntervalOptions = ref([
    { label: "500ms", value: 500 },
    { label: "1000ms", value: 1000 },
    { label: "2000ms", value: 2000 },
    { label: "5000ms", value: 5000 },
    { label: "10000ms", value: 10000 },
    { label: "30000ms", value: 30000 },
  ]);
  let datasetReadInFlight = false;
  let autoReadStatusTimer: ReturnType<typeof setInterval> | null = null;
  let statusInFlight = false;

  // 判断是否需要显示自动读取控件
  const needsAutoReadControls = computed(() => {
    const protocolStr = String(protocolType.value);
    if (isIec104Protocol(protocolStr)) return false;
    return connType.value === 0 || connType.value === 1;
  });

  const startAutoRefresh = () => {
    if (timer.value) return;
    const refresh = async () => {
      // 导入文件时暂停轮询，避免干扰上传和超时
      if (isAutoRefreshPaused.value || refreshInFlight) return;
      refreshInFlight = true;
      try {
        await fetchDeviceTable(
          routeName.value,
          currentSlaveId.value,
          searchQuery.value[currentSlaveId.value] || "",
          pageIndex.value,
          pageSize.value,
        );
      } finally {
        refreshInFlight = false;
      }
    };
    timer.value = setInterval(() => void refresh(), TABLE_REFRESH_INTERVAL);
  };

  const isIec61850DatasetPage = () =>
    isIec61850Protocol(String(protocolType.value)) &&
    iec61850Category.value === "DataSets" &&
    !!iec61850Item.value;

  const stopAutoRefresh = () => {
    if (timer.value) {
      clearInterval(timer.value);
      timer.value = null;
    }
  };

  const applyAutoReadStatus = (status: AutoReadStatus) => {
    const running = status.state === "running";
    const isCurrentDataset =
      status.mode === "dataset" && status.config?.item === iec61850Item.value;

    datasetAutoRead.value = running && isCurrentDataset;
    isAutoRead.value = running && status.mode !== "dataset";
    if (running && (status.mode === "batch" || status.mode === "single")) {
      readMode.value = status.mode;
    }
    if (running && status.config?.cycle_interval_ms) {
      if (status.mode === "dataset") {
        datasetReadInterval.value = status.config.cycle_interval_ms;
      } else if (status.mode === "batch") {
        readInterval.value = status.config.cycle_interval_ms;
      } else if (status.config.request_interval_ms !== undefined) {
        readInterval.value = status.config.request_interval_ms;
      }
    }
    if (status.state === "failed") {
      showErrorOnce(status.last_error || t("autoRead.readError"));
    }
  };

  const fetchAutoReadStatus = async () => {
    if (!routeName.value || statusInFlight) return;
    statusInFlight = true;
    try {
      const status = await getAutoReadStatus(routeName.value);
      applyAutoReadStatus(status);
      if (status.state === "running" || status.state === "stopping") {
        startAutoReadStatusPolling();
      } else {
        stopAutoReadStatusPolling();
      }
    } finally {
      statusInFlight = false;
    }
  };

  const startAutoReadStatusPolling = () => {
    if (autoReadStatusTimer) return;
    autoReadStatusTimer = setInterval(() => void fetchAutoReadStatus(), 1000);
  };

  const stopAutoReadStatusPolling = () => {
    if (autoReadStatusTimer) {
      clearInterval(autoReadStatusTimer);
      autoReadStatusTimer = null;
    }
  };

  const stopAllAutoRead = async () => {
    const status = await stopAutoRead(routeName.value).catch(() => null);
    isAutoRead.value = false;
    datasetAutoRead.value = false;
    if (status) applyAutoReadStatus(status);
    startAutoReadStatusPolling();
  };

  const stopAndWaitForIdle = async () => {
    await stopAllAutoRead();
    for (let attempt = 0; attempt < 40; attempt++) {
      const status = await getAutoReadStatus(routeName.value);
      applyAutoReadStatus(status);
      if (status.state === "idle" || status.state === "failed") return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("自动读取任务仍在停止中，请稍后重试");
  };

  const buildStandardAutoReadConfig = (): AutoReadConfig => {
    const mode = isDlt645.value ? "single" : readMode.value;
    return {
      mode,
      cycle_interval_ms:
        mode === "single"
          ? Math.max(readInterval.value * 2, 1000)
          : Math.max(readInterval.value, 100),
      request_interval_ms: mode === "single" ? readInterval.value : 0,
      slave_id:
        mode === "single" && !isDlt645.value ? currentSlaveId.value : undefined,
      channel_id: channelId.value ?? undefined,
      category: iec61850Category.value,
      item: iec61850Item.value,
      point_types: pointTypes.value,
      dlt645_prefix: dlt645Prefix.value,
      dlt645_settlement: dlt645Settlement.value,
    };
  };

  const handleDatasetAutoReadChange = async (enabled: boolean) => {
    if (enabled) {
      const deviceInfo = await getDeviceInfo(routeName.value);
      if (!deviceInfo?.get("server_status")) {
        datasetAutoRead.value = false;
        showErrorOnce(t("autoRead.deviceNotConnectedForDataset"));
        return;
      }
      await stopAndWaitForIdle();
      const status = await startAutoRead(routeName.value, {
        mode: "dataset",
        cycle_interval_ms: Math.max(datasetReadInterval.value, 100),
        request_interval_ms: 0,
        channel_id: channelId.value ?? undefined,
        category: iec61850Category.value,
        item: iec61850Item.value,
        point_types: pointTypes.value,
      });
      applyAutoReadStatus(status);
      startAutoReadStatusPolling();
      ElMessage.success(t("autoRead.datasetAutoReadEnabled"));
    } else {
      await stopAllAutoRead();
      ElMessage.success(t("autoRead.datasetAutoReadStopped"));
    }
  };

  const handleDatasetIntervalChange = async (val: string | number) => {
    const interval = Number(val);
    if (!Number.isFinite(interval) || interval <= 0) return;
    if (
      !datasetIntervalOptions.value.some((option) => option.value === interval)
    ) {
      datasetIntervalOptions.value.push({
        label: `${interval}ms`,
        value: interval,
      });
      datasetIntervalOptions.value.sort((a, b) => a.value - b.value);
    }
    datasetReadInterval.value = interval;
    if (datasetAutoRead.value) {
      await handleDatasetAutoReadChange(true);
    }
  };

  const handleDatasetManualRead = async () => {
    if (datasetReadInFlight) return;
    const deviceInfo = await getDeviceInfo(routeName.value);
    if (!deviceInfo?.get("server_status")) {
      showErrorOnce(t("autoRead.deviceNotConnectedForDataset"));
      return;
    }
    if (channelId.value === null || !isIec61850DatasetPage()) return;
    datasetReadInFlight = true;
    datasetReading.value = true;
    try {
      isReading.value = true;
      cancelRead.value = false;
      await runBackgroundManualRead({
        mode: "dataset",
        cycle_interval_ms: 100,
        request_interval_ms: 0,
        channel_id: channelId.value,
        category: iec61850Category.value,
        item: iec61850Item.value,
        point_types: pointTypes.value,
      });
      await fetchDeviceTable(
        routeName.value,
        currentSlaveId.value,
        searchQuery.value[currentSlaveId.value] || "",
        pageIndex.value,
        pageSize.value,
      );
      ElMessage.success(t("autoRead.datasetReadComplete"));
    } finally {
      isReading.value = false;
      datasetReadInFlight = false;
      datasetReading.value = false;
    }
  };

  const handleAutoReadChange = async (enabled: boolean) => {
    if (enabled) {
      try {
        await stopAndWaitForIdle();
        const status = await startAutoRead(
          routeName.value,
          buildStandardAutoReadConfig(),
        );
        applyAutoReadStatus(status);
        startAutoReadStatusPolling();
        if (readMode.value === "batch" && !isDlt645.value) {
          ElMessage.success(t("autoRead.batchAutoReadEnabled"));
        } else {
          ElMessage.success(t("autoRead.singleAutoReadEnabled"));
        }
      } catch (error) {
        isAutoRead.value = false;
        throw error;
      }
    } else {
      await stopAllAutoRead();
      ElMessage.success(t("autoRead.autoReadStopped"));
    }
  };

  /** 模式切换时由模板 `@change` 调用，确保先完全停止再重新启动 */
  const handleReadModeChange = async () => {
    if (isDlt645.value) {
      readMode.value = "single";
    }
    if (!isAutoRead.value) return;
    await stopAndWaitForIdle();
    const status = await startAutoRead(
      routeName.value,
      buildStandardAutoReadConfig(),
    );
    applyAutoReadStatus(status);
    startAutoReadStatusPolling();
  };

  const handleIntervalChange = async (val: string | number) => {
    const numVal = Number(val);
    if (!isNaN(numVal) && numVal > 0) {
      const exists = intervalOptions.value.some((opt) => opt.value === numVal);
      if (!exists) {
        intervalOptions.value.push({ label: `${numVal}ms`, value: numVal });
        intervalOptions.value.sort((a, b) => a.value - b.value);
      }
      readInterval.value = numVal;
      if (isAutoRead.value) {
        await stopAndWaitForIdle();
        const status = await startAutoRead(
          routeName.value,
          buildStandardAutoReadConfig(),
        );
        applyAutoReadStatus(status);
        startAutoReadStatusPolling();
      }
    }
  };

  const handleManualRead = async () => {
    if (isReading.value) {
      cancelRead.value = true;
      await stopManualRead(routeName.value).catch(() => null);
      return;
    }

    const deviceInfo = await getDeviceInfo(routeName.value);
    const serverStatus = deviceInfo?.get("server_status");
    if (!serverStatus) {
      showErrorOnce(t("autoRead.deviceNotConnectedForRead"));
      return;
    }

    isReading.value = true;
    cancelRead.value = false;
    readProgress.value = 0;
    successCount.value = 0;
    failCount.value = 0;

    if (readMode.value === "batch" && !isDlt645.value) {
      await handleBatchRead();
    } else {
      await handleSinglePointRead();
    }
  };

  const runBackgroundManualRead = async (config: AutoReadConfig) => {
    let status = await manualRead(routeName.value, config);
    while (status.state === "running" || status.state === "stopping") {
      if (cancelRead.value && status.state === "running") {
        status = await stopManualRead(routeName.value);
      } else {
        await new Promise((resolve) => setTimeout(resolve, 200));
        status = await getManualReadStatus(routeName.value);
      }
      successCount.value = status.success;
      failCount.value = status.fail;
      readProgress.value = status.total
        ? Math.floor((status.current / status.total) * 100)
        : 0;
    }
    if (status.state === "failed") {
      throw new Error(status.last_error || t("autoRead.readError"));
    }
    successCount.value = status.success;
    failCount.value = status.fail;
    readProgress.value = 100;
    return status;
  };

  // 批量读取由后端单次任务执行；前端只查询任务状态，不重复触发读取接口。
  const handleBatchRead = async () => {
    progressMessage.value = t("autoRead.readingRegisters");
    try {
      const result = await runBackgroundManualRead({
        mode: "batch",
        cycle_interval_ms: 100,
        request_interval_ms: readInterval.value,
        channel_id: channelId.value ?? undefined,
        category: iec61850Category.value,
        item: iec61850Item.value,
        point_types: pointTypes.value,
      });
      progressMessage.value = t("autoRead.batchReadProgress", {
        success: result.success,
        fail: result.fail,
      });
      ElMessage.success(
        t("autoRead.batchReadComplete", {
          success: result.success,
          fail: result.fail,
        }),
      );
      await fetchDeviceTable(
        routeName.value,
        currentSlaveId.value,
        searchQuery.value[currentSlaveId.value] || "",
        pageIndex.value,
        pageSize.value,
      );
    } catch (e) {
      console.error("批量读取失败:", e);
      progressMessage.value = t("autoRead.readError");
    } finally {
      setTimeout(() => {
        isReading.value = false;
        readProgress.value = 0;
      }, READ_PROGRESS_DELAY);
    }
  };

  // 逐点读取同样由后端单次任务执行；前端不再拉全量点表并逐点调用接口。
  const handleSinglePointRead = async () => {
    progressMessage.value = t("autoRead.startingSingleRead");
    try {
      const result = await runBackgroundManualRead({
        mode: "single",
        cycle_interval_ms: 100,
        request_interval_ms: readInterval.value,
        slave_id: currentSlaveId.value,
        channel_id: channelId.value ?? undefined,
        category: iec61850Category.value,
        item: iec61850Item.value,
        point_types: pointTypes.value,
        dlt645_prefix: dlt645Prefix.value,
        dlt645_settlement: dlt645Settlement.value,
      });
      if (cancelRead.value) {
        progressMessage.value = t("autoRead.readCancelled");
        ElMessage.warning(t("autoRead.operationCancelled"));
        return;
      }
      progressMessage.value = t("autoRead.readComplete", {
        success: result.success,
        fail: result.fail,
      });
      ElMessage.success(
        t("autoRead.singleReadComplete", {
          success: result.success,
          fail: result.fail,
        }),
      );
      await fetchDeviceTable(
        routeName.value,
        currentSlaveId.value,
        searchQuery.value[currentSlaveId.value] || "",
        pageIndex.value,
        pageSize.value,
      );
    } catch (e) {
      console.error("逐点读取失败:", e);
      progressMessage.value = t("autoRead.readError");
    } finally {
      const resetDelay = cancelRead.value ? 0 : READ_PROGRESS_DELAY;
      setTimeout(() => {
        isReading.value = false;
        readProgress.value = 0;
        successCount.value = 0;
        failCount.value = 0;
      }, resetDelay);
    }
  };

  watch([iec61850Category, iec61850Item], () => {
    void fetchAutoReadStatus();
  });

  watch(
    isDlt645,
    (enabled) => {
      if (enabled) readMode.value = "single";
    },
    { immediate: true },
  );

  const formatProgress = (percentage: number) => {
    return percentage === 100 ? t("autoRead.completed") : `${percentage}%`;
  };

  onActivated(() => {
    startAutoRefresh();
    void fetchAutoReadStatus();
    startAutoReadStatusPolling();
  });
  onDeactivated(() => {
    stopAutoRefresh();
    stopAutoReadStatusPolling();
  });
  onUnmounted(() => {
    stopAutoRefresh();
    stopAutoReadStatusPolling();
  });

  return {
    isAutoRead,
    isReading,
    cancelRead,
    successCount,
    failCount,
    readProgress,
    progressMessage,
    readInterval,
    intervalOptions,
    readMode,
    readModeOptions,
    datasetAutoRead,
    datasetReading,
    datasetReadInterval,
    datasetIntervalOptions,
    needsAutoReadControls,
    startAutoRefresh,
    stopAutoRefresh,
    handleAutoReadChange,
    handleIntervalChange,
    handleReadModeChange,
    handleManualRead,
    handleDatasetAutoReadChange,
    handleDatasetIntervalChange,
    handleDatasetManualRead,
    fetchAutoReadStatus,
    formatProgress,
  };
}
