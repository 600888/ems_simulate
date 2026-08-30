<template>
  <div class="slave-container">
    <el-tabs
      v-model="activeName"
      class="modern-tabs"
      :class="{ 'without-data-tab': isIec61850 || isDlt645 }"
      @tab-click="handleClick"
      :before-leave="beforeLeave"
      @tab-remove="handleTabRemove"
    >
      <el-tab-pane
        v-for="slave in slaveIdList"
        :key="slave"
        :name="slave.toString()"
      >
        <template #label>
          <span class="custom-tab-label">
            <span>{{
              isIec61850 || isDlt645
                ? $t("common.data")
                : `${$t("point.slave")} ${slave}`
            }}</span>
            <span v-if="showsSlaveManagement" @click.stop>
              <el-dropdown
                trigger="click"
                @command="handleCommand($event, slave)"
                class="tab-dropdown"
              >
                <el-icon class="more-btn"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">{{
                      $t("common.edit")
                    }}</el-dropdown-item>
                    <el-dropdown-item
                      command="delete"
                      divided
                      style="color: var(--el-color-danger)"
                      >{{ $t("common.delete") }}</el-dropdown-item
                    >
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </span>
        </template>
        <!-- DL/T645 特殊命令栏（仅 DLT645 设备显示，主站/从站命令集不同） -->
        <div v-if="isDlt645" class="dlt645-command-bar">
          <el-button
            v-for="cmd in dlt645Commands"
            :key="cmd.command"
            class="dlt645-cmd-btn"
            :class="{ 'dlt645-cmd-danger': cmd.danger }"
            :icon="cmd.icon"
            @click="handleDlt645CommandClick(cmd)"
          >
            {{ t(cmd.labelKey) }}
          </el-button>
        </div>
        <!-- 搜索与控制栏 -->
        <div class="search-bar">
          <div class="search-left">
            <el-input
              v-model="searchQuery[slave]"
              :placeholder="$t('common.searchPlaceholder')"
              class="modern-input"
              clearable
              @keyup.enter="handleSearch(slave)"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button
              type="primary"
              class="modern-btn search-btn"
              @click="handleSearch(slave)"
            >
              {{ $t("common.search") }}
            </el-button>
            <template v-if="!(isIec61850 && iec61850Category === 'DataSets')">
              <el-button
                class="modern-btn reset-btn"
                @click="resetPoint"
                :icon="Refresh"
              >
                {{ $t("slave.resetPointValue") }}
              </el-button>
              <el-button
                class="modern-btn add-btn"
                @click="showAddPointDialog = true"
                :icon="Plus"
              >
                {{ $t("point.add") }}
              </el-button>
              <el-popconfirm
                :title="$t('slave.clearConfirm')"
                :confirm-button-text="$t('common.confirm')"
                :cancel-button-text="$t('common.cancel')"
                @confirm="handleClearPoints"
              >
                <template #reference>
                  <el-button
                    class="modern-btn clear-btn"
                    type="danger"
                    :icon="Delete"
                  >
                    {{ $t("slave.clearPoints") }}
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
            <template v-if="needsAutoReadControls">
              <div class="auto-read-control">
                <span class="auto-read-label">{{ $t("slave.autoRead") }}</span>
                <el-switch
                  v-if="isIec61850 && iec61850Category === 'DataSets'"
                  v-model="datasetAutoRead"
                  @change="handleDatasetAutoReadChange"
                  active-color="#3b82f6"
                  inactive-color="#94a3b8"
                />
                <el-switch
                  v-else
                  v-model="isAutoRead"
                  @change="handleAutoReadChange"
                  active-color="#3b82f6"
                  inactive-color="#94a3b8"
                />

                <el-divider direction="vertical" />

                <!-- 读取模式选择 (始终显示) -->
                <el-tooltip
                  v-if="
                    !isDlt645 &&
                    !(isIec61850 && iec61850Category === 'DataSets')
                  "
                  :content="
                    readMode === 'batch'
                      ? $t('slave.batchRead')
                      : $t('slave.singleRead')
                  "
                  placement="top"
                >
                  <el-segmented
                    v-model="readMode"
                    :options="readModeOptions"
                    size="small"
                    @change="handleReadModeChange"
                  />
                </el-tooltip>

                <!-- 间隔设置 (批量和逐点都支持，始终显示) -->
                <span class="auto-read-label">
                  {{
                    $t(
                      isIec61850 && iec61850Category === "DataSets"
                        ? "slave.cycleInterval"
                        : readMode === "single" || isDlt645
                          ? "slave.pointInterval"
                          : "slave.cycleInterval",
                    )
                  }}
                </span>
                <el-select
                  v-if="isIec61850 && iec61850Category === 'DataSets'"
                  v-model="datasetReadInterval"
                  :placeholder="$t('slave.cycleInterval')"
                  allow-create
                  filterable
                  default-first-option
                  style="width: 100px"
                  @change="handleDatasetIntervalChange"
                  size="normal"
                >
                  <el-option
                    v-for="item in datasetIntervalOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
                <el-select
                  v-else
                  v-model="readInterval"
                  :placeholder="
                    $t(
                      readMode === 'single' || isDlt645
                        ? 'slave.pointInterval'
                        : 'slave.cycleInterval',
                    )
                  "
                  allow-create
                  filterable
                  default-first-option
                  style="width: 90px"
                  @change="handleIntervalChange"
                  size="normal"
                >
                  <el-option
                    v-for="item in intervalOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>

                <!-- 手动读取/取消按钮 (仅在非自动读取时显示) -->
                <el-button
                  v-if="
                    isIec61850 &&
                    iec61850Category === 'DataSets' &&
                    !datasetAutoRead
                  "
                  type="success"
                  class="modern-btn manual-read-btn"
                  @click="handleDatasetManualRead"
                  :icon="Download"
                  :loading="datasetReading"
                >
                  {{ $t("slave.readDataset") }}
                </el-button>
                <el-button
                  v-else-if="
                    !(isIec61850 && iec61850Category === 'DataSets') &&
                    !isAutoRead
                  "
                  :type="isReading ? 'danger' : 'success'"
                  class="modern-btn"
                  :class="isReading ? 'cancel-read-btn' : 'manual-read-btn'"
                  @click="handleManualRead"
                  :icon="isReading ? CircleCloseFilled : Download"
                  :loading="isReading && readMode === 'batch' && !isDlt645"
                >
                  {{
                    isReading
                      ? $t("common.cancel")
                      : readMode === "batch" && !isDlt645
                        ? $t("common.batchRead")
                        : $t("common.singleRead")
                  }}
                </el-button>

                <!-- 自动读取时显示当前模式 -->
                <el-tag
                  v-if="
                    isIec61850 &&
                    iec61850Category === 'DataSets' &&
                    datasetAutoRead
                  "
                  type="info"
                  size="small"
                  effect="plain"
                >
                  {{ $t("slave.datasetAutoReading") }}
                </el-tag>
                <el-tag
                  v-else-if="
                    !(isIec61850 && iec61850Category === 'DataSets') &&
                    isAutoRead
                  "
                  type="info"
                  size="small"
                  effect="plain"
                >
                  {{
                    readMode === "batch" && !isDlt645
                      ? $t("slave.batchAutoReading")
                      : $t("slave.singleAutoReading")
                  }}
                </el-tag>
              </div>
            </template>
            <!-- IEC104 总召唤按钮 -->
            <template v-if="isIec104Client">
              <div class="auto-read-control">
                <el-button
                  type="primary"
                  class="modern-btn"
                  @click="handleInterrogation"
                  :icon="Download"
                  :loading="interrogating"
                >
                  {{ $t("device.generalCall") }}
                </el-button>
                <el-tooltip
                  :content="$t('device.generalCallTooltip')"
                  placement="top"
                >
                  <el-icon class="info-icon"><InfoFilled /></el-icon>
                </el-tooltip>
              </div>
            </template>
          </div>
        </div>

        <!-- 进度条区域 -->
        <div v-if="isReading || readProgress > 0" class="progress-container">
          <div class="progress-info">
            <span class="progress-text">{{ progressMessage }}</span>
            <div class="progress-stats">
              <span class="stat-success">{{
                $t("common.successCount", { count: successCount })
              }}</span>
              <span class="stat-fail">{{
                $t("common.failCount", { count: failCount })
              }}</span>
              <span class="progress-percentage">{{
                $t("common.progress", { pct: readProgress })
              }}</span>
            </div>
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
          :isIec61850="isIec61850"
          :iec61850TreeData="iec61850TreeData"
          :iec61850Category="iec61850Category"
          :channelId="channelId"
          @update:pageSize="handlePageSizeChange"
          @update:pageIndex="handlePageIndexChange"
          @update:activeFilters="handleFilterChange"
          @sort-change="handleSortChange"
          @refresh="handleTableRefresh"
        />
      </el-tab-pane>

      <!-- 添加从机按钮（作为特殊 tab，IEC61850 不需要） -->
      <el-tab-pane v-if="showsSlaveManagement" name="add" :closable="false">
        <template #label>
          <span class="add-slave-tab">
            <el-icon><Plus /></el-icon>
            {{ $t("slave.addSlave") }}
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
      :protocolType="String(protocolType)"
      @success="handlePointAdded"
    />

    <!-- 添加从机对话框（IEC61850 不需要） -->
    <AddSlaveDialog
      v-if="showsSlaveManagement"
      v-model="showAddSlaveDialog"
      :deviceName="routeName"
      :existingSlaves="slaveIdList"
      @success="handleSlaveAdded"
    />

    <!-- 编辑从机对话框（IEC61850 不需要） -->
    <EditSlaveDialog
      v-if="showsSlaveManagement"
      v-model="showEditSlaveDialog"
      :deviceName="routeName"
      :existingSlaves="slaveIdList"
      :currentSlaveId="editSlaveId"
      @success="handleSlaveEdited"
    />

    <!-- DL/T645 特殊命令参数弹窗 -->
    <Dlt645CommandDialog
      v-model="dlt645DialogVisible"
      :command="dlt645CurrentCommand"
      :is-server="isDlt645ServerDevice"
      :loading="dlt645CmdLoading"
      :current-address="dlt645CurrentAddress"
      :reading-address="dlt645AddressReading"
      :address-error="dlt645AddressError"
      :current-baud-rate="dlt645CurrentBaud"
      @confirm="handleDlt645Confirm"
      @read-address="fetchDlt645Address"
    />
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, watch, computed } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox, type TabsPaneContext } from "element-plus";
import { showError } from "@/api/http";
import {
  Search,
  Refresh,
  Download,
  Plus,
  Delete,
  CircleCloseFilled,
  MoreFilled,
  InfoFilled,
  Connection,
  EditPen,
  Clock,
  Timer,
  Odometer,
  Key,
  DataLine,
  DeleteFilled,
  DocumentDelete,
} from "@element-plus/icons-vue";
import {
  getSlaveIdList,
  getDeviceTable,
  getDeviceInfo,
  deleteSlave,
  iec104Interrogation,
  sendDlt645Command,
} from "@/api/deviceApi";
import { instance } from "@/api/http";
import { getIEC61850TreeData } from "@/api/channelApi";
import type { IEC61850TreeDataResponse } from "@/api/channelApi";
import { clearPoints, resetPointData } from "@/api/pointApi";
import { useAutoRead } from "@/composables";
import {
  isDlt645Protocol,
  isIec61850Protocol,
  isIec60870Protocol,
} from "@/constants/protocol";
import { isAutoRefreshPaused } from "@/composables/autoRefreshGate";
import { TABLE_HEADERS } from "@/constants/table";
import DeviceTable from "./Table.vue";
import AddPointDialog from "./AddPointDialog.vue";
import AddSlaveDialog from "./AddSlaveDialog.vue";
import EditSlaveDialog from "./EditSlaveDialog.vue";
import Dlt645CommandDialog from "./Dlt645CommandDialog.vue";

