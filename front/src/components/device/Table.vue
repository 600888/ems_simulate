<template>
  <div>
    <el-table
      :data="filteredData"
      :header-cell-style="{ textAlign: 'center' }"
      :cell-style="{ textAlign: 'center' }"
      :cell-class-name="cellStyle"
      @filter-change="handleFilterChange"
      border
      style="width: 100%"
      :row-key="getRowKey"
      @expand-change="handleExpand"
      :expand-row-keys="expandedRowKeys"
    >
      <el-table-column type="expand">
        <template #default="scope">
          <el-tabs v-model="activeName" type="card" class="tabs">
            <el-tab-pane label="数据解析和设置" name="数据解析和设置">
              <div class="register-container">
                <SingleRegister
                  v-if="intRegisterDecodeList.includes(scope.row['解析码'])"
                  :rowIndex="scope.$index"
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                  :realValue="parseFloat(scope.row['真实值'] || 0)"
                  :mulCoe="scope.row['乘法系数'] || 1"
                  :addCoe="scope.row['加法系数'] || 0"
                  @editSuccess="updatePointData"
                />
                <LongRegister
                  v-if="longRegisterDecodeList.includes(scope.row['解析码'])"
                  :rowIndex="scope.$index"
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                  :realValue="parseFloat(scope.row['真实值'] || 0)"
                  :mulCoe="scope.row['乘法系数'] || 1"
                  :addCoe="scope.row['加法系数'] || 0"
                  @editSuccess="updatePointData"
                />
                <FloatRegister
                  v-if="floatRegisterDecodeList.includes(scope.row['解析码'])"
                  :rowIndex="scope.$index"
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                  :realValue="parseFloat(scope.row['真实值'] || 0)"
                  :mulCoe="scope.row['乘法系数'] || 1"
                  :addCoe="scope.row['加法系数'] || 0"
                  @editSuccess="updatePointData"
                />
                <EditPointLimit
                  :deviceName="deviceName"
                  :pointCode="scope.row['测点编码']"
                />
              </div>
            </el-tab-pane>
            <el-tab-pane label="数据模拟" name="数据模拟">
              <PointSimulator
                :deviceName="deviceName"
                :pointCode="scope.row['测点编码']"
                @update-success="handlePointSimulatorUpdate"
              />
            </el-tab-pane>
            <el-tab-pane label="测点编辑" name="测点编辑">
              <EditPointMetadata
                :deviceName="deviceName"
                :pointCode="scope.row['测点编码']"
                @update-success="(newCode) => handleMetadataUpdate(newCode, scope.row['测点编码'])"
              />
            </el-tab-pane>
          </el-tabs>
        </template>
      </el-table-column>
      <el-table-column
        v-for="(header, index) in filteredTableHeader"
        :key="index"
        :prop="header.toLowerCase()"
        :label="header"
        :min-width="widthList[index]"
        show-overflow-tooltip
        :filters="index === filteredTableHeader.length - 1 ? tagFilters : undefined"
        filter-placement="bottom-end"
        confirm-text="确定"
        reset-text="重置"
        :fixed="index === filteredTableHeader.length - 1 ? 'right' : undefined"
      >
        <!-- 提示 -->
        <template #header>
          <el-tooltip v-if="header === '解析码'" effect="dark" :content="toolTip" placement="top">
            <div class="header-with-tooltip">
              <span>{{ header }}</span>
              <el-icon><QuestionFilled /></el-icon>
            </div>
          </el-tooltip>
          <el-tooltip v-else-if="header === '乘法系数'" effect="dark" placement="top">
            <template #content>
              <div>客户端(接收): 真实值 = 寄存器值 × 乘法系数 + 加法系数</div>
              <div>服务端(发送): 寄存器值 = (真实值 - 加法系数) ÷ 乘法系数</div>
            </template>
            <div class="header-with-tooltip">
              <span>{{ header }}</span>
              <el-icon><QuestionFilled /></el-icon>
            </div>
          </el-tooltip>
          <el-tooltip v-else-if="header === '加法系数'" effect="dark" placement="top">
            <template #content>
              <div>客户端(接收): 真实值 = 寄存器值 × 乘法系数 + 加法系数</div>
              <div>服务端(发送): 寄存器值 = (真实值 - 加法系数) ÷ 乘法系数</div>
            </template>
            <div class="header-with-tooltip">
              <span>{{ header }}</span>
              <el-icon><QuestionFilled /></el-icon>
            </div>
          </el-tooltip>
          <span v-else>{{ header }}</span>
        </template>

        <template #default="scope">
          <!-- 条件渲染最后一行的标签 -->
          <el-tag
            v-if="index === filteredTableHeader.length - 1"
            :type="getTagType(scope.row[header])"
          >
            {{ scope.row[header] }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
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
</template>

<script setup lang="ts" name="DeviceTable">
import { ref, computed, type PropType } from 'vue'
import SingleRegister from '../register/SingleRegister.vue'
import LongRegister from '../register/LongRegister.vue'
import FloatRegister from '../register/FloatRegister.vue'
import EditPointLimit from '../point/EditPointLimit.vue'
import PointSimulator from '../point/PointSimulator.vue'
import EditPointMetadata from '../point/EditPointMetadata.vue'

interface TableDataRow {
  [key: string]: any
}

const props = defineProps({
  slaveId: {
    type: Number,
    required: true
  },
  tableHeader: {
    type: Array as PropType<string[]>,
    required: true
  },
  tableData: {
    type: Array as PropType<any[]>,
    required: true
  },
  total: {
    type: Number,
    required: true
  },
  pageSize: {
    type: Number,
    required: true
  },
  pageIndex: {
    type: Number,
    required: true
  },
  activeFilters: {
    type: Object as PropType<any>,
    required: true
  },
  protocolType: {
    type: [Number, String] as PropType<number | string>,
    default: 1  // 默认 Modbus TCP
  }
})

// 协议类型判断
const isModbusProtocol = computed(() => {
  const type = props.protocolType;
  return type === 0 || type === 1 || (typeof type === 'string' && type.startsWith('Modbus'));
})

// DLT645 协议判断
const isDlt645Protocol = computed(() => {
  const type = props.protocolType;
  return typeof type === 'string' && type.includes('Dlt645');
})

// 需要隐藏的列（位和功能码）
const hiddenColumns = computed(() => {
  // Modbus 协议显示位和功能码
  if (isModbusProtocol.value) return [];
  // DLT645 协议也显示功能码（DI/控制码）
  if (isDlt645Protocol.value) return ['位'];
  // 其他协议默认隐藏
  return ['位', '功能码'];
})

// 过滤后的表头
const filteredTableHeader = computed(() => {
  return props.tableHeader.filter(header => !hiddenColumns.value.includes(header))
})

// 过滤后的宽度列表
const baseWidthList = [100, 100, 80, 100, 100, 280, 280, 150, 150, 120, 100, 100, 100]
const filteredWidthList = computed(() => {
  return baseWidthList.filter((_, index) => {
    const header = props.tableHeader[index]
    return !hiddenColumns.value.includes(header)
  })
})

// 响应式状态
const widthList = computed(() => filteredWidthList.value)
import { useRoute } from "vue-router";
import { getPointType, PointType, PointTypeMap } from '@/types/point'
const emit = defineEmits(['update:pageSize','update:pageIndex','update:activeFilters', 'refresh']); // 声明事件
const route = useRoute();
const deviceName = computed(() => route.name as string);
const intRegisterDecodeList = ref(["0x10","0x11","0x20","0x21","0x22","0xB0","0xB1","0xC0","0xC1"])
const longRegisterDecodeList = ref(["0x40","0x41","0x43","0x44","0xD0","0xD1","0xD4","0xD5","0x60","0x61","0xE0","0xE1"])
const floatRegisterDecodeList = ref(["0x42","0x45","0xD2","0xD3","0x62","0xE2"])
const toolTip = ref<string>(`解析码说明:
  16位: 0x20(无符号BE) 0x21(有符号BE) 0xC0(无符号LE) 0xC1(有符号LE)
  32位整数: 0x40(无符号BE) 0x41(有符号BE) 0xD0(无符号LE) 0xD1(有符号LE)
  32位浮点: 0x42(float BE) 0xD2(float LE)
  64位: 0x60-0x62(BE) 0xE0-0xE2(LE)`);

// 自动取第一个标签的name作为默认值
const activeName = ref("数据解析和设置")
// 响应式状态
const expandedRowKeys = ref<string[]>([])
const getRowKey = (row: TableDataRow) =>  row["测点编码"]  // 明确返回类型

// 展开状态处理
const handleExpand = (row: TableDataRow, expandedRows: TableDataRow[]) => {
  const isExpanded = expandedRows.some(r => r["测点编码"] === row["测点编码"])
  if (isExpanded) {
    // 展开时添加当前行key（使用Set避免重复）
    if (!expandedRowKeys.value.includes(row["测点编码"])) {
      expandedRowKeys.value = [...expandedRowKeys.value, row["测点编码"]]
    }
  } else {
    // 收起时移除当前行key
    expandedRowKeys.value = expandedRowKeys.value.filter(code => code !== row["测点编码"])
  }
}

const tagFilters = ref(
  [
    { text: '遥测', value: PointType.YC },
    { text: '遥信', value: PointType.YX },
    { text: '遥控', value: PointType.YK },
    { text: '遥调', value: PointType.YT }
  ]
)

const handleFilterChange = (filters: Record<string, string[]>) => {
  emit('update:activeFilters', filters);
}

const filteredData = computed(() => {
  return convertedTableData.value.filter((row: { [key: string]: any }) => {
    return Object.entries(props.activeFilters).every(([column, values]:[string,any]) => {
      if (values.length === 0) return true
      return values.includes(getPointType(row['帧类型']))
    })
  })
})


const convertedTableData = computed<TableDataRow[]>(() => {
  return props.tableData.map(row => {
    const rowData: TableDataRow = {}
    row.forEach((value: any, index: number) => {
      if (index < props.tableHeader.length) {
        const header = props.tableHeader[index]
        rowData[header] = index === props.tableHeader.length - 4
          ? parseFloat(value).toFixed(3)
          : value
      }
    })
    return rowData
  })
})

// 方法
const handleSizeChange = (newPageSize: number) => {
  emit("update:pageSize", newPageSize);
  emit("update:pageIndex", 1);
}

const handleCurrentChange = (newPage: number) => {
  emit("update:pageIndex", newPage);
}

const getTagType = (value: string) => {
  switch (value) {
    case '遥测': return 'success'
    case '遥信': return 'warning'
    case '遥控': return 'danger'
    case '遥调': return 'info'
    default: return 'info'
  }
}

const updatePointData = (rowIndex:number, realValue: number, registerValue: number) => {
  if (rowIndex !== -1) {
    props.tableData[rowIndex][7] = registerValue
    props.tableData[rowIndex][8] = realValue
  }
}
const cellStyle = () => 'cell-style'
const handlePointSimulatorUpdate = () => {
  // 当单点模拟设置更新成功时，可以在这里添加刷新表格数据的逻辑
  console.log('单点模拟设置已更新');
}
const handleMetadataUpdate = (newCode: string, oldCode: string) => {
  console.log('测点属性已更新', oldCode, '->', newCode);
  
  // 如果编码改变了，需要更新展开行的 key，否则该行会收起
  if (newCode !== oldCode) {
    const index = expandedRowKeys.value.indexOf(oldCode);
    if (index !== -1) {
      expandedRowKeys.value[index] = newCode;
    }
  }
  
  // 通知父组件刷新数据，不再使用 window.location.reload()
  emit('refresh');
}
</script>

<style>
.register-container {
  display: flex;
  flex-wrap: nowrap;
  gap: 20px;
  /* align-items: center; */
}

.simulator-layout {
  display: flex;
  flex-wrap: nowrap;
  gap: 20px;
}

.el-pagination {
  margin-top: 20px;
  text-align: right;
}

.cell-style {
  text-align: center; /* 单元格文字居中 */
  height: 50px;
  font-size: 16px;
  /* color: #eb3939; */
}
</style>
