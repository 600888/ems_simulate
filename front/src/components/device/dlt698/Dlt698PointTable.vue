<template>
  <div class="point-table">
    <el-table
      :data="pageRows"
      row-key="code"
      border
      stripe
      @selection-change="emit('selection', $event)"
    >
      <el-table-column type="expand" width="42">
        <template #default="{ row }">
          <div class="detail">
            <PointDetailTabs
              v-model="active[row.code]"
              :client="role === 'client'"
            >
              <template #configControl>
                <div class="control">
                  <Dlt698ValueControl
                    :point="row"
                    :role="role"
                    :busy="busy"
                    :loading="savingValueCode === row.code"
                    :disabled="
                      preview ||
                      (role === 'server'
                        ? !can('local_values')
                        : !can('set') || !row.writable)
                    "
                    @save="emit('set-value', row, $event)"
                  />
                  <EditPointLimit
                    v-if="!preview && role === 'server' && scalar(row)"
                    :device-name="deviceName"
                    :point-code="row.code"
                    :active="active[row.code] === 'configControl'"
                  />
                </div>
              </template>
              <template #propertyEdit>
                <Dlt698PointDialog
                  inline
                  :model-value="true"
                  :point="row"
                  :role="role"
                  :busy="busy"
                  :loading="savingPointCode === row.code"
                  :save-error="saveError"
                  @save="emit('save', $event, row)"
                />
              </template>
              <template #pointMapping
                ><PointMappingConfig
                  v-if="!preview && can('mapping') && scalar(row)"
                  :device-name="deviceName"
                  :target-point-code="row.code"
                  :active="active[row.code] === 'pointMapping'" /><el-empty
                  v-else
                  :description="
                    l(
                      role === 'client'
                        ? '客户端测点可作为映射来源；目标映射请在服务端配置。'
                        : '此 Data 类型请使用精确值编辑，标量类型可配置测点映射。',
                      role === 'client'
                        ? 'Client points can be mapping sources. Configure target mappings on the server.'
                        : 'Use typed editing for this Data type. Scalar points support mapping.',
                    )
                  "
                  :image-size="60"
              /></template>
              <template #simulation
                ><PointSimulator
                  v-if="!preview && can('simulation') && scalar(row)"
                  :device-name="deviceName"
                  :point-code="row.code"
                  :active="active[row.code] === 'simulation'" /><el-empty
                  v-else
                  :description="
                    l(
                      '此 Data 类型请使用精确值编辑，标量类型可配置仿真模拟',
                      'Use typed editing for this Data type. Scalar points support simulation',
                    )
                  "
                  :image-size="60"
              /></template>
              <template #changeHistory
                ><PointChangeHistory
                  v-if="!preview && can('history')"
                  :device-name="deviceName"
                  :point-code="row.code"
                  :active="active[row.code] === 'changeHistory'" /><el-empty
                  v-else
                  :description="
                    l(
                      '界面预览不记录设备值变化',
                      'UI previews do not record device changes',
                    )
                  "
                  :image-size="60"
              /></template>
            </PointDetailTabs>
          </div>
        </template>
      </el-table-column>
      <el-table-column type="selection" width="42" reserve-selection />
      <el-table-column prop="oad" label="OAD" width="120"
        ><template #default="{ row }"
          ><code>{{ row.oad }}</code></template
        ></el-table-column
      >
      <el-table-column
        prop="name"
        :label="l('测点名称', 'Point name')"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        prop="data_type"
        :label="l('Data 类型', 'Data type')"
        width="100"
      />
      <el-table-column
        :label="l('原始值', 'Raw value')"
        min-width="155"
        show-overflow-tooltip
        ><template #default="{ row }">{{
          dataText(displayData(row))
        }}</template></el-table-column
      >
      <el-table-column
        :label="l('工程值', 'Engineering value')"
        min-width="160"
        show-overflow-tooltip
        ><template #default="{ row }">{{
          engineeringText(displayData(row), row.scaler)
        }}</template></el-table-column
      >
      <el-table-column prop="unit" :label="l('单位', 'Unit')" width="75" />
      <el-table-column :label="l('结果', 'Result')" min-width="140"
        ><template #default="{ row }"
          ><el-tooltip
            :content="row.result?.message || ''"
            :disabled="!row.result?.message"
            ><el-tag :type="resultType(row)" size="small">{{
              resultText(row)
            }}</el-tag></el-tooltip
          ></template
        ></el-table-column
      >
      <el-table-column
        :label="l('上次有效时间', 'Last good time')"
        min-width="210"
        ><template #default="{ row }">{{
          formatBeijingDateTime(row.last_good_at)
        }}</template></el-table-column
      >
      <el-table-column :label="l('操作', 'Actions')" width="170" fixed="right"
        ><template #default="{ row }"
          ><el-button
            v-if="role === 'client'"
            link
            type="primary"
            :disabled="!can('get') || busy"
            :loading="readingCode === row.code"
            @click="emit('read', row)"
            >{{ l("读取", "Read") }}</el-button
          ><el-button
            link
            type="primary"
            :disabled="!can('points') && !preview"
            @click="emit('edit', row)"
            >{{ l("编辑", "Edit") }}</el-button
          ><el-popconfirm
            :title="l('删除此测点？', 'Delete this point?')"
            @confirm="emit('delete', row)"
            ><template #reference
              ><el-button
                link
                type="danger"
                :disabled="!can('points') && !preview"
                >{{ l("删除", "Delete") }}</el-button
              ></template
            ></el-popconfirm
          ></template
        ></el-table-column
      >
      <template #empty
        ><el-empty
          :description="
            l(
              '暂无测点，请添加测点或从标准目录选择',
              'No points. Add a point or select from the standard catalog.',
            )
          "
          :image-size="70"
      /></template>
    </el-table>
    <div class="pagination">
      <span
        >{{ l("共", "Total") }} {{ points.length }}
        {{ l("个测点", "points") }}</span
      ><el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :page-sizes="[10, 20, 50]"
        layout="sizes, prev, pager, next"
        :total="points.length"
      />
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import type {
  Dlt698Data,
  Dlt698Feature,
  Dlt698Point,
  Dlt698Role,
} from "@/types/dlt698";
import { dataText, engineeringText } from "@/utils/dlt698";
import { formatBeijingDateTime } from "@/utils/beijingTime";
import { useDlt698Text } from "@/composables/useDlt698Text";
import PointDetailTabs from "@/components/point/PointDetailTabs.vue";
import PointMappingConfig from "@/components/point/PointMappingConfig.vue";
import PointSimulator from "@/components/point/PointSimulator.vue";
import PointChangeHistory from "@/components/point/PointChangeHistory.vue";
import Dlt698ValueControl from "./Dlt698ValueControl.vue";
import Dlt698PointDialog from "./Dlt698PointDialog.vue";
import EditPointLimit from "@/components/point/EditPointLimit.vue";
const props = defineProps<{
  points: Dlt698Point[];
  role: Dlt698Role;
  deviceName: string;
  preview?: boolean;
  busy?: boolean;
  readingCode?: string;
  savingValueCode?: string;
  savingPointCode?: string;
  saveError?: string;
  can: (feature: Dlt698Feature) => boolean;
}>();
const emit = defineEmits<{
  (e: "selection", points: Dlt698Point[]): void;
  (e: "save", point: Dlt698Point, original: Dlt698Point): void;
  (e: "set-value", point: Dlt698Point, value: Dlt698Data): void;
  (
    e: "read" | "edit" | "delete" | "write" | "local-edit",
    point: Dlt698Point,
  ): void;
}>();
const l = useDlt698Text(),
  page = ref(1),
  size = ref(10),
  active = reactive<Record<string, string>>({});