const route = useRoute();
const { t } = useI18n();
const initialDeviceName = route.params.deviceName as string;
const routeName = ref(initialDeviceName);
const activeName = ref("");
const slaveIdList = ref<number[]>([]);
const currentSlaveId = ref(1);
const tableDataMap = ref<
  Record<number, { tableHeader: string[]; tableData: any[][]; total: number }>
>({});
const searchQuery = ref<Record<number, string>>({});
const pageSize = ref(10);
const pageIndex = ref(1);
const total = ref(0);
const activeFilters = ref<Record<string, number>>({});
const orderBy = ref<string | null>(null);
const orderDirection = ref<string | null>(null);
const protocolType = ref<number | string>(1);
const connType = ref<number>(2); // 默认为服务端
const channelId = ref<number | null>(null);

// IEC61850 树形节点筛选
const iec61850Category = ref<string>("");
const iec61850Item = ref<string>("");

// IEC61850 树形数据 (新接口)
const iec61850TreeData = ref<IEC61850TreeDataResponse | null>(null);

// 判断当前是否为 IEC61850 协议
const isIec61850 = computed(() => {
  return isIec61850Protocol(String(protocolType.value));
});

const isDlt645 = computed(() => isDlt645Protocol(protocolType.value));

/** 是否为 DLT645 主站（客户端）设备 */
const isDlt645ClientDevice = computed(
  () => String(protocolType.value) === "Dlt645Client",
);
/** 是否为 DLT645 从站（模拟电表服务端）设备 */
const isDlt645ServerDevice = computed(
  () => String(protocolType.value) === "Dlt645Server",
);

