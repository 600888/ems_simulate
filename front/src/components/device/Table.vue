<template>
  <div class="modern-table-container">
    <el-table
      :data="displayData"
      class="custom-table"
      :cell-class-name="() => 'modern-cell'"
      :header-cell-class-name="() => 'modern-header-cell'"
      @filter-change="handleFilterChange"
      @sort-change="handleSortChange"
      :row-key="getRowKey"
      @expand-change="handleExpand"
      :expand-row-keys="expandedRowKeys"
      :row-class-name="isIec61850 ? iec61850RowClassName : undefined"
      border
      stripe
      style="width: 100%"
    >
      <!-- 展开详情区域 (DO 行不显示, DA 行正常显示) -->
      <el-table-column type="expand">
        <template #default="scope">
          <div v-if="!scope.row._isDoRow && !scope.row._isVirtualDa" class="expand-wrapper">
            <el-tabs v-model="activeName" class="inner-tabs" lazy>
              <el-tab-pane :label="$t('table.configControl')" name="数据解析和设置">
                <div class="control-grid">
                  <SingleRegister
                    v-if="intRegisterDecodeList.includes(scope.row['解析码'])"
                    :rowIndex="scope.$index"
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :realValue="parseFloat(scope.row['真实值'] || 0)"
                    :slaveId="slaveId"
                    @editSuccess="updatePointData"
                  />
                  <LongRegister
                    v-if="longRegisterDecodeList.includes(scope.row['解析码'])"
                    :rowIndex="scope.$index"
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :realValue="parseFloat(scope.row['真实值'] || 0)"
                    :slaveId="slaveId"
                    @editSuccess="updatePointData"
                  />
                  <FloatRegister
                    v-if="floatRegisterDecodeList.includes(scope.row['解析码'])"
                    :rowIndex="scope.$index"
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :realValue="parseFloat(scope.row['真实值'] || 0)"
                    :slaveId="slaveId"
                    @editSuccess="updatePointData"
                  />
                  <EditPointLimit :deviceName="deviceName" :pointCode="scope.row['测点编码']" :active="activeName === '数据解析和设置'" />
                </div>
              </el-tab-pane>
              <el-tab-pane :label="$t('table.propertyEdit')" name="测点编辑">
                <div class="metadata-grid">
                  <EditPointMetadata
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :active="activeName === '测点编辑'"
                    @update-success="(newCode) => handleMetadataUpdate(newCode, scope.row['测点编码'])"
                  />
                  <EditPointIec104
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :active="activeName === '测点编辑'"
                    :protocolType="String(protocolType)"
                    @update-success="emit('refresh')"
                  />
                </div>
              </el-tab-pane>
              
              <el-tab-pane :label="$t('table.pointMapping')" name="测点映射">
                <PointMappingConfig
                  :deviceName="deviceName"
                  :targetPointCode="scope.row['测点编码']"
                  :active="activeName === '测点映射'"
                />
              </el-tab-pane>

              <el-tab-pane name="数据模拟" :disabled="isClientDevice">
                <template #label>
                  <el-tooltip :content="isClientDevice ? $t('device.clientNoSim') : ''" :disabled="!isClientDevice" placement="top">
                    <span>{{ $t('table.simulation') }}</span>
                  </el-tooltip>
                </template>
                <PointSimulator
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                  :active="activeName === '数据模拟'"
                  @update-success="handlePointSimulatorUpdate"
                />
              </el-tab-pane>

              <el-tab-pane :label="$t('table.changeHistory')" name="变化回溯">
                <PointChangeHistory
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                  :active="activeName === '变化回溯'"
                  :slaveId="slaveId"
                />
              </el-tab-pane>
            </el-tabs>
          </div>
        </template>
      </el-table-column>

      <!-- 地址列 -->
      <el-table-column
        :label="$t('table.address')"
        prop="地址"
        sortable="custom"
        :min-width="isIec61850 ? 200 : 130"
        show-overflow-tooltip
      >
        <template #header>
          <div class="header-content address-header">
            <span>{{ $t('table.address') }}</span>
            <el-switch
              v-if="!isIec61850"
              v-model="showHexAddress"
              size="small"
              inline-prompt
              :active-text="$t('table.hex')"
              :inactive-text="$t('table.dec')"
              class="address-switch"
            />
          </div>
        </template>
        <template #default="scope">
          <span v-if="scope.row._isDoRow" class="cell-text do-address" @click.stop="toggleDoExpand(scope.row._doRef)">
            <el-icon class="do-expand-icon" :class="{ 'is-expanded': iec61850ExpandedDoKeys.includes(scope.row._doRef) }">
              <ArrowRight />
            </el-icon>
            {{ scope.row._doName }}
            <el-tag size="small" effect="plain" class="do-da-tag do-tag">DO</el-tag>
            <span class="do-badge">{{ scope.row._daCount }} {{ $t('table.items') }}</span>
          </span>
          <span v-else-if="scope.row._isDaRow" class="cell-text da-address" :class="{ 'is-struct-da': scope.row._isStructDa }" @click.stop="scope.row._isStructDa && toggleDaExpand(`${scope.row._doRef}.${scope.row._daPath}`)">
            <el-icon v-if="scope.row._isStructDa" class="da-expand-icon" :class="{ 'is-expanded': iec61850ExpandedDaKeys.includes(`${scope.row._doRef}.${scope.row._daPath}`) }">
              <ArrowRight />
            </el-icon>
            {{ scope.row._daDisplayName || scope.row._daPath || scope.row['地址'] }}
            <el-tag size="small" effect="plain" class="do-da-tag da-tag">DA</el-tag>
            <span v-if="scope.row._isStructDa" class="do-badge">{{ scope.row._bdaCount }} {{ $t('table.items') }}</span>
          </span>
          <span v-else-if="scope.row._isBdaRow" class="cell-text bda-address">
            {{ scope.row._bdaName || scope.row._daPath }}
            <el-tag size="small" effect="plain" class="do-da-tag bda-tag">BDA</el-tag>
          </span>
          <span v-else class="cell-text">
            {{ showHexAddress ? scope.row['16进制地址'] : scope.row['地址'] }}
          </span>
        </template>
      </el-table-column>

      <!-- IEC61850 FC 列 -->
      <el-table-column
        v-if="isIec61850"
        :label="$t('table.fc')"
        :width="70"
        :show-overflow-tooltip="false"
      >
        <template #default="scope">
          <el-tag
            v-if="scope.row._fc && !scope.row._isDoRow"
            :color="IEC61850_FC_COLORS[scope.row._fc] || '#6b7280'"
            effect="dark"
            size="small"
            class="fc-tag"
          >
            {{ scope.row._fc }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- DataSet 最后更新时间列 -->
      <el-table-column
        v-if="props.iec61850Category === 'DataSets'"
        :label="$t('table.lastUpdate')"
        :width="160"
        show-overflow-tooltip
      >
        <template #default="scope">
          <span class="cell-text">{{ scope.row['最后更新时间'] || '' }}</span>
        </template>
      </el-table-column>

      <!-- IEC61850 DA路径列 -->
      <el-table-column
        v-if="isIec61850"
        :label="$t('table.daPath')"
        :width="120"
        show-overflow-tooltip
      >
        <template #default="scope">
          <span v-if="scope.row._daPath" class="cell-text da-path">{{ scope.row._daPath }}</span>
        </template>
      </el-table-column>

      <!-- 动态列渲染（排除地址列） -->
      <el-table-column
        v-for="(header, index) in filteredTableHeaderWithoutAddress"
        :key="index"
        :prop="header.toLowerCase()"
        :label="getHeaderLabel(header)"
        :min-width="addressFilteredWidthList[index]"
        :show-overflow-tooltip="!['帧类型', 'IEC104类型'].includes(header)"
        :sortable="['功能码', '解析码'].includes(header) ? 'custom' : false"
        :filters="header === '帧类型' ? tagFilters : header === 'IEC104类型' ? iec104TypeFilters : undefined"
        :column-key="header"
        :fixed="['帧类型', '状态'].includes(header) ? 'right' : undefined"
      >
        <template #header>
          <div class="header-content">
            <span>{{ getHeaderLabel(header) }}</span>
            <el-tooltip v-if="shouldShowTooltip(header)" effect="dark" placement="top">
              <template #content>
                <div v-if="header === '解析码'">{{ toolTip }}</div>
                <div v-else-if="header === '功能码'">{{ funcCodeToolTip }}</div>
                <div v-else>{{ $t('table.algHint') }}</div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
        </template>

        <template #default="scope">
          <el-tag
            v-if="header === '帧类型'"
            :type="getTagType(scope.row[header])"
            effect="light"
            class="status-tag"
          >
            {{ translateFrameType(scope.row[header]) }}
          </el-tag>
          <el-tag
            v-else-if="header === 'IEC104类型' && scope.row[header]"
            :type="getIec104TagType(getIec104TypeLabelKey(scope.row[header]))"
            effect="light"
            class="status-tag"
          >
            {{ locale === 'en-US' ? scope.row[header] : t(getIec104TypeLabelKey(scope.row[header])) }}
          </el-tag>
          <div v-else-if="header === '状态'" class="status-cell">
            <template v-if="scope.row._isVirtualDa">
              <!-- 虚拟 DA 节点（如 q/t）不显示状态图标 -->
            </template>
            <template v-else>
              <el-icon v-if="scope.row[header] === '成功'" color="#67C23A" size="20"><CircleCheckFilled /></el-icon>
              <el-icon v-else-if="scope.row[header] === '失败'" color="#F56C6C" size="20"><CircleCloseFilled /></el-icon>
              <el-icon v-else color="#909399" size="20"><RemoveFilled /></el-icon>
            </template>
          </div>
          <span v-else class="cell-text" :class="{
            'high-contrast': header === '测点编码',
            'do-name': scope.row._isDoRow && header === '测点名称',
          }">
            {{ (scope.row._isBdaRow && header === '测点名称') ? (scope.row._bdaName || scope.row._daPath) : (scope.row._isDaRow && header === '测点名称' && scope.row._daDisplayName) ? scope.row._daDisplayName : scope.row[header] }}
          </span>
        </template>
      </el-table-column>

      <!-- 操作列（DataSet 扁平模式隐藏写入按钮） -->
      <el-table-column
        v-if="props.iec61850Category !== 'DataSets'"
        :label="$t('common.operation')"
        :width="isClientDevice || isIec61850WithActions ? 240 : 100"
        fixed="right"
      >
        <template #default="scope">
          <!-- DO 行: 读取 + 品质/时标按钮 (系统 DO 不支持，跳过) -->
          <div v-if="scope.row._isDoRow && !isSystemDo(scope.row._doName)" class="action-buttons">
            <el-button
              v-if="isIec61850Client && scope.row['测点编码']"
              type="primary"
              size="small"
              :icon="Download"
              @click="handleIec61850ReadPoint(scope.row['测点编码'])"
              :loading="readingPoints[scope.row['测点编码']]"
            >
              {{ $t('table.read') }}
            </el-button>
            <el-button
              v-if="isIec61850Client"
              size="small"
              :icon="InfoFilled"
              @click="handleIec61850ReadMetadata(scope.row._doRef)"
            >
              {{ $t('table.metadata') }}
            </el-button>
          </div>
          <!-- DA 行: 读取/写入按钮 -->
          <div v-if="!scope.row._isDoRow && !scope.row._isVirtualDa && scope.row['测点编码']" class="action-buttons">
            <!-- IEC61850 客户端: 读取 (所有行可读) -->
            <el-button
              v-if="isIec61850Client"
              type="primary"
              size="small"
              :icon="Download"
              @click="handleIec61850ReadPoint(scope.row['测点编码'])"
              :loading="readingPoints[scope.row['测点编码']]"
            >
              {{ $t('table.read') }}
            </el-button>
            <!-- IEC61850 服务端: 写入 (所有行可写，仿真设值) -->
            <el-button
              v-if="isIec61850Server"
              type="success"
              size="small"
              :icon="Edit"
              @click="handleIec61850WritePoint(scope.row)"
            >
              {{ $t('table.write') }}
            </el-button>
            <!-- IEC61850 客户端: 写入 (仅遥控/遥调，发送控制命令) -->
            <el-button
              v-if="isIec61850Client && [PointType.YK, PointType.YT].includes(getPointType(scope.row['帧类型']))"
              type="success"
              size="small"
              :icon="Edit"
              @click="handleIec61850WritePoint(scope.row)"
            >
              {{ $t('table.write') }}
            </el-button>
            <!-- 非 IEC61850 客户端: 读取 -->
            <el-button
              v-if="isClientDevice && !isIec61850Client"
              type="primary"
              size="small"
              :icon="Download"
              @click="handleReadPoint(scope.row['测点编码'])"
              :loading="readingPoints[scope.row['测点编码']]"
            >
              {{ $t('table.read') }}
            </el-button>
            <!-- 非 IEC61850 客户端: 写入 (Modbus: func_code=01/03 也可写; 其他协议仅遥控/遥调) -->
            <el-button
              v-if="isClientDevice && !isIec61850Client && (isModbusWriteable(scope.row) || [PointType.YK, PointType.YT].includes(getPointType(scope.row['帧类型'])))"
              type="success"
              size="small"
              :icon="Edit"
              @click="handleWritePoint(scope.row)"
            >
              {{ $t('table.write') }}
            </el-button>
            <el-popconfirm
              v-if="!isIec61850"
              :title="$t('table.deleteConfirm')"
              :confirm-button-text="$t('common.delete')"
              :cancel-button-text="$t('common.cancel')"
              @confirm="handleDeletePoint(scope.row['测点编码'])"
            >
              <template #reference>
                <el-button
                  type="danger"
                  size="small"
                  :icon="Delete"
                  :loading="deletingPoints[scope.row['测点编码']]"
                >
                  {{ $t('common.delete') }}
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页器 -->
    <div class="pagination-wrapper">
      <el-pagination
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
        :current-page="pageIndex"
        :page-sizes="[10, 20, 50, 100]"
        :page-size="pageSize"
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="effectiveTotal"
      />
    </div>
  </div>
  <WritePointDialog
    v-model="writeDialogVisible"
    :deviceName="deviceName"
    :pointCode="currentPoint.code"
    :currentValue="currentPoint.value"
    :pointType="currentPoint.type"
    :slaveId="slaveId"
    @success="handleWriteSuccess"
  />
  <!-- IEC61850 专用写入对话框 -->
  <Iec61850WriteDialog
    v-model="iec61850WriteDialogVisible"
    :channelId="channelId!"
    :pointCode="iec61850WritePointData.code"
    :currentValue="iec61850WritePointData.value"
    :pointType="iec61850WritePointData.type"
    @success="handleWriteSuccess"
  />
  <!-- IEC61850 品质/时标元数据弹窗 -->
  <el-dialog
    v-model="metadataDialogVisible"
    :title="$t('table.metadataTitle', { point: metadataPointCode })"
    width="620px"
    destroy-on-close
  >
    <template v-if="metadataResult">
      <el-descriptions :column="2" border size="small" title="品质 (Quality)">
        <el-descriptions-item :label="$t('table.qValidity')">
          <el-tag :type="metadataResult.quality.validity === 0 ? 'success' : 'danger'" size="small">
            {{ metadataResult.quality.validity ?? '-' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.qDetailQuality')">
          {{ metadataResult.quality.detailQuality ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.qSource')">
          {{ metadataResult.quality.source === 0 ? 'process' : metadataResult.quality.source === 1 ? 'substituted' : (metadataResult.quality.source ?? '-') }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.qTest')">
          <el-tag :type="metadataResult.quality.test ? 'warning' : 'success'" size="small">
            {{ metadataResult.quality.test ?? '-' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.qOperatorBlocked')" :span="2">
          <el-tag :type="metadataResult.quality.operatorBlocked ? 'warning' : 'success'" size="small">
            {{ metadataResult.quality.operatorBlocked ?? '-' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-descriptions :column="2" border size="small" :title="$t('table.tsTitle')" class="metadata-timestamp">
        <el-descriptions-item :label="$t('table.tsDatetime')" :span="2">
          <span style="font-family: monospace; font-size: 14px;">
            {{ formatTimestamp(metadataResult.timestamp.unixTimestampMs) }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.tsSeconds')">
          {{ metadataResult.timestamp.seconds ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.tsUnixMs')">
          {{ metadataResult.timestamp.unixTimestampMs ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.tsAccuracy')">
          {{ metadataResult.timestamp.timeAccuracy ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.tsLeapKnown')">
          <el-tag :type="metadataResult.timestamp.leapSecondsKnown === false ? 'success' : 'info'" size="small">
            {{ metadataResult.timestamp.leapSecondsKnown ?? '-' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.tsClockFailure')">
          <el-tag :type="metadataResult.timestamp.clockFailure ? 'danger' : 'success'" size="small">
            {{ metadataResult.timestamp.clockFailure ?? '-' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('table.tsClockNotSync')">
          <el-tag :type="metadataResult.timestamp.clockNotSynchronized ? 'warning' : 'success'" size="small">
            {{ metadataResult.timestamp.clockNotSynchronized ?? '-' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </template>
    <template v-else>
      <el-empty :description="$t('table.metadataEmpty')" />
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch, type PropType } from 'vue'
import { useRoute } from "vue-router"
import { useI18n } from 'vue-i18n'
import { QuestionFilled, Download, Edit, Delete, CircleCheckFilled, CircleCloseFilled, RemoveFilled, ArrowRight, InfoFilled } from "@element-plus/icons-vue"
import { ElMessage } from 'element-plus'
import { getPointType, PointType, getIec104TypeLabelKey } from '@/types/point'
import { readSinglePoint, deletePoint } from '@/api/pointApi'
import { iec61850ReadPoint, iec61850ReadPointMetadata } from '@/api/channelApi'
import type { IEC61850TreeDataResponse, Iec61850MetadataResponse } from '@/api/channelApi'
import { resolveDoReadPointCode } from '@/utils/iec61850Tree'
import {
  INT_REGISTER_DECODE_LIST,
  LONG_REGISTER_DECODE_LIST,
  FLOAT_REGISTER_DECODE_LIST,
  COLUMN_WIDTH_MAP,
  FRAME_TYPE_FILTERS,
  IEC104_TYPE_FILTERS,
  FRAME_TYPE_TAG_MAP,
  getIec104TagType,
  DECODE_CODE_TOOLTIP,
  FUNC_CODE_TOOLTIP,
  CLIENT_PROTOCOL_NAMES,
  HEADER_I18N_MAP,
} from '@/constants/table'

import SingleRegister from '../register/SingleRegister.vue'
import LongRegister from '../register/LongRegister.vue'
import FloatRegister from '../register/FloatRegister.vue'
import EditPointLimit from '../point/EditPointLimit.vue'
import PointSimulator from '../point/PointSimulator.vue'
import EditPointMetadata from '../point/EditPointMetadata.vue'
import EditPointIec104 from '../point/EditPointIec104.vue'
import PointMappingConfig from '../point/PointMappingConfig.vue'
import PointChangeHistory from '../point/PointChangeHistory.vue'
import WritePointDialog from './WritePointDialog.vue'
import Iec61850WriteDialog from './Iec61850WriteDialog.vue'

const { t, locale } = useI18n()

// ===== IEC61850 树形表格常量 =====

/** FC → 颜色映射 (类似 IECSCOUT) */
const IEC61850_FC_COLORS: Record<string, string> = {
  'MX': '#3b82f6',   // 蓝色 - 测量
  'ST': '#10b981',   // 绿色 - 状态
  'CO': '#f59e0b',   // 橙色 - 控制
  'CF': '#8b5cf6',   // 紫色 - 配置
  'DC': '#6b7280',   // 灰色 - 描述
  'EX': '#ef4444',   // 红色 - 扩展
  'SG': '#06b6d4',   // 青色 - 设定组
  'SR': '#6b7280',   // 灰色 - 替代
  'OR': '#f97316',   // 深橙 - 操作
  'BL': '#94a3b8',   // 浅灰 - 阻塞
}

const props = defineProps({
  slaveId: { type: Number, required: true },
  tableHeader: { type: Array as PropType<string[]>, required: true },
  tableData: { type: Array as PropType<any[]>, required: true },
  total: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  pageIndex: { type: Number, required: true },
  activeFilters: { type: Object as PropType<any>, required: true },
  protocolType: { type: [Number, String] as PropType<number | string>, default: 1 },
  isIec61850: { type: Boolean, default: false },
  iec61850TreeData: { type: Object as PropType<IEC61850TreeDataResponse | null>, default: null },
  iec61850Category: { type: String, default: '' },
  channelId: { type: Number as PropType<number | null>, default: null },
});

const emit = defineEmits(['update:pageSize', 'update:pageIndex', 'update:activeFilters', 'refresh', 'sort-change']);
const route = useRoute();
const deviceName = computed(() => route.params.deviceName as string);

/** 根据中文列名获取 i18n 翻译后的表头文本 */
const getHeaderLabel = (header: string): string => {
  const key = HEADER_I18N_MAP[header];
  return key ? t('table.' + key) : header;
};

/** 帧类型中文 → i18n key 映射 */
const FRAME_TYPE_I18N_MAP: Record<string, string> = {
  '遥测': 'meas',
  '遥信': 'status2',
  '遥控': 'control',
  '遥调': 'adjust',
};
/** 翻译帧类型 */
const translateFrameType = (val: string): string => {
  const key = FRAME_TYPE_I18N_MAP[val];
  return key ? t('table.' + key) : val;
};

const activeName = ref("数据解析和设置");
const expandedRowKeys = ref<string[]>([]);

// 切换设备时清空展开行，避免用旧pointCode请求新设备
watch(deviceName, () => {
  expandedRowKeys.value = [];
});

const intRegisterDecodeList = INT_REGISTER_DECODE_LIST;
const longRegisterDecodeList = LONG_REGISTER_DECODE_LIST;
const floatRegisterDecodeList = FLOAT_REGISTER_DECODE_LIST;

const isModbus = computed(() => {
  const t = props.protocolType;
  return t === 0 || t === 1 || (typeof t === 'string' && t.startsWith('Modbus'));
});

const isDlt645 = computed(() => typeof props.protocolType === 'string' && props.protocolType.includes('Dlt645'));

const isClientDevice = computed(() => {
  const t = String(props.protocolType);
  return (CLIENT_PROTOCOL_NAMES as readonly string[]).includes(t);
});

const isIec61850Server = computed(() => {
  return props.isIec61850 && String(props.protocolType) === 'Iec61850Server';
});

const isIec61850Client = computed(() => {
  return props.isIec61850 && String(props.protocolType) === 'Iec61850Client';
});

/** IEC61850 设备是否显示操作按钮 */
const isIec61850WithActions = computed(() => {
  return isIec61850Server.value || isIec61850Client.value;
});

const readingPoints = reactive<Record<string, boolean>>({});
const deletingPoints = reactive<Record<string, boolean>>({});
const showHexAddress = ref(false);

const isIec104 = computed(() => {
  const t = props.protocolType;
  return typeof t === 'string' && (t === 'Iec104Server' || t === 'Iec104Client');
});

const hiddenColumns = computed(() => {
  // 始终隐藏16进制地址列（已合并到地址列）
  const hidden = ['16进制地址', '地址'];
  
  // 非Modbus协议，隐藏相关专有列
  if (!isModbus.value) {
    hidden.push('位', '功能码', '解析码');
  }
  
  // 非IEC104协议，隐藏IEC104类型列
  if (!isIec104.value) {
    hidden.push('IEC104类型');
  }
  
  // 非客户端设备且非 IEC61850 设备，隐藏状态列
  if (!isClientDevice.value && !props.isIec61850) {
    hidden.push('状态');
  }
  
  // DataSet 扁平模式隐藏状态列（无实际意义）
  if (props.iec61850Category === 'DataSets') {
    hidden.push('状态');
  }

  // IEC61850 协议隐藏无意义列
  if (props.isIec61850) {
    hidden.push('寄存器值', '乘法系数', '加法系数', '帧类型');
  }

  // 非 IEC61850 协议隐藏 FC 列 (IEC61850 通过专用列渲染 FC)
  if (!props.isIec61850) {
    hidden.push('FC');
  }
  
  return hidden;
});

const filteredTableHeader = computed(() => props.tableHeader.filter(h => !hiddenColumns.value.includes(h)));
const filteredTableHeaderWithoutAddress = computed(() => filteredTableHeader.value);

// 列宽度映射已提取到 @/constants/table
const columnWidthMap = COLUMN_WIDTH_MAP;

// 根据当前可见列动态生成宽度列表
const addressFilteredWidthList = computed(() => {
  return filteredTableHeaderWithoutAddress.value.map(header => {
    return columnWidthMap[header] || columnWidthMap['default'];
  });
});

const getRowKey = (row: any) => {
  if (row._isDoRow) return row._rowKey;
  return row["测点编码"];
};
const handleExpand = (row: any, rows: any[]) => {
  if (row._isDoRow) return; // DO 行不处理展开详情
  const code = row["测点编码"];
  const isNowExp = rows.some(r => r["测点编码"] === code);
  expandedRowKeys.value = isNowExp ? [...expandedRowKeys.value, code] : expandedRowKeys.value.filter(c => c !== code);
};

// ===== IEC61850 树形数据 =====

/** IEC61850 DO 行展开/折叠控制 */
const iec61850ExpandedDoKeys = ref<string[]>([]);
const iec61850ExpandedDaKeys = ref<string[]>([]);
const toggleDoExpand = (doRef: string) => {
  const idx = iec61850ExpandedDoKeys.value.indexOf(doRef);
  if (idx >= 0) {
    iec61850ExpandedDoKeys.value.splice(idx, 1);
    // 收起 DO 时也收起其下所有 DA
    iec61850ExpandedDaKeys.value = iec61850ExpandedDaKeys.value.filter(
      (k: string) => !k.startsWith(doRef + '.')
    );
  } else {
    iec61850ExpandedDoKeys.value.push(doRef);
  }
};
const toggleDaExpand = (daKey: string) => {
  const idx = iec61850ExpandedDaKeys.value.indexOf(daKey);
  if (idx >= 0) {
    iec61850ExpandedDaKeys.value.splice(idx, 1);
  } else {
    iec61850ExpandedDaKeys.value.push(daKey);
  }
};

/** IEC61850 树形表格行样式 */
const iec61850RowClassName = ({ row }: { row: any }) => {
  if (row._isDoRow) return 'do-row';
  if (row._isDaRow) return 'da-row';
  if (row._isVirtualDa) return 'virtual-da-row';
  return '';
};

const tagFilters = FRAME_TYPE_FILTERS;

const iec104TypeFilters = computed(() =>
  IEC104_TYPE_FILTERS.map(f => ({ text: t(f.text), value: f.value }))
);

const handleFilterChange = (f: any) => emit('update:activeFilters', f);
const handleSortChange = ({ prop, order }: { prop: string, order: string | null }) => {
  emit('sort-change', { prop, order });
};

const convertedTableData = computed(() => {
  return props.tableData.map(row => {
    const data: any = {};
    row.forEach((val: any, i: number) => {
      if (i < props.tableHeader.length) {
        const h = props.tableHeader[i];
        let displayVal = val;
        if (displayVal === 'None' || displayVal === null) {
          displayVal = '';
        }
        data[h] = (h === '真实值') ? parseFloat(val || 0).toFixed(3) : displayVal;
      }
    });
    return data;
  });
});

const filteredData = computed(() => {
  return convertedTableData.value.filter((row: any) => {
    return Object.entries(props.activeFilters).every(([key, values]: [any, any]) => {
      if (!values.length) return true;
      if (key === '帧类型') {
        return values.includes(getPointType(row['帧类型']));
      }
      // 其他列（如IEC104类型）直接匹配单元格值
      return values.includes(row[key]);
    });
  });
});

/** 有效分页总数（IEC61850 DataSet 按扁平行数，其他按后端 total） */
const effectiveTotal = computed(() => {
  if (props.isIec61850 && props.iec61850TreeData) {
    // DataSet 扁平模式：items 展开后的总行数
    if (props.iec61850Category === 'DataSets') {
      let count = 0;
      for (const item of (props.iec61850TreeData.items || [])) {
        count += item.children?.length || 0;
      }
      return count;
    }
    // 树形模式：total 是 DO 数量
    return props.iec61850TreeData.total || 0;
  }
  return props.total;
});

/** 帧类型数字 → 标签映射 */
const FRAME_TYPE_LABELS: Record<number, string> = { 0: '遥测', 1: '遥信', 2: '遥控', 3: '遥调' };

/** IEC61850 树形数据: 将后端返回的树形结构扁平化为表格行 */
const iec61850FlatRows = computed(() => {
  if (!props.isIec61850 || !props.iec61850TreeData) return [];
  const items = props.iec61850TreeData.items || [];
  const result: any[] = [];

  // DataSets 模式：直接拼合 DA 到顶层，不需要 DO 行和下拉展开
  const isDataSet = props.iec61850Category === 'DataSets';

  for (const doNode of items) {
    const doRef = doNode.do_ref;
    const doName = doNode.du_name || doNode.do_name;

    if (isDataSet) {
      // DataSet 扁平模式：跳过 DO 行，直接平铺每个 DA 为独立行
      for (const daNode of (doNode.children || [])) {
        result.push({
          _isDaRow: false,
          _isFlatDa: true,
          _daPath: daNode.da_path,
          _fc: daNode.fc,
          '地址': `${doRef}.${daNode.da_path}`,
          '测点名称': `${doNode.do_name}.${daNode.da_path}`,
          '测点编码': daNode.point_code || '',
          '真实值': daNode.value || '',
          '16进制地址': '',
          'FC': daNode.fc,
          '最后更新时间': daNode.read_time || '',
        });
      }
      continue; // 跳过 DO 行逻辑
    }

    // === 以下为常规 DO/DA 树形模式（DataModel 等）===
    // 从 DO 的 DA 列表中查找主值作为根节点显示值
    const hasValue = (v: any) => v !== '' && v !== undefined && v !== null;
    const getDoDisplayValue = (daList: any[]): any => {
      const groups = [
        ['mag', 'cVal', 'instMag', 'mxVal'],
        ['stVal', 'ctlVal', 'setVal'],
      ];
      for (const group of groups) {
        for (const da of daList) {
          if (!group.includes(da.da_path)) continue;
          if (hasValue(da.value)) return da.value;
          if (da.children?.length) {
            for (const bda of da.children) {
              if (hasValue(bda.value)) return bda.value;
            }
          }
        }
      }
      return '';
    };
    const doValue = getDoDisplayValue(doNode.children || []) || doNode.value || '';
    // DO 行：使用模型实际返回的主值测点，兼容 mag.i、Oper.ctlVal 等路径。
    const readPointCode = resolveDoReadPointCode(doNode);
    result.push({
      _isDoRow: true,
      _rowKey: `do-${doRef}`,
      _doName: doNode.do_name,
      _doRef: doRef,
      _fc: doNode.fc,
      _daCount: doNode.children?.length || 0,
      _duName: doNode.du_name,
      '地址': doRef,
      '测点名称': doName,
      '测点编码': readPointCode,
      '帧类型': FRAME_TYPE_LABELS[doNode.frame_type] || '',
      '真实值': doValue,
      '16进制地址': '',
      'FC': doNode.fc,
      '状态': doNode.status || '',
    });

    // 仅当 DO 展开时才添加 DA/BDA 行
    if (!iec61850ExpandedDoKeys.value.includes(doRef)) continue;

    for (const daNode of (doNode.children || [])) {
      const daRow: any = {
        _isDaRow: true,
        _daPath: daNode.da_path,
        _daDisplayName: daNode.da_name,
        _fc: daNode.fc,
        _doRef: doRef,
        _isStructDa: daNode.is_struct,
        _bdaCount: daNode.children?.length || 0,
        _isVirtualDa: !daNode.point_code,
        '地址': `${doRef}.${daNode.da_path}`,
        '测点名称': daNode.point_name || daNode.da_name,
        '测点编码': daNode.point_code || '',
        '真实值': daNode.value || '',
        '16进制地址': '',
        'FC': daNode.fc,
        '帧类型': FRAME_TYPE_LABELS[doNode.frame_type] || '',
        '状态': daNode.status || '',
      };
      result.push(daRow);

      // 仅当结构体 DA 展开时才添加 BDA 行
      if (daNode.is_struct && iec61850ExpandedDaKeys.value.includes(`${doRef}.${daNode.da_path}`)) {
        for (const bdaNode of (daNode.children || [])) {
          result.push({
            _isBdaRow: true,
            _isDaRow: false,
            _parentDa: daNode.da_name,
            _bdaName: bdaNode.bda_name,
            _daPath: bdaNode.bda_path,
            _fc: bdaNode.fc,
            _doRef: doRef,
            '地址': `${doRef}.${bdaNode.bda_path}`,
            '测点名称': bdaNode.bda_name,
            '测点编码': bdaNode.point_code || '',
            '真实值': bdaNode.value || '',
            '16进制地址': '',
            'FC': bdaNode.fc,
            '帧类型': '',
            '状态': bdaNode.status || '',
          });
        }
      }
    }
  }
  return result;
});

/** 最终展示数据 (IEC61850 用树形扁平行叠加缓存元数据, 其他用扁平) */
const displayData = computed(() => {
  return props.isIec61850 ? iec61850DisplayRows.value : filteredData.value;
});

const handleSizeChange = (s: number) => { emit("update:pageSize", s); emit("update:pageIndex", 1); };
const handleCurrentChange = (p: number) => emit("update:pageIndex", p);
const getTagType = (v: string) => FRAME_TYPE_TAG_MAP[v] || 'info';

// getIec104TagType 已提取到 @/constants/table

const updatePointData = (idx: number, real: number, reg: number) => {
  if (idx !== -1) { props.tableData[idx][7] = reg; props.tableData[idx][8] = real; }
};

const handleMetadataUpdate = (newC: string, oldC: string) => {
  const idx = expandedRowKeys.value.indexOf(oldC);
  if (idx !== -1) expandedRowKeys.value[idx] = newC;
  emit('refresh');
};

const handlePointSimulatorUpdate = () => null;

/** 判断 Modbus 测点是否可写（功能码 01/03 对应线圈/保持寄存器，可读可写） */
const isModbusWriteable = (row: any) => {
  if (!isClientDevice.value || isIec61850Client.value) return false;
  if (!isModbus.value) return false;
  const funcCode = Number(row['功能码']);
  return funcCode === 1 || funcCode === 3;
};

const handleReadPoint = async (pointCode: string) => {
  readingPoints[pointCode] = true;
  try {
    const value = await readSinglePoint(deviceName.value, pointCode);
    if (value !== null) {
      ElMessage.success(t('table.readSuccess', { value }));
      emit('refresh');
    }
  } catch (e) {
    console.error(t('table.readFailed'), e);
  } finally {
    readingPoints[pointCode] = false;
  }
};

const writeDialogVisible = ref(false);
const currentPoint = reactive({
  code: '',
  value: '' as string | number,
  type: 0
});

const handleWritePoint = (row: any) => {
  currentPoint.code = row['测点编码'];
  currentPoint.value = row['真实值'];
  currentPoint.type = getPointType(row['帧类型']);
  writeDialogVisible.value = true;
};

const handleWriteSuccess = () => {
  emit('refresh');
};

// ===== IEC61850 品质/时标元数据读取 =====
const metadataDialogVisible = ref(false);
const metadataPointCode = ref('');
const metadataResult = ref<Iec61850MetadataResponse | null>(null);
const readingMetadata = ref<Record<string, boolean>>({});

/** 品质时标数据本地缓存（key: DO reference），避免被自动轮询刷新覆盖 */
const metadataCache = ref<Map<string, Iec61850MetadataResponse>>(new Map());

const SYSTEM_DOS = new Set(['Mod', 'Beh', 'Health', 'NamPlt', 'PhyHealth', 'Proxy', 'PhyNam']);
const isSystemDo = (name: string) => SYSTEM_DOS.has(name);

const formatTimestamp = (ms: number | null): string => {
  if (ms === null || ms === undefined) return '-';
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

const handleIec61850ReadMetadata = async (pointCode: string) => {
  if (!props.channelId) return;
  readingMetadata.value[pointCode] = true;
  metadataPointCode.value = pointCode;
  metadataResult.value = null;
  metadataDialogVisible.value = true;
  try {
    const result = await iec61850ReadPointMetadata(props.channelId, pointCode);
    metadataResult.value = result;

    // 缓存品质时标数据（用于表格 DA 子节点回显，不会被自动轮询刷新覆盖）
    if (result) {
      const newCache = new Map(metadataCache.value);
      newCache.set(pointCode, result);
      metadataCache.value = newCache;
    }
  } catch (e: any) {
    ElMessage.error(t('table.metadataFailed', { msg: e?.message || e }));
    metadataDialogVisible.value = false;
  } finally {
    readingMetadata.value[pointCode] = false;
  }
};

/** 将缓存的品质时标数据叠加到树形扁平行上，实现表格 DA 子节点回显 */
const iec61850DisplayRows = computed(() => {
  const baseRows = iec61850FlatRows.value;
  const cache = metadataCache.value;
  if (cache.size === 0) return baseRows;

  // quality 字段名 → BDA 名称映射（全小写）
  const qBdaMap: Record<string, keyof Iec61850MetadataResponse['quality']> = {
    'validity': 'validity',
    'detailquality': 'detailQuality',
    'source': 'source',
    'test': 'test',
    'operatorblocked': 'operatorBlocked',
  };
  // timestamp 字段名 → BDA 名称映射
  const tBdaMap: Record<string, keyof Iec61850MetadataResponse['timestamp']> = {
    'seconds': 'seconds',
    'fraction': 'fraction',
    'timeaccuracy': 'timeAccuracy',
    'leapsecondsknown': 'leapSecondsKnown',
    'clockfailure': 'clockFailure',
    'clocknotsynchronized': 'clockNotSynchronized',
    'clocknotsync': 'clockNotSynchronized',
  };

  return baseRows.map((row) => {
    const doRef: string = row._doRef || '';
    if (!doRef || !cache.has(doRef)) return row;

    const metadata = cache.get(doRef)!;
    const bdaName: string = ((row._bdaName || row._daPath || '') as string).toLowerCase().replace(/^q\.|^t\./, '');

    // DA 行: q（品质）
    if (row._isDaRow && (row._daPath === 'q')) {
      const v = metadata.quality.validity;
      const vt = v === 0 ? 'good' : v === 1 ? 'invalid' : v === 2 ? 'questionable' : '';
      return { ...row, '真实值': `q[${vt}]` };
    }
    // DA 行: t（时标）
    if (row._isDaRow && (row._daPath === 't')) {
      const ts = metadata.timestamp;
      let display = '';
      if (ts?.unixTimestampMs !== null && ts?.unixTimestampMs !== undefined) {
        display = formatTimestamp(ts.unixTimestampMs);
      } else if (ts?.seconds !== null && ts?.seconds !== undefined) {
        display = formatTimestamp(ts.seconds * 1000);
      } else {
        display = '-';
      }
      return { ...row, '真实值': display };
    }
    // BDA 子节点: q.*（t 暂不展开 BDA，保留为后续兼容）
    if (row._isBdaRow && (row._parentDa === 'q' || (row._daPath || '').startsWith('q.'))) {
      const key = qBdaMap[bdaName];
      if (key !== undefined) {
        return { ...row, '真实值': metadata.quality[key] !== null ? String(metadata.quality[key]!) : '', '状态': '已读取' };
      }
      return row;
    }
    // BDA 子节点: t.*
    if (row._isBdaRow && (row._parentDa === 't' || (row._daPath || '').startsWith('t.'))) {
      const key = tBdaMap[bdaName];
      if (key !== undefined) {
        return { ...row, '真实值': metadata.timestamp[key] !== null ? String(metadata.timestamp[key]!) : '', '状态': '已读取' };
      }
      return row;
    }
    return row;
  });
});

// ===== IEC61850 专用读写操作 =====

const handleIec61850ReadPoint = async (pointCode: string) => {
  if (!props.channelId) return;
  readingPoints[pointCode] = true;
  try {
    const result = await iec61850ReadPoint(props.channelId, pointCode);
    if (result && result.value !== null) {
      ElMessage.success(t('table.readSuccess', { value: result.value }));
      emit('refresh');
    } else {
      ElMessage.warning(t('table.readFailed'));
    }
  } catch (e: any) {
    ElMessage.error(t('table.iec61850ReadFailed', { msg: e?.message || e }));
  } finally {
    readingPoints[pointCode] = false;
  }
};

const iec61850WriteDialogVisible = ref(false);
const iec61850WritePointData = reactive({
  code: '',
  value: '' as string | number,
  type: 0,
});

const handleIec61850WritePoint = (row: any) => {
  iec61850WritePointData.code = row['测点编码'];
  iec61850WritePointData.value = row['真实值'];
  iec61850WritePointData.type = getPointType(row['帧类型']);
  iec61850WriteDialogVisible.value = true;
};

const handleDeletePoint = async (pointCode: string) => {
  deletingPoints[pointCode] = true;
  try {
    const success = await deletePoint(deviceName.value, pointCode);
    if (success) {
      ElMessage.success(t('table.deleteSuccess'));
      emit('refresh');
    } else {
      ElMessage.error(t('table.deleteFailed'));
    }
  } catch (e) {
  } finally {
    deletingPoints[pointCode] = false;
  }
};
const shouldShowTooltip = (header: string) => {
  if (['乘法系数', '加法系数'].includes(header)) return true;
  if (!isModbus.value) return false;
  return ['解析码', '功能码'].includes(header);
};

const toolTip = DECODE_CODE_TOOLTIP;
const funcCodeToolTip = FUNC_CODE_TOOLTIP;
</script>

<style lang="scss" scoped>
.modern-table-container {
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--sidebar-border);
  background-color: var(--panel-bg);
  position: relative;
}

.custom-table {
  --el-table-header-bg-color: #f8fafc;
  --el-table-border-color: var(--sidebar-border);
  
  border: none !important;
  
  /* 极致锁定：移除 Table 各大容器的所有外侧边框，确保只有内部分割线生效 */
  :deep(.el-table__inner-wrapper),
  :deep(.el-table__header-wrapper),
  :deep(.el-table__body-wrapper) {
    border-left: none !important;
    border-right: none !important;
    &::before, &::after { display: none !important; }
  }

  /* 剥离所有单元格的最左和最右边框，确保完全由外层 modern-table-container 负责边界 */
  :deep(.el-table__cell) {
    border-right: 1px solid var(--sidebar-border) !important;
    border-bottom: 1px solid var(--sidebar-border) !important;
    
    &:first-child { border-left: none !important; }
    &:last-child { border-right: none !important; }
  }

  :deep(.modern-header-cell) {
    background-color: #f8fafc !important;
    color: #475569;
    font-weight: 700;
    height: 48px;
    text-align: center;
    
    /* 让筛选图标和文字在同一行 */
    .cell {
      display: flex !important;
      align-items: center;
      justify-content: center;
      gap: 4px;
      white-space: nowrap;
    }
  }

  :deep(.modern-cell) {
    height: 52px;
    text-align: center;
  }
}

.pagination-wrapper {
  padding: 12px 16px;
  display: flex;
  justify-content: flex-start;
  background-color: #ffffff;
  border-top: 1px solid var(--sidebar-border);
}

.expand-wrapper {
  padding: 12px 16px;
  background-color: #f9fbfe;
  border: none;
}

/* 配置与控制区域改为左右分布 */
.control-grid {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

/* 属性编辑区域左右分布 */
.metadata-grid {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 16px;
}

/* 内部Tabs紧凑化 */
.inner-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 12px;
  }
  :deep(.el-tabs__item) {
    height: 32px;
    line-height: 32px;
    font-size: 13px;
    padding: 0 16px;
  }
}

/* 深色模式修正 */
body.theme-dark {
  .modern-table-container { border-color: #334155; }
  .custom-table {
    --el-table-header-bg-color: #1e293b;
    :deep(.el-table__cell) { border-color: #334155 !important; }
    :deep(.modern-header-cell) { background-color: #1e293b !important; color: #94a3b8; }
  }
  .pagination-wrapper { background-color: #0f172a; border-top-color: #334155; }
  .expand-wrapper { background-color: #0d1117; border-bottom-color: #334155; }
}

/* 地址列表头样式 */
.address-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.address-switch {
  --el-switch-on-color: #3b82f6;
  --el-switch-off-color: #94a3b8;
}

.status-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

/* ===== IEC61850 树形表格样式 ===== */

/* DO 行 (父行) 样式 - 保持与其他行一致的背景 */
:deep(.do-row) {
  font-weight: 600;

  /* 隐藏展开详情箭头 (DO 行不需要详情面板) */
  .el-table__expand-icon {
    visibility: hidden;
  }
}

/* 虚拟 DA 行 (q/t/dU 补充行) 样式 */
:deep(.virtual-da-row) {
  /* 隐藏展开详情箭头 (虚拟行不需要详情面板) */
  .el-table__expand-icon {
    visibility: hidden;
  }
}

/* DO 展开箭头 */
.do-expand-icon {
  transition: transform 0.2s;
  margin-right: 4px;
  cursor: pointer;
  color: #6b7280;
  font-size: 14px;

  &.is-expanded {
    transform: rotate(90deg);
  }
}

/* DO 行地址区域 */
.do-address {
  cursor: pointer;
  display: flex;
  align-items: center;
  font-weight: 700;
}

/* DA 行地址区域 (缩进+左对齐) */
.da-address {
  display: block;
  text-align: left;
  padding-left: 24px;

  &.is-struct-da {
    cursor: pointer;
  }
}
.bda-address {
  display: block;
  text-align: left;
  padding-left: 44px;
  color: #6b7280;
  font-size: 0.9em;
}
.da-expand-icon {
  transition: transform 0.2s;
  margin-right: 4px;
  &.is-expanded {
    transform: rotate(90deg);
  }
}

/* DA 行 (子行) 样式 - 保持与其他行一致 */
:deep(.da-row) {
}

/* DO 名称加粗 (保持正常颜色) */
.do-name {
  font-weight: 700 !important;
}

/* DA 路径样式 */
.da-path {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: #475569;
}

/* FC 标签 */
.fc-tag {
  border: none !important;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  min-width: 36px;
  text-align: center;
}

/* DO 子项数 badge */
.do-badge {
  display: inline-block;
  font-size: 11px;
  color: #6b7280;
  background: #f1f5f9;
  border-radius: 8px;
  padding: 1px 8px;
}

/* DO 原始名称 (当 dU 描述与 DO 名称不同时显示) */
.do-original-name {
  display: inline-block;
  font-size: 11px;
  color: #94a3b8;
  background: #f8fafc;
  border-radius: 4px;
  padding: 0 5px;
  margin-left: 4px;
}

/* DO/DA 标识标签 */
.do-da-tag {
  margin-left: 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  border-radius: 4px;
  padding: 0 5px;
  height: 18px;
  line-height: 18px;
  vertical-align: middle;
}
.do-tag {
  color: #3b82f6;
  border-color: #bfdbfe;
  background: #eff6ff;
}
.da-tag {
  color: #10b981;
  border-color: #a7f3d0;
  background: #ecfdf5;
}
.bda-tag {
  color: #6366f1;
  border-color: #c7d2fe;
  background: #eef2ff;
}

/* 深色模式 - IEC61850 树形 */
body.theme-dark {
  .do-name { color: inherit !important; }
  .do-address { color: #94a3b8; }
  .da-path { color: #94a3b8; }
  .bda-address { color: #64748b; }
  .do-badge { color: #94a3b8; background: #334155; }
  .do-original-name { color: #64748b; background: #1e293b; }
  .do-tag { color: #60a5fa; border-color: #1e3a5f; background: #1e293b; }
  .da-tag { color: #34d399; border-color: #064e3b; background: #0d2818; }
  .bda-tag { color: #818cf8; border-color: #312e81; background: #1e1b4b; }
}

.metadata-timestamp {
  margin-top: 12px;
}
</style>
