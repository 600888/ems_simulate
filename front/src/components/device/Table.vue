<template>
  <div class="modern-table-container">
    <el-table
      :data="filteredData"
      class="custom-table"
      :cell-class-name="() => 'modern-cell'"
      :header-cell-class-name="() => 'modern-header-cell'"
      @filter-change="handleFilterChange"
      :row-key="getRowKey"
      @expand-change="handleExpand"
      :expand-row-keys="expandedRowKeys"
      border
      stripe
      style="width: 100%"
    >
      <!-- 展开详情区域 -->
      <el-table-column type="expand">
        <template #default="scope">
          <div class="expand-wrapper">
            <el-tabs v-model="activeName" class="inner-tabs">
              <el-tab-pane label="配置与控制" name="数据解析和设置">
                <div class="control-grid">
                  <SingleRegister
                    v-if="intRegisterDecodeList.includes(scope.row['解析码'])"
                    :rowIndex="scope.$index"
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :realValue="parseFloat(scope.row['真实值'] || 0)"
                    @editSuccess="updatePointData"
                  />
                  <LongRegister
                    v-if="longRegisterDecodeList.includes(scope.row['解析码'])"
                    :rowIndex="scope.$index"
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :realValue="parseFloat(scope.row['真实值'] || 0)"
                    @editSuccess="updatePointData"
                  />
                  <FloatRegister
                    v-if="floatRegisterDecodeList.includes(scope.row['解析码'])"
                    :rowIndex="scope.$index"
                    :deviceName="deviceName"
                    :pointCode="scope.row['测点编码']"
                    :realValue="parseFloat(scope.row['真实值'] || 0)"
                    @editSuccess="updatePointData"
                  />
                  <EditPointLimit :deviceName="deviceName" :pointCode="scope.row['测点编码']" />
                </div>
              </el-tab-pane>
              <el-tab-pane label="仿真模拟" name="数据模拟">
                <PointSimulator
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                  @update-success="handlePointSimulatorUpdate"
                />
              </el-tab-pane>
              <el-tab-pane label="属性编辑" name="测点编辑">
                <EditPointMetadata
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                  @update-success="(newCode) => handleMetadataUpdate(newCode, scope.row['测点编码'])"
                />
              </el-tab-pane>
            </el-tabs>
          </div>
        </template>
      </el-table-column>

      <!-- 地址列：合并10进制和16进制 -->
      <el-table-column
        label="地址"
        :min-width="130"
        show-overflow-tooltip
      >
        <template #header>
          <div class="header-content address-header">
            <span>地址</span>
            <el-switch
              v-model="showHexAddress"
              size="small"
              inline-prompt
              active-text="Hex"
              inactive-text="Dec"
              class="address-switch"
            />
          </div>
        </template>
        <template #default="scope">
          <span class="cell-text">
            {{ showHexAddress ? scope.row['16进制地址'] : scope.row['地址'] }}
          </span>
        </template>
      </el-table-column>

      <!-- 动态列渲染（排除地址列） -->
      <el-table-column
        v-for="(header, index) in filteredTableHeaderWithoutAddress"
        :key="index"
        :prop="header.toLowerCase()"
        :label="header"
        :min-width="addressFilteredWidthList[index]"
        show-overflow-tooltip
        :filters="index === filteredTableHeaderWithoutAddress.length - 1 ? tagFilters : undefined"
        :fixed="index === filteredTableHeaderWithoutAddress.length - 1 ? 'right' : undefined"
      >
        <template #header>
          <div class="header-content">
            <span>{{ header }}</span>
            <el-tooltip v-if="['解析码', '乘法系数', '加法系数'].includes(header)" effect="dark" placement="top">
              <template #content>
                <div v-if="header === '解析码'">{{ toolTip }}</div>
                <div v-else>算法: 真实值 = 寄存器值 × 系数 + 偏移量</div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
        </template>

        <template #default="scope">
          <el-tag
            v-if="index === filteredTableHeaderWithoutAddress.length - 1"
            :type="getTagType(scope.row[header])"
            effect="light"
            class="status-tag"
          >
            {{ scope.row[header] }}
          </el-tag>
          <span v-else class="cell-text" :class="{ 'high-contrast': header === '测点编码' }">
            {{ scope.row[header] }}
          </span>
        </template>
      </el-table-column>

      <!-- 操作列：仅客户端设备显示 -->
      <el-table-column
        v-if="isClientDevice"
        label="操作"
        width="100"
        fixed="right"
      >
        <template #default="scope">
          <el-button
            type="primary"
            size="small"
            :icon="Download"
            @click="handleReadPoint(scope.row['测点编码'])"
            :loading="readingPoints[scope.row['测点编码']]"
          >
            读取
          </el-button>
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
        :total="total"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, type PropType } from 'vue'
import { useRoute } from "vue-router"
import { QuestionFilled, Download } from "@element-plus/icons-vue"
import { ElMessage } from 'element-plus'
import { getPointType, PointType } from '@/types/point'
import { readSinglePoint } from '@/api/deviceApi'

import SingleRegister from '../register/SingleRegister.vue'
import LongRegister from '../register/LongRegister.vue'
import FloatRegister from '../register/FloatRegister.vue'
import EditPointLimit from '../point/EditPointLimit.vue'
import PointSimulator from '../point/PointSimulator.vue'
import EditPointMetadata from '../point/EditPointMetadata.vue'