const showsSlaveManagement = computed(
  () => !isIec61850.value && !isDlt645.value,
);

/** DL/T645 特殊命令项定义 */
interface Dlt645CommandItem {
  command: string;
  labelKey: string;
  icon: any;
  danger?: boolean;
}

/** 主站（Dlt645Client）特殊命令 */
const DLT645_CLIENT_COMMANDS: Dlt645CommandItem[] = [
  {
    command: "read_address",
    labelKey: "slave.dlt645ClientCmd.read_address",
    icon: Connection,
  },
  {
    command: "write_address",
    labelKey: "slave.dlt645ClientCmd.write_address",
    icon: EditPen,
  },
  {
    command: "broadcast_time_sync",
    labelKey: "slave.dlt645ClientCmd.broadcast_time_sync",
    icon: Clock,
  },
  {
    command: "freeze",
    labelKey: "slave.dlt645ClientCmd.freeze",
    icon: Timer,
  },
  {
    command: "change_baud_rate",
    labelKey: "slave.dlt645ClientCmd.change_baud_rate",
    icon: Odometer,
  },
  {
    command: "change_password",
    labelKey: "slave.dlt645ClientCmd.change_password",
    icon: Key,
  },
  {
    command: "clear_demand",
    labelKey: "slave.dlt645ClientCmd.clear_demand",
    icon: DataLine,
    danger: true,
  },
  {
    command: "clear_meter",
    labelKey: "slave.dlt645ClientCmd.clear_meter",
    icon: DeleteFilled,
    danger: true,
  },
  {
    command: "clear_event",
    labelKey: "slave.dlt645ClientCmd.clear_event",
    icon: DocumentDelete,
    danger: true,
  },
];