watch(
  () => props.points,
  (points) => {
    points.forEach((p) => {
      active[p.code] ||= "configControl";
    });
    page.value = Math.min(
      page.value,
      Math.max(1, Math.ceil(points.length / size.value)),
    );
  },
  { immediate: true },
);
const pageRows = computed(() =>
  props.points.slice((page.value - 1) * size.value, page.value * size.value),
);
function displayData(point: Dlt698Point) {
  return (
    point.result?.data ||
    point.last_good ||
    (props.role === "server" ? point.initial_value : undefined)
  );
}
function scalar(point: Dlt698Point) {
  return /^(?:U?Int(?:8|16|32)|Float(?:32|64))$/.test(point.data_type);
}
function resultType(
  point: Dlt698Point,
): "success" | "warning" | "danger" | "info" {
  return point.result?.kind === "data"
    ? "success"
    : point.result?.kind === "dar"
      ? "warning"
      : ["transport_error", "validation_error"].includes(
            point.result?.kind || "",
          )
        ? "danger"
        : "info";
}
function resultText(point: Dlt698Point) {
  const kind = point.result?.kind;
  if (kind === "dar") return `DAR = ${point.result?.dar}`;
  if (kind === "data") return l("有效 Data", "Valid Data");
  if (kind === "transport_error")
    return l("传输错误 · 保留上次值", "Transport error · retained");
  if (kind === "validation_error")
    return l("标准校验失败", "Validation failed");
  if (kind === "unknown") return l("结果未知", "Outcome unknown");
  return l("尚未读取", "Not read");
}
</script>
<style scoped>
.point-table {
  container-type: inline-size;
  min-width: 0;
}
.detail {
  box-sizing: border-box;
  max-width: 100cqw;
  padding: 16px 24px;
  background: var(--bg-subtle);
}
.control {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--text-secondary);
  font-size: 13px;
}
.edit-button {
  margin-top: 12px;
}
:deep(.el-table th.el-table__cell) {
  background: var(--table-header-bg);
}
:deep(.el-table__expanded-cell) {
  padding: 0;
}
:deep(.inner-tabs .el-tabs__header) {
  margin-bottom: 12px;
}
:deep(.inner-tabs .el-tabs__item) {
  height: 32px;
  line-height: 32px;
  font-size: 13px;
  padding: 0 16px;
}
small {
  color: var(--text-secondary);
}
</style>
