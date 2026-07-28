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
  getDeviceInfo,
  getDeviceTable,
  getIEC61850ConnectProgress,
} from "@/api/deviceApi";
import { getIEC61850TableData, iec61850ReadPoints } from "@/api/channelApi";
import { readSinglePoint } from "@/api/pointApi";
import {
  TABLE_REFRESH_INTERVAL,
  READ_PROGRESS_DELAY,
  SINGLE_READ_PROGRESS_DELAY,
} from "@/constants";
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
  let datasetAutoReadTimer: ReturnType<typeof setTimeout> | null = null;
  let datasetReadInFlight = false;

  // 逐点自动读取定时器
  let singlePointAutoReadTimer: any = null;

  // 判断是否需要显示自动读取控件
  const needsAutoReadControls = computed(() => {
    const protocolStr = String(protocolType.value);
    if (isIec104Protocol(protocolStr)) return false;
    return connType.value === 0 || connType.value === 1;
  });

  // 判断是否为 IEC61850 筛选模式
  const isIec61850Filtered = () => {
    return (
      isIec61850Protocol(String(protocolType.value)) &&
      channelId.value !== null &&
      !!iec61850Category.value
    );
  };

  const startAutoRefresh = () => {
    if (timer.value) return;
    const refresh = async () => {
      // 导入文件时暂停轮询，避免干扰上传和超时
      if (
        isAutoRefreshPaused.value ||
        refreshInFlight ||
        isIec61850DatasetPage()
      )
        return;
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

  const stopDatasetAutoReadTimer = () => {
    if (datasetAutoReadTimer) {
      clearTimeout(datasetAutoReadTimer);
      datasetAutoReadTimer = null;
    }
  };

  const readCurrentDataset = async (showSuccess: boolean) => {
    if (
      !isIec61850DatasetPage() ||
      datasetReadInFlight ||
      isAutoRefreshPaused.value
    )
      return;
    datasetReadInFlight = true;
    datasetReading.value = true;
    try {
      await fetchDeviceTable(
        routeName.value,
        currentSlaveId.value,
        searchQuery.value[currentSlaveId.value] || "",
        pageIndex.value,
        pageSize.value,
      );
      if (showSuccess) ElMessage.success(t("autoRead.datasetReadComplete"));
    } finally {
      datasetReadInFlight = false;
      datasetReading.value = false;
    }
  };

  // 使用递归 setTimeout，保证慢速 MMS 读取不会并发重叠。
  const scheduleDatasetAutoRead = (delay = datasetReadInterval.value) => {
    stopDatasetAutoReadTimer();
    if (!datasetAutoRead.value || !isIec61850DatasetPage()) return;
    datasetAutoReadTimer = setTimeout(
      async () => {
        await readCurrentDataset(false);
        scheduleDatasetAutoRead();
      },
      Math.max(delay, 1),
    );
  };

  const handleDatasetAutoReadChange = async (enabled: boolean) => {
    if (enabled) {
      const deviceInfo = await getDeviceInfo(routeName.value);
      if (!deviceInfo?.get("server_status")) {
        datasetAutoRead.value = false;
        showErrorOnce(t("autoRead.deviceNotConnectedForDataset"));
        return;
      }
      datasetAutoRead.value = true;
      ElMessage.success(t("autoRead.datasetAutoReadEnabled"));
      scheduleDatasetAutoRead(0);
    } else {
      datasetAutoRead.value = false;
      stopDatasetAutoReadTimer();
      ElMessage.success(t("autoRead.datasetAutoReadStopped"));
    }
  };

  const handleDatasetIntervalChange = (val: string | number) => {
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
    if (datasetAutoRead.value) scheduleDatasetAutoRead();
  };

  const handleDatasetManualRead = async () => {
    if (datasetReadInFlight) return;
    const deviceInfo = await getDeviceInfo(routeName.value);
    if (!deviceInfo?.get("server_status")) {
      showErrorOnce(t("autoRead.deviceNotConnectedForDataset"));
      return;
    }
    await readCurrentDataset(true);
  };

  /** 停止所有自动读取（批量+逐点） */
  const stopAllAutoRead = async () => {
    await stopAutoRead(routeName.value).catch(() => {});
    stopSinglePointAutoRead();
  };

  const handleAutoReadChange = async (enabled: boolean) => {
    if (enabled) {
      if (readMode.value === "batch" && !isDlt645.value) {
        await startAutoRead(routeName.value);
        ElMessage.success(t("autoRead.batchAutoReadEnabled"));
      } else {
        startSinglePointAutoRead();
        ElMessage.success(t("autoRead.singleAutoReadEnabled"));
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
    await stopAllAutoRead();
    if (readMode.value === "batch" && !isDlt645.value) {
      await startAutoRead(routeName.value);
    } else {
      startSinglePointAutoRead();
    }
  };

  const handleIntervalChange = (val: string | number) => {
    const numVal = Number(val);
    if (!isNaN(numVal) && numVal > 0) {
      const exists = intervalOptions.value.some((opt) => opt.value === numVal);
      if (!exists) {
        intervalOptions.value.push({ label: `${numVal}ms`, value: numVal });
        intervalOptions.value.sort((a, b) => a.value - b.value);
      }
      readInterval.value = numVal;
    }
  };

  /** 启动逐点自动读取循环 */
  const startSinglePointAutoRead = () => {
    isReading.value = true;
    cancelRead.value = false;
    successCount.value = 0;
    failCount.value = 0;
    readProgress.value = 0;
    progressMessage.value = t("autoRead.singleAutoReadingProgress");
    doSinglePointReadCycle();
  };

  /** 停止逐点自动读取 */
  const stopSinglePointAutoRead = () => {
    if (singlePointAutoReadTimer) {
      clearTimeout(singlePointAutoReadTimer);
      singlePointAutoReadTimer = null;
    }
    cancelRead.value = true;
    isReading.value = false;
    readProgress.value = 0;
    successCount.value = 0;
    failCount.value = 0;
    progressMessage.value = "";
  };

  /** 执行一轮逐点读取 */
  const doSinglePointReadCycle = async () => {
    if (!isAutoRead.value || cancelRead.value) {
      stopSinglePointAutoRead();
      return;
    }

    try {
      // 获取测点列表
      const data = await getDeviceTable(
        routeName.value,
        currentSlaveId.value,
        "",
        1,
        10000,
        pointTypes.value,
        null,
        null,
        [],
        dlt645Prefix.value,
        dlt645Settlement.value,
      );
      const allRows: any[][] = data.get("table_data") || [];
      const totalPoints = allRows.length;

      if (totalPoints === 0) {
        singlePointAutoReadTimer = setTimeout(doSinglePointReadCycle, 2000);
        return;
      }

      successCount.value = 0;
      failCount.value = 0;

      for (let i = 0; i < totalPoints; i++) {
        if (!isAutoRead.value || cancelRead.value) break;

        const row = allRows[i];
        const pointCode = row[6];
        const pointName = row[5];
        progressMessage.value = t("autoRead.autoReading", {
          current: i + 1,
          total: totalPoints,
          name: pointName,
        });

        try {
          const value = await readSinglePoint(
            routeName.value,
            pointCode,
            isDlt645.value ? undefined : currentSlaveId.value,
          );
          if (value !== null) {
            successCount.value++;
            // 实时更新表格中的显示值
            if (tableDataMap.value[currentSlaveId.value]) {
              const displayRow = tableDataMap.value[
                currentSlaveId.value
              ].tableData.find((r) => r[6] === pointCode);
              if (displayRow) displayRow[8] = value;
            }
          } else {
            failCount.value++;
          }
        } catch (e) {
          failCount.value++;
        }

        if (readInterval.value > 0) {
          await new Promise((resolve) =>
            setTimeout(resolve, readInterval.value),
          );
        }
        readProgress.value = Math.floor(((i + 1) / totalPoints) * 100);
      }
    } catch (e) {
      console.error("逐点自动读取错误:", e);
    }

    // 循环下一轮
    if (isAutoRead.value && !cancelRead.value) {
      const cycleInterval = Math.max(readInterval.value * 2, 1000);
      singlePointAutoReadTimer = setTimeout(
        doSinglePointReadCycle,
        cycleInterval,
      );
    } else {
      stopSinglePointAutoRead();
    }
  };

  const handleManualRead = async () => {
    if (isReading.value) {
      cancelRead.value = true;
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

  // 批量读取模式
  const handleBatchRead = async () => {
    progressMessage.value = t("autoRead.readingRegisters");
    try {
      if (
        isIec61850Protocol(String(protocolType.value)) &&
        channelId.value !== null
      ) {
        progressMessage.value = t("autoRead.planningIec61850Batch");
        readProgress.value = 1;

        // 先发起批读，再并行轮询 Handler 的进度快照。后端把阻塞的 MMS
        // 调用放在线程中执行，因此每完成一个 DataSet 都能及时刷新到界面。
        const readPromise = iec61850ReadPoints(
          channelId.value,
          iec61850Category.value,
          iec61850Item.value,
          readInterval.value,
        );
        let polling = false;
        const pollReadProgress = async () => {
          if (polling) return;
          polling = true;
          try {
            const snapshot = await getIEC61850ConnectProgress(routeName.value);
            if (snapshot?.operation === "read") {
              // 网络响应可能乱序，始终保持进度单调递增。
              readProgress.value = Math.max(
                readProgress.value,
                Math.min(snapshot.progress, 99),
              );
              if (snapshot.message) progressMessage.value = snapshot.message;
            }
          } finally {
            polling = false;
          }
        };
        const progressTimer = window.setInterval(() => {
          void pollReadProgress();
        }, 100);
        void pollReadProgress();

        try {
          const result = await readPromise;
          if (result) {
            successCount.value = result.success;
            failCount.value = result.fail;
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
          } else {
            progressMessage.value = t("autoRead.batchReadCompleteSimple");
            ElMessage.success(t("autoRead.batchReadCompleteSimple"));
          }
        } finally {
          window.clearInterval(progressTimer);
        }
        await fetchDeviceTable(
          routeName.value,
          currentSlaveId.value,
          searchQuery.value[currentSlaveId.value] || "",
          pageIndex.value,
          pageSize.value,
        );
        readProgress.value = 100;
        return;
      }

      const result = await manualRead(routeName.value, readInterval.value);
      if (result) {
        if (typeof result === "object" && "success" in result) {
          successCount.value = result.success;
          failCount.value = result.fail;
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
        } else {
          readProgress.value = 100;
          progressMessage.value = t("autoRead.batchReadCompleteSimple");
          ElMessage.success(t("autoRead.batchReadCompleteSimple"));
        }
        await fetchDeviceTable(
          routeName.value,
          currentSlaveId.value,
          searchQuery.value[currentSlaveId.value] || "",
          pageIndex.value,
          pageSize.value,
        );
        readProgress.value = 100;
      }
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

  // 逐点读取模式
  const handleSinglePointRead = async () => {
    progressMessage.value = t("autoRead.fetchingPointList");
    try {
      let allRows: any[][] = [];
      if (isIec61850Filtered() && channelId.value !== null) {
        const data = await getIEC61850TableData(
          channelId.value,
          iec61850Category.value,
          iec61850Item.value,
          null,
          1,
          10000,
          pointTypes.value,
        );
        if (data) allRows = data.get("table_data") || [];
      } else {
        const data = await getDeviceTable(
          routeName.value,
          currentSlaveId.value,
          "",
          1,
          10000,
          pointTypes.value,
          null,
          null,
          [],
          dlt645Prefix.value,
          dlt645Settlement.value,
        );
        allRows = data.get("table_data") || [];
      }

      const totalPoints = allRows.length;
      if (totalPoints === 0) {
        ElMessage.warning(t("autoRead.noPointToRead"));
        isReading.value = false;
        return;
      }

      progressMessage.value = t("autoRead.startingSingleRead");
      for (let i = 0; i < totalPoints; i++) {
        if (cancelRead.value) {
          progressMessage.value = t("autoRead.readCancelled");
          ElMessage.warning(t("autoRead.operationCancelled"));
          break;
        }

        const row = allRows[i];
        const pointCode = row[6];
        const pointName = row[5];
        progressMessage.value = t("autoRead.singleReadProgress", {
          current: i + 1,
          total: totalPoints,
          name: pointName,
        });

        try {
          const value = await readSinglePoint(
            routeName.value,
            pointCode,
            isDlt645.value ? undefined : currentSlaveId.value,
          );
          if (value !== null) {
            successCount.value++;
            if (tableDataMap.value[currentSlaveId.value]) {
              const displayRow = tableDataMap.value[
                currentSlaveId.value
              ].tableData.find((r) => r[6] === pointCode);
              if (displayRow) displayRow[8] = value;
            }
          } else {
            failCount.value++;
          }
        } catch (e) {
          failCount.value++;
        }

        if (readInterval.value > 0) {
          await new Promise((resolve) =>
            setTimeout(resolve, readInterval.value),
          );
        }
        readProgress.value = Math.floor(((i + 1) / totalPoints) * 100);
      }

      if (!cancelRead.value) {
        progressMessage.value = t("autoRead.readComplete", {
          success: successCount.value,
          fail: failCount.value,
        });
        ElMessage.success(
          t("autoRead.singleReadComplete", {
            success: successCount.value,
            fail: failCount.value,
          }),
        );
      }
    } catch (e) {
      console.error("逐点读取失败:", e);
    } finally {
      if (cancelRead.value) {
        isReading.value = false;
        readProgress.value = 0;
        successCount.value = 0;
        failCount.value = 0;
      } else {
        setTimeout(() => {
          isReading.value = false;
          readProgress.value = 0;
          successCount.value = 0;
          failCount.value = 0;
        }, SINGLE_READ_PROGRESS_DELAY);
      }
    }
  };

  const fetchAutoReadStatus = async () => {
    const status = await getAutoReadStatus(routeName.value);
    if (isDlt645.value) {
      readMode.value = "single";
      if (status) await stopAutoRead(routeName.value);
      isAutoRead.value = false;
      return;
    }
    isAutoRead.value = status;
    if (status) startAutoRefresh();
  };

  watch([iec61850Category, iec61850Item], () => {
    if (!isIec61850DatasetPage()) {
      datasetAutoRead.value = false;
      stopDatasetAutoReadTimer();
    } else if (datasetAutoRead.value) {
      scheduleDatasetAutoRead(0);
    }
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

  onActivated(() => startAutoRefresh());
  onDeactivated(() => {
    stopAutoRefresh();
    datasetAutoRead.value = false;
    stopDatasetAutoReadTimer();
  });
  onUnmounted(() => {
    stopAutoRefresh();
    stopDatasetAutoReadTimer();
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