/** 从站（Dlt645Server）特殊命令 */
const DLT645_SERVER_COMMANDS: Dlt645CommandItem[] = [
  {
    command: "write_address",
    labelKey: "slave.dlt645ServerCmd.write_address",
    icon: EditPen,
  },
  {
    command: "set_time",
    labelKey: "slave.dlt645ServerCmd.set_time",
    icon: Clock,
  },
  {
    command: "change_password",
    labelKey: "slave.dlt645ServerCmd.change_password",
    icon: Key,
  },
  {
    command: "clear_demand",
    labelKey: "slave.dlt645ServerCmd.clear_demand",
    icon: DataLine,
    danger: true,
  },
  {
    command: "clear_meter",
    labelKey: "slave.dlt645ServerCmd.clear_meter",
    icon: DeleteFilled,
    danger: true,
  },
  {
    command: "clear_event",
    labelKey: "slave.dlt645ServerCmd.clear_event",
    icon: DocumentDelete,
    danger: true,
  },
];

/** 当前设备角色对应的命令列表 */
const dlt645Commands = computed(() =>
  isDlt645ClientDevice.value ? DLT645_CLIENT_COMMANDS : DLT645_SERVER_COMMANDS,
);

// DL/T645 命令弹窗状态
const dlt645DialogVisible = ref(false);
const dlt645CurrentCommand = ref("");
const dlt645CmdLoading = ref(false);

/** 需要弹窗输入参数的命令（用于判断无参命令直接执行） */
const DLT645_PARAM_COMMANDS = new Set([
  "write_address",
  "broadcast_time_sync",
  "set_time",
  "change_baud_rate",
  "change_password",
  "clear_demand",
  "clear_meter",
  "clear_event",
]);

// 读/写通讯地址需要读取当前电表地址显示在弹窗中
const dlt645CurrentAddress = ref<string | null>(null);
const dlt645AddressReading = ref(false);
const dlt645AddressError = ref(false);

// 更改通信速率弹窗默认选中当前速率
const dlt645CurrentBaud = ref<number | null>(null);
const fetchDlt645BaudRate = async () => {
  try {
    const info = await getDeviceInfo(routeName.value);
    const baud = Number(info.get("baudrate"));
    dlt645CurrentBaud.value = Number.isFinite(baud) ? baud : null;
  } catch {
    dlt645CurrentBaud.value = null;
  }
};

/** 读取当前电表通讯地址（主站读电表实际地址，从站取设备配置地址） */
const fetchDlt645Address = async () => {
  dlt645AddressReading.value = true;
  dlt645AddressError.value = false;
  try {
    if (isDlt645ClientDevice.value) {
      // 主站：通过读通讯地址命令获取电表实际地址
      const detail = await sendDlt645Command(
        routeName.value,
        "read_address",
        {},
      );
      const addr = detail?.value ?? null;
      dlt645CurrentAddress.value = addr !== null ? String(addr) : null;
    } else if (isDlt645ServerDevice.value) {
      // 从站：直接取设备配置的电表地址
      const info = await getDeviceInfo(routeName.value);
      const addr = info.get("meter_address");
      dlt645CurrentAddress.value = addr ? String(addr) : null;
    }
  } catch {
    dlt645AddressError.value = true;
    dlt645CurrentAddress.value = null;
  } finally {
    dlt645AddressReading.value = false;
  }
};

// 弹窗打开时按命令预取相关信息
watch(
  () => dlt645DialogVisible.value,
  (visible) => {
    if (!visible) return;
    const cmd = dlt645CurrentCommand.value;
    if (cmd === "read_address" || cmd === "write_address") {
      fetchDlt645Address();
    }
    if (cmd === "change_baud_rate") {
      fetchDlt645BaudRate();
    }
  },
);

/** 点击命令按钮：危险或带参命令弹窗，其余直接执行 */
const handleDlt645CommandClick = (cmd: Dlt645CommandItem) => {
  dlt645CurrentCommand.value = cmd.command;
  if (
    cmd.danger ||
    cmd.command === "read_address" ||
    DLT645_PARAM_COMMANDS.has(cmd.command)
  ) {
    dlt645DialogVisible.value = true;
  } else {
    executeDlt645Command(cmd.command, {});
  }
};

/** 执行 DL/T645 特殊命令 */
const executeDlt645Command = async (
  command: string,
  params: Record<string, unknown>,
) => {
  dlt645CmdLoading.value = true;
  try {
    await sendDlt645Command(routeName.value, command, params);
    ElMessage.success(t("slave.dlt645CmdSuccess"));
    // 刷新表格数据
    handleSearch(currentSlaveId.value);
  } catch (e: any) {
    showError(e, t("slave.dlt645CmdFailed"));
  } finally {
    dlt645CmdLoading.value = false;
  }
};

/** 弹窗确认回调 */
const handleDlt645Confirm = (params: Record<string, unknown>) => {
  dlt645DialogVisible.value = false;
  executeDlt645Command(dlt645CurrentCommand.value, params);
};

