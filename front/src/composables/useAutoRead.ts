/**
 * 自动刷新与读取控制 composable
 * 从 Slave.vue 中提取的自动刷新、手动读取逻辑
 * 支持暂停（导入文件时暂停自动轮询）
 */

import { ref, computed, onActivated, onDeactivated, onUnmounted } from "vue";

// ===== 全局暂停标志：文件导入时暂停自动轮询 =====
export const isAutoRefreshPaused = ref(false);
import { ElMessage } from "element-plus";
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
import { isIec61850Protocol, isIec104Protocol } from "@/constants/protocol";

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
  tableDataMap: Ref<
    Record<number, { tableHeader: string[]; tableData: any[][]; total: number }>
  >;
  total: Ref<number>;
  fetchDeviceTable: (
    name: string,
    sid: number,
    q: string,
    pi: number,
    ps: number
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
    tableDataMap,
    total,
    fetchDeviceTable,
  } = options;

  const isAutoRead = ref(false);
  const timer = ref<any>(null);
  const isReading = ref(false);
  const cancelRead = ref(false);
  const successCount = ref(0);
  const failCount = ref(0);
  const readProgress = ref(0);
  const progressMessage = ref("");

  const readInterval = ref(10);
  const intervalOptions = ref([
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
    { label: "批量", value: "batch" },
    { label: "逐点", value: "single" },
  ];

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
    timer.value = setInterval(() => {
      // 导入文件时暂停轮询，避免干扰上传和超时
      if (isAutoRefreshPaused.value) return;
      fetchDeviceTable(
        routeName.value,
        currentSlaveId.value,
        searchQuery.value[currentSlaveId.value] || "",
        pageIndex.value,
        pageSize.value
      );
    }, TABLE_REFRESH_INTERVAL);
  };

  const stopAutoRefresh = () => {
    if (timer.value) {
      clearInterval(timer.value);
      timer.value = null;
    }
  };

  /** 停止所有自动读取（批量+逐点） */
  const stopAllAutoRead = async () => {
    await stopAutoRead(routeName.value).catch(() => {});
    stopSinglePointAutoRead();
  };

  const handleAutoReadChange = async (enabled: boolean) => {
    if (enabled) {
      if (readMode.value === "batch") {
        await startAutoRead(routeName.value);
        ElMessage.success("已启用自动读取（批量模式）");
      } else {
        startSinglePointAutoRead();
        ElMessage.success("已启用自动读取（逐点模式）");
      }
    } else {
      await stopAllAutoRead();
      ElMessage.success("已停止自动读取");
    }
  };

  /** 模式切换时由模板 `@change` 调用，确保先完全停止再重新启动 */
  const handleReadModeChange = async () => {
    if (!isAutoRead.value) return;
    await stopAllAutoRead();
    if (readMode.value === "batch") {
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
    progressMessage.value = "逐点自动读取中...";
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
        pointTypes.value
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
        progressMessage.value = `自动读取 [${i + 1}/${totalPoints}] ${pointName}`;

        try {
          const value = await readSinglePoint(routeName.value, pointCode);
          if (value !== null) {
            successCount.value++;
            // 实时更新表格中的显示值
            if (tableDataMap.value[currentSlaveId.value]) {
              const displayRow = tableDataMap.value[currentSlaveId.value].tableData.find(
                (r) => r[6] === pointCode
              );
              if (displayRow) displayRow[8] = value;
            }
          } else {
            failCount.value++;
          }
        } catch (e) {
          failCount.value++;
        }

        if (readInterval.value > 0) {
          await new Promise((resolve) => setTimeout(resolve, readInterval.value));
        }
        readProgress.value = Math.floor(((i + 1) / totalPoints) * 100);
      }
    } catch (e) {
      console.error("逐点自动读取错误:", e);
    }

    // 循环下一轮
    if (isAutoRead.value && !cancelRead.value) {
      const cycleInterval = Math.max(readInterval.value * 2, 1000);
      singlePointAutoReadTimer = setTimeout(doSinglePointReadCycle, cycleInterval);
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
      ElMessage.error("设备未连接，请先启动设备后再进行读取操作");
      return;
    }

    isReading.value = true;
    cancelRead.value = false;
    readProgress.value = 0;
    successCount.value = 0;
    failCount.value = 0;

    if (readMode.value === "batch") {
      await handleBatchRead();
    } else {
      await handleSinglePointRead();
    }
  };

  // 批量读取模式
  const handleBatchRead = async () => {
    progressMessage.value = "正在批量读取寄存器...";
    try {
      if (isIec61850Protocol(String(protocolType.value)) && channelId.value !== null) {
        progressMessage.value = "正在规划 IEC61850 DataSet 批量读取...";
        readProgress.value = 1;

        // 先发起批读，再并行轮询 Handler 的进度快照。后端把阻塞的 MMS
        // 调用放在线程中执行，因此每完成一个 DataSet 都能及时刷新到界面。
        const readPromise = iec61850ReadPoints(
          channelId.value,
          iec61850Category.value,
          iec61850Item.value,
          readInterval.value
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
                Math.min(snapshot.progress, 99)
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
            progressMessage.value = `批量读取完成 (成功: ${result.success}, 失败: ${result.fail})`;
            ElMessage.success(
              `批量读取完成，成功 ${result.success} 个，失败 ${result.fail} 个`
            );
          } else {
            progressMessage.value = "批量读取完成";
            ElMessage.success("批量读取完成");
          }
        } finally {
          window.clearInterval(progressTimer);
        }
        await fetchDeviceTable(
          routeName.value,
          currentSlaveId.value,
          searchQuery.value[currentSlaveId.value] || "",
          pageIndex.value,
          pageSize.value
        );
        readProgress.value = 100;
        return;
      }

      const result = await manualRead(routeName.value, readInterval.value);
      if (result) {
        if (typeof result === "object" && "success" in result) {
          successCount.value = result.success;
          failCount.value = result.fail;
          progressMessage.value = `批量读取完成 (成功: ${result.success}, 失败: ${result.fail})`;
          ElMessage.success(
            `批量读取完成，成功 ${result.success} 个，失败 ${result.fail} 个`
          );
        } else {
          readProgress.value = 100;
          progressMessage.value = "批量读取完成";
          ElMessage.success("批量读取完成");
        }
        await fetchDeviceTable(
          routeName.value,
          currentSlaveId.value,
          searchQuery.value[currentSlaveId.value] || "",
          pageIndex.value,
          pageSize.value
        );
        readProgress.value = 100;
      }
    } catch (e) {
      console.error("批量读取失败:", e);
      progressMessage.value = "读取出错";
    } finally {
      setTimeout(() => {
        isReading.value = false;
        readProgress.value = 0;
      }, READ_PROGRESS_DELAY);
    }
  };

  // 逐点读取模式
  const handleSinglePointRead = async () => {
    progressMessage.value = "正在获取测点列表...";
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
          pointTypes.value
        );
        if (data) allRows = data.get("table_data") || [];
      } else {
        const data = await getDeviceTable(
          routeName.value,
          currentSlaveId.value,
          "",
          1,
          10000,
          pointTypes.value
        );
        allRows = data.get("table_data") || [];
      }

      const totalPoints = allRows.length;
      if (totalPoints === 0) {
        ElMessage.warning("当前从机没有测点");
        isReading.value = false;
        return;
      }

      progressMessage.value = "开始逐点读取...";
      for (let i = 0; i < totalPoints; i++) {
        if (cancelRead.value) {
          progressMessage.value = "读取已取消";
          ElMessage.warning("操作已取消");
          break;
        }

        const row = allRows[i];
        const pointCode = row[6];
        const pointName = row[5];
        progressMessage.value = `[${i + 1}/${totalPoints}] ${pointName}`;

        try {
          const value = await readSinglePoint(routeName.value, pointCode);
          if (value !== null) {
            successCount.value++;
            if (tableDataMap.value[currentSlaveId.value]) {
              const displayRow = tableDataMap.value[currentSlaveId.value].tableData.find(
                (r) => r[6] === pointCode
              );
              if (displayRow) displayRow[8] = value;
            }
          } else {
            failCount.value++;
          }
        } catch (e) {
          failCount.value++;
        }

        if (readInterval.value > 0) {
          await new Promise((resolve) => setTimeout(resolve, readInterval.value));
        }
        readProgress.value = Math.floor(((i + 1) / totalPoints) * 100);
      }

      if (!cancelRead.value) {
        progressMessage.value = `完成 (成功: ${successCount.value}, 失败: ${failCount.value})`;
        ElMessage.success(
          `读取完成，成功 ${successCount.value} 个，失败 ${failCount.value} 个`
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
    isAutoRead.value = status;
    if (status) startAutoRefresh();
  };

  const formatProgress = (percentage: number) => {
    return percentage === 100 ? "完成" : `${percentage}%`;
  };

  onActivated(() => startAutoRefresh());
  onDeactivated(() => stopAutoRefresh());
  onUnmounted(() => stopAutoRefresh());

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
    needsAutoReadControls,
    startAutoRefresh,
    stopAutoRefresh,
    handleAutoReadChange,
    handleIntervalChange,
    handleReadModeChange,
    handleManualRead,
    fetchAutoReadStatus,
    formatProgress,
  };
}