const props = defineProps({
  slaveId: { type: Number, required: true },
  tableHeader: { type: Array as PropType<string[]>, required: true },
  tableData: { type: Array as PropType<any[]>, required: true },
  total: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  pageIndex: { type: Number, required: true },
  activeFilters: { type: Object as PropType<any>, required: true },
  protocolType: { type: [Number, String] as PropType<number | string>, default: 1 }
});

const emit = defineEmits(['update:pageSize', 'update:pageIndex', 'update:activeFilters', 'refresh']);
const route = useRoute();
const deviceName = computed(() => route.name as string);

const activeName = ref("数据解析和设置");
const expandedRowKeys = ref<string[]>([]);
const intRegisterDecodeList = ["0x10","0x11","0x20","0x21","0x22","0xB0","0xB1","0xC0","0xC1"];
const longRegisterDecodeList = ["0x40","0x41","0x43","0x44","0xD0","0xD1","0xD4","0xD5","0x60","0x61","0xE0","0xE1"];
const floatRegisterDecodeList = ["0x42","0x45","0xD2","0xD3","0x62","0xE2"];

const isModbus = computed(() => {
  const t = props.protocolType;
  return t === 0 || t === 1 || (typeof t === 'string' && t.startsWith('Modbus'));
});

const isDlt645 = computed(() => typeof props.protocolType === 'string' && props.protocolType.includes('Dlt645'));

const isClientDevice = computed(() => {
  const t = props.protocolType;
  return t === 'ModbusTcpClient' || t === 'Iec104Client' || t === 'Dlt645Client';
});

const readingPoints = reactive<Record<string, boolean>>({});
const showHexAddress = ref(false);

const hiddenColumns = computed(() => {
  // 始终隐藏16进制地址列（已合并到地址列）
  const hidden = ['16进制地址', '地址'];
  if (!isModbus.value && !isDlt645.value) hidden.push('位', '功能码');
  else if (isDlt645.value) hidden.push('位');
  return hidden;
});

const filteredTableHeader = computed(() => props.tableHeader.filter(h => !hiddenColumns.value.includes(h)));
const filteredTableHeaderWithoutAddress = computed(() => filteredTableHeader.value);

const baseWidths = [80, 100, 100, 200, 200, 150, 150, 120, 100, 100, 100];
const addressFilteredWidthList = computed(() => baseWidths.slice(0, filteredTableHeaderWithoutAddress.value.length));

const getRowKey = (row: any) => row["测点编码"];
const handleExpand = (row: any, rows: any[]) => {
  const code = row["测点编码"];
  const isNowExp = rows.some(r => r["测点编码"] === code);
  expandedRowKeys.value = isNowExp ? [...expandedRowKeys.value, code] : expandedRowKeys.value.filter(c => c !== code);
};

const tagFilters = [
  { text: '遥测', value: PointType.YC }, { text: '遥信', value: PointType.YX },
  { text: '遥控', value: PointType.YK }, { text: '遥调', value: PointType.YT }
];

const handleFilterChange = (f: any) => emit('update:activeFilters', f);

const convertedTableData = computed(() => {
  return props.tableData.map(row => {
    const data: any = {};
    row.forEach((val: any, i: number) => {
      if (i < props.tableHeader.length) {
        const h = props.tableHeader[i];
        data[h] = (i === props.tableHeader.length - 4) ? parseFloat(val).toFixed(3) : val;
      }
    });
    return data;
  });
});

const filteredData = computed(() => {
  return convertedTableData.value.filter((row: any) => {
    return Object.entries(props.activeFilters).every(([_, values]: [any, any]) => {
      return !values.length || values.includes(getPointType(row['帧类型']));
    });
  });
});

const handleSizeChange = (s: number) => { emit("update:pageSize", s); emit("update:pageIndex", 1); };
const handleCurrentChange = (p: number) => emit("update:pageIndex", p);
const getTagType = (v: string) => {
  const map: any = { '遥测': 'success', '遥信': 'warning', '遥控': 'danger', '遥调': 'info' };
  return map[v] || 'info';
};

const updatePointData = (idx: number, real: number, reg: number) => {
  if (idx !== -1) { props.tableData[idx][7] = reg; props.tableData[idx][8] = real; }
};

const handleMetadataUpdate = (newC: string, oldC: string) => {
  const idx = expandedRowKeys.value.indexOf(oldC);
  if (idx !== -1) expandedRowKeys.value[idx] = newC;
  emit('refresh');
};

const handlePointSimulatorUpdate = () => null;

const handleReadPoint = async (pointCode: string) => {
  readingPoints[pointCode] = true;
  try {
    const value = await readSinglePoint(deviceName.value, pointCode);
    if (value !== null) {
      ElMessage.success(`读取成功: ${value}`);
      emit('refresh');
    } else {
      ElMessage.warning('读取失败，请检查连接状态');
    }
  } catch (e) {
    ElMessage.error('读取失败');
  } finally {
    readingPoints[pointCode] = false;
  }
};

const toolTip = "解析码说明: 16位(0x20/21/C0/C1), 32位整(0x40/41/D0/D1), 32位浮(0x42/D2), 64位(0x60/61/E0/E1)";
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
</style>