const parseDlt645QueryNumber = (value: unknown): number | null => {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const dlt645Prefix = computed(() =>
  parseDlt645QueryNumber(route.query.dlt645_prefix),
);
const dlt645Settlement = computed(() =>
  parseDlt645QueryNumber(route.query.dlt645_settlement),
);

// 判断当前是否为 IEC61850 树节点筛选模式
const isIec61850Filtered = computed(() => {
  return (
    isIec61850.value && channelId.value !== null && !!iec61850Category.value
  );
});

// IEC104 客户端判断
const isIec104Client = computed(() => {
  const protocolStr = String(protocolType.value);
  return (
    isIec60870Protocol(protocolStr) &&
    ["Iec104Client", "Iec101Client"].includes(protocolStr)
  );
});

// 总召唤按钮状态
const interrogating = ref(false);
const handleInterrogation = async () => {
  interrogating.value = true;
  try {
    await iec104Interrogation(routeName.value);
    ElMessage.success(t("device.generalCallSuccess"));
    // 刷新表格
    handleSearch(currentSlaveId.value);
  } catch (e: any) {
    showError(e, t("device.generalCallFailed"));
  } finally {
    interrogating.value = false;
  }
};

const showAddPointDialog = ref<boolean>(false);
const showAddSlaveDialog = ref<boolean>(false);
const showEditSlaveDialog = ref<boolean>(false);
const editSlaveId = ref<number>(0);

const pointTypes = computed<number[]>(() => {
  // 只提取帧类型筛选的数字值，忽略 IEC104类型等字符串筛选
  const frameTypeFilters = activeFilters.value["帧类型"];
  if (frameTypeFilters && Array.isArray(frameTypeFilters)) {
    return frameTypeFilters.filter((v: any) => typeof v === "number");
  }
  return [];
});

const iec104Types = computed<string[]>(() => {
  const typeFilters = activeFilters.value["IEC104类型"];
  return Array.isArray(typeFilters)
    ? typeFilters.filter(
        (value: unknown): value is string => typeof value === "string",
      )
    : [];
});

const dnp3EventFilter = computed<string | null>(() => {
  const filters = activeFilters.value["DNP3事件类别"];
  return Array.isArray(filters) && typeof filters[0] === "string"
    ? filters[0]
    : null;
});
const dnp3EventClass = computed<number | null>(() => {
  const match = /^class([1-3])$/.exec(dnp3EventFilter.value || "");
  return match ? Number(match[1]) : null;
});
const dnp3EventEnabled = computed<boolean | null>(() => {
  if (dnp3EventFilter.value === "none") return false;
  return dnp3EventClass.value === null ? null : true;
});

const handlePageIndexChange = (idx: number) => {
  pageIndex.value = idx;
  handleSearch(currentSlaveId.value);
};
const handlePageSizeChange = (size: number) => {
  pageSize.value = size;
  handleSearch(currentSlaveId.value);
};
const handleFilterChange = (filters: Record<string, any>) => {
  activeFilters.value = filters;
  // 筛选必须先于分页执行；切换筛选条件后从筛选结果的第一页开始展示。
  pageIndex.value = 1;
  fetchDeviceTable(
    routeName.value,
    currentSlaveId.value,
    searchQuery.value[currentSlaveId.value] || "",
    1,
    pageSize.value,
  );
};
const handleSortChange = ({
  prop,
  order,
}: {
  prop: string;
  order: string | null;
}) => {
  orderBy.value = order ? prop : null;
  orderDirection.value = order;
  fetchDeviceTable(
    routeName.value,
    currentSlaveId.value,
    searchQuery.value[currentSlaveId.value] || "",
    pageIndex.value,
    pageSize.value,
  );
};
const handleTableRefresh = () => handleSearch(currentSlaveId.value);

const fetchSlaveList = async () => {
  if (!routeName.value) return;
  // 导入 ICD 文件期间暂停刷新，避免 404 错误
  if (isAutoRefreshPaused.value) return;
  try {
    const deviceInfo = await getDeviceInfo(routeName.value);
    if (deviceInfo) {
      protocolType.value = deviceInfo.get("type") ?? 1;
      // 确保 conn_type 是数字类型
      connType.value = Number(deviceInfo.get("conn_type") ?? 2);
      // 存储 channel_id 用于 IEC61850 表格数据接口
      channelId.value = deviceInfo.get("channel_id") ?? null;
    }
  } catch (e) {
    console.warn("设备信息获取失败");
  }

  // IEC61850 和 DLT645 不向界面暴露从机概念，使用内部固定数据分区。
  if (isIec61850.value || isDlt645.value) {
    slaveIdList.value = [1];
    currentSlaveId.value = 1;
    activeName.value = "1";
    await fetchAllDeviceTables();
    return;
  }

  slaveIdList.value = await getSlaveIdList(routeName.value);
  if (slaveIdList.value.length > 0) {
    currentSlaveId.value = slaveIdList.value[0];
    activeName.value = slaveIdList.value[0].toString();
    await fetchAllDeviceTables();
  }
};

const fetchDeviceTable = async (
  name: string,
  sid: number,
  q: string,
  pi: number,
  ps: number,
) => {
  // 导入 ICD 文件期间暂停刷新，避免 404 错误
  if (isAutoRefreshPaused.value) return;
  // IEC61850 使用新的树形接口
  if (isIec61850.value && channelId.value !== null) {
    // DataSets 分类: 使用 tree-data 接口（Table.vue 的 displayData 只认 iec61850TreeData）
    if (iec61850Category.value === "DataSets" && iec61850Item.value) {
      const treeResp = await getIEC61850TreeData(
        channelId.value,
        iec61850Category.value,
        iec61850Item.value,
        q || null,
        pointTypes.value,
        pi,
        ps,
      );
      // 读取失败时保留上一帧数据，避免表格瞬间清空后再次出现造成闪烁。
      if (treeResp) {
        iec61850TreeData.value = treeResp;
        total.value = treeResp.total;
      }
      // 设置 tableHeader: 地址/FC/最后更新时间/DA路径 是模板写死的专用列,
      // 动态列只需补充剩余的表头
      if (!tableDataMap.value[sid]) {
        tableDataMap.value[sid] = { tableHeader: [], tableData: [], total: 0 };
      }
      tableDataMap.value[sid].tableHeader = ["测点名称", "测点编码", "真实值"];
      return;
    }

    // DataModel 及其他: 使用 tree-data 接口
    const treeResp = await getIEC61850TreeData(
      channelId.value,
      iec61850Category.value,
      iec61850Item.value,
      q || null,
      pointTypes.value,
      pi,
      ps,
    );
    iec61850TreeData.value = treeResp;
    if (treeResp) {
      total.value = treeResp.total;
    }
    if (!tableDataMap.value[sid]) {
      tableDataMap.value[sid] = { tableHeader: [], tableData: [], total: 0 };
    }
    tableDataMap.value[sid].tableHeader = [
      "测点名称",
      "测点类型",
      "真实值",
      "状态",
    ];
    tableDataMap.value[sid].total = total.value;
    return;
  }

  const data = await getDeviceTable(
    name,
    sid,
    q,
    pi,
    ps,
    pointTypes.value,
    orderBy.value,
    orderDirection.value,
    iec104Types.value,
    dlt645Prefix.value,
    dlt645Settlement.value,
    dnp3EventClass.value,
    dnp3EventEnabled.value,
  );
  if (data) {
    const fetchedTotal = Number(data.get("total") || 0);
    const fetchedTotalPages = Math.max(1, Math.ceil(fetchedTotal / ps));

    // 缓存的总数可能因筛选或数据变化而过期；请求后再校验一次当前页。
    if (sid === currentSlaveId.value && pi > fetchedTotalPages) {
      pageIndex.value = 1;
      await fetchDeviceTable(name, sid, q, 1, ps);
      return;
    }

    // 确保初始化对象
    if (!tableDataMap.value[sid]) {
      tableDataMap.value[sid] = { tableHeader: [], tableData: [], total: 0 };
    }

    tableDataMap.value[sid] = {
      tableHeader: TABLE_HEADERS as string[],
      tableData: data.get("table_data"),
      total: fetchedTotal,
    };

    // 如果是当前显示的从机，同时更新全局 total 以防万一（但我们将主要改为从 map 中取值）
    if (sid === currentSlaveId.value) {
      total.value = fetchedTotal;
    }
  }
};

const fetchAllDeviceTables = async () => {
  for (const slave of slaveIdList.value) {
    await fetchDeviceTable(
      routeName.value,
      slave,
      "",
      pageIndex.value,
      pageSize.value,
    );
  }
};

// 阻止切换到 "add" tab
const beforeLeave = (activeName: string, oldActiveName: string) => {
  if (activeName === "add") {
    if (!isInternalSwitch.value) {
      showAddSlaveDialog.value = true;
      return false; // 用户点击时阻止切换
    }
    // 内部切换（如删除最后一个从机后），允许切换但不弹窗
    return true;
  }
  return true;
};

const handleClick = async (tab: TabsPaneContext) => {
  if (tab.paneName === "add") {
    // 如果当前已经是 add（例如删光了所有从机），再次点击需要弹窗
    if (activeName.value === "add") {
      showAddSlaveDialog.value = true;
    }
    return;
  }

  if (tab.index !== undefined) {
    const targetSlaveId = slaveIdList.value[parseInt(tab.index)];
    currentSlaveId.value = targetSlaveId;
    // 先尝试沿用当前页；fetchDeviceTable 会根据目标从机的最新总数回退到第一页。
    await fetchDeviceTable(
      routeName.value,
      targetSlaveId,
      searchQuery.value[targetSlaveId] || "",
      pageIndex.value,
      pageSize.value,
    );
  }
};

const handleSearch = (slave: number) => {
  fetchDeviceTable(
    routeName.value,
    slave,
    searchQuery.value[slave] || "",
    pageIndex.value,
    pageSize.value,
  );
};

const resetPoint = async () => {
  try {
    if (await resetPointData(routeName.value)) {
      ElMessage.success(t("slave.resetSuccess"));
      handleSearch(currentSlaveId.value);
    }
  } catch (e) {
    console.error("重置测点失败:", e);
  }
};

const handleClearPoints = async () => {
  try {
    const deletedCount = await clearPoints(
      routeName.value,
      currentSlaveId.value,
    );
    if (deletedCount >= 0) {
      ElMessage.success(t("slave.clearSuccess", { count: deletedCount }));
      handleTableRefresh();
    }
  } catch (e) {
    console.error("清空测点失败:", e);
  }
};

const isInternalSwitch = ref(false);

const handleDeleteSlave = async (slaveId: number) => {
  try {
    const success = await deleteSlave(routeName.value, slaveId);
    if (success) {
      ElMessage.success(t("slave.deleteSuccess", { id: slaveId }));

      // 标记为内部切换，防止触发 beforeLeave 的弹窗
      isInternalSwitch.value = true;

      // 重新加载从机列表
      await fetchSlaveList();

      // 切换到第一个可用的从机，或添加页
      if (slaveIdList.value.length > 0) {
        // 如果删除的是当前选中的，切换到第一个
        activeName.value = slaveIdList.value[0].toString();
        currentSlaveId.value = slaveIdList.value[0];
        // 刷新新的从机数据
        await fetchDeviceTable(
          routeName.value,
          currentSlaveId.value,
          searchQuery.value[currentSlaveId.value] || "",
          1,
          pageSize.value,
        );
      } else {
        activeName.value = "add";
        currentSlaveId.value = 1;
      }

      // 恢复标志位 (使用 setTimeout 确保在 Vue 更新周期之后)
      setTimeout(() => {
        isInternalSwitch.value = false;
      }, 100);
    }
  } catch (e) {
    console.error("删除从机失败:", e);
  }
};

const handleTabRemove = (tabName: string | number) => {
  const slaveId = Number(tabName);

  ElMessageBox.confirm(
    t("slave.deleteConfirm", { id: slaveId }),
    t("common.warning"),
    {
      confirmButtonText: t("common.confirm"),
      cancelButtonText: t("common.cancel"),
      type: "warning",
    },
  )
    .then(() => {
      handleDeleteSlave(slaveId);
    })
    .catch(() => {
      // cancel
    });
};

const handleCommand = (command: string | number | object, slaveId: number) => {
  if (command === "delete") {
    handleTabRemove(slaveId);
  } else if (command === "edit") {
    editSlaveId.value = slaveId;
    showEditSlaveDialog.value = true;
  }
};

const handleSlaveEdited = async (newSlaveId: number) => {
  await fetchSlaveList();
  // Switch to new slave ID
  if (slaveIdList.value.includes(newSlaveId)) {
    activeName.value = newSlaveId.toString();
    currentSlaveId.value = newSlaveId;
    await fetchDeviceTable(
      routeName.value,
      currentSlaveId.value,
      searchQuery.value[currentSlaveId.value] || "",
      1,
      pageSize.value,
    );
  }
};

// ===== 自动读取 composable =====
const {
  isAutoRead,
  isReading,
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
  successCount,
  failCount,
} = useAutoRead({
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
});

// Watch for route param changes

watch(
  () => route.fullPath,
  async () => {
    // 强制刷新：当 query 参数变化（如添加了 t=timestamp）且属于本组件对应设备时触发
    if (
      route.params.deviceName &&
      route.params.deviceName === initialDeviceName
    ) {
      // 同步 IEC61850 树节点筛选参数
      const newCategory = (route.query.category as string) || "";
      const newItem = (route.query.item as string) || "";
      const filterChanged =
        newCategory !== iec61850Category.value ||
        newItem !== iec61850Item.value;
      iec61850Category.value = newCategory;
      iec61850Item.value = newItem;

      if (routeName.value !== route.params.deviceName) {
        stopAutoRefresh();
        routeName.value = route.params.deviceName as string;
        pageIndex.value = 1;
        pageSize.value = 10;
        isAutoRead.value = false;
        await fetchSlaveList();
        await fetchAutoReadStatus();
        startAutoRefresh();
      } else {
        // 同一设备，若筛选参数变化则重新加载数据
        if (filterChanged) {
          pageIndex.value = 1;
          await fetchDeviceTable(
            routeName.value,
            currentSlaveId.value,
            searchQuery.value[currentSlaveId.value] || "",
            pageIndex.value,
            pageSize.value,
          );
        } else {
          handleSearch(currentSlaveId.value);
        }
      }
    }
  },
);

onMounted(async () => {
  // 从路由查询参数初始化 IEC61850 筛选条件
  iec61850Category.value = (route.query.category as string) || "";
  iec61850Item.value = (route.query.item as string) || "";

  await fetchSlaveList();
  // 获取当前自动读取状态
  await fetchAutoReadStatus();

  // 连接 WebSocket
  // connectWebSocket();
});

let websocket: WebSocket | null = null;
let wsReconnectTimer: any = null;

// import { instance } from "@/api/deviceApi"; // Moved to top

const connectWebSocket = () => {
  if (websocket) return;

  // 获取 baseURL
  let baseURL = instance.defaults.baseURL || "/";
  if (baseURL.startsWith("/")) {
    // 如果是相对路径，拼接到当前 host
    baseURL = window.location.origin + baseURL;
  }

  // 替换 http/https 为 ws/wss
  const wsBase = baseURL.replace(/^http/, "ws");
  // 去除末尾斜杠
  const wsUrl = `${wsBase.replace(/\/$/, "")}/device/ws/${routeName.value}`;

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
      if (data.type === "progress") {
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

const handlePointAdded = () => {
  fetchDeviceTable(
    routeName.value,
    currentSlaveId.value,
    searchQuery.value[currentSlaveId.value] || "",
    pageIndex.value,
    pageSize.value,
  );
};

const handleSlaveAdded = async () => {
  await fetchSlaveList();
};

const reloadDatas = async () => {
  await fetchSlaveList();
};

defineExpose({
  reloadDatas,
});
</script>

<style lang="scss" scoped>
.slave-container {
  background-color: var(--panel-bg);
  padding: 16px 20px 12px;
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
  &.without-data-tab {
    /* 只隐藏外层从机 Tabs 的头部（直接子级），不影响展开行内层 inner-tabs */
    > :deep(.el-tabs__header) {
      display: none;
    }
  }

  :deep(.el-tabs__header) {
    margin-bottom: 24px;
    border: none !important;

    .el-tabs__nav-wrap {
      &::after {
        display: none !important;
      }
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
      &::before,
      &::after {
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

.custom-tab-label {
  display: flex;
  align-items: center;
  justify-content: center; /* Ensure label content is centered */
  height: 100%;

  .tab-dropdown {
    margin-left: 8px; /* More space */
    display: flex;
    align-items: center; /* Vertical center */

    .more-btn {
      font-size: 20px; /* Larger icon */
      color: var(--text-secondary);
      cursor: pointer;
      transform: rotate(90deg);
      border-radius: 4px;
      padding: 4px; /* Larger hit area */
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;

      &:hover {
        background-color: rgba(0, 0, 0, 0.05);
        color: var(--color-primary);
        transform: rotate(90deg) scale(1.1); /* Slight zoom on hover */
      }
    }
  }
}

/* DL/T645 特殊命令栏 */
.dlt645-command-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.dlt645-cmd-btn {
  height: 38px;
  padding: 0 18px;
  font-size: 14px;
  border-radius: 8px;
  font-weight: 500;
  &.dlt645-cmd-danger {
    color: var(--el-color-danger);
    border-color: var(--el-color-danger);
    &:hover {
      background-color: var(--el-color-danger);
      color: #fff;
      border-color: var(--el-color-danger);
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

  &.search-btn {
    padding: 0 20px;
  }
  &.reset-btn {
    background-color: var(--color-warning);
    color: white;
    border: none;
    &:hover {
      background-color: #d97706;
      transform: translateY(-1px);
    }
  }
  &.manual-read-btn {
    background-color: var(--color-success, #10b981);
    color: white;
    border: none;
    padding: 0 16px;
    &:hover {
      background-color: #059669;
      transform: translateY(-1px);
    }
  }
  &.cancel-read-btn {
    background-color: var(--el-color-danger, #f56c6c);
    color: white;
    border: none;
    padding: 0 16px;
    &:hover {
      background-color: #f78989;
      transform: translateY(-1px);
    }
  }
  &.add-btn {
    background-color: #6366f1;
    color: white;
    border: none;
    &:hover {
      background-color: #4f46e5;
      transform: translateY(-1px);
    }
  }
  &.add-slave-btn {
    background-color: #8b5cf6;
    color: white;
    border: none;
    &:hover {
      background-color: #7c3aed;
      transform: translateY(-1px);
    }
  }
  &:hover {
    transform: translateY(-1px);
    opacity: 0.9;
  }
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

.info-icon {
  font-size: 16px;
  color: var(--text-secondary, #94a3b8);
  cursor: help;
  transition: color 0.2s;
  &:hover {
    color: var(--color-primary, #3b82f6);
  }
}

.manual-read-section {
  display: flex;
  align-items: center;
  gap: 10px;

  .el-divider--vertical {
    height: 20px;
    margin: 0 4px;
  }

  :deep(.el-segmented) {
    --el-segmented-item-selected-bg-color: var(--color-primary);
    --el-segmented-item-selected-color: #fff;

    .el-segmented__item {
      padding: 0 12px;
      font-size: 12px;
    }
  }
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
  align-items: center;
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.progress-stats {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-success {
  color: #10b981;
  font-weight: 600;
  padding: 2px 8px;
  background: rgba(16, 185, 129, 0.1);
  border-radius: 4px;
}

.stat-fail {
  color: #ef4444;
  font-weight: 600;
  padding: 2px 8px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 4px;
}

.progress-percentage {
  font-weight: 600;
  color: var(--color-primary);
  padding-left: 12px;
  border-left: 1px solid var(--sidebar-border);
}
</style>
