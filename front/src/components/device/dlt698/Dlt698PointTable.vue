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
                  <Dlt698DataTree
                    :data="displayData(row) || row.initial_value"
                  />
                  <el-button
                    :disabled="
                      (!preview && !can('local_values')) || role !== 'server'
                    "
                    @click="emit('local-edit', row)"
                    >{{
                      l("本地修改发布值", "Edit local published value")
                    }}</el-button
                  >
                  <el-button
                    :disabled="
                      (!preview && !can('set')) ||
                      !row.writable ||
                      role !== 'client'
                    "
                    @click="emit('write', row)"
                    >SET</el-button
                  >
                  <small>{{
                    l(
                      "本地赋值不授予远端写权限。",
                      "Local assignment does not grant remote write permission.",
                    )
                  }}</small>
                </div>
              </template>
              <template #propertyEdit
                ><el-descriptions :column="2" border
                  ><el-descriptions-item label="OAD">{{
                    row.oad
                  }}</el-descriptions-item
                  ><el-descriptions-item label="Data">{{
                    row.data_type
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="l('标准倍率', 'Scaler')"
                    >10 ^ {{ row.scaler }}</el-descriptions-item
                  ><el-descriptions-item :label="l('单位', 'Unit')">{{
                    row.unit || "—"
                  }}</el-descriptions-item></el-descriptions
                ><el-button
                  class="edit-button"
                  :disabled="!can('points') && !preview"
                  @click="emit('edit', row)"
                  >{{ l("编辑测点属性", "Edit point metadata") }}</el-button
                ></template
              >
              <template #pointMapping
                ><PointMappingConfig
                  v-if="!preview && can('mapping')"
                  :device-name="deviceName"
                  :target-point-code="row.code"
                  :active="active[row.code] === 'pointMapping'" /><el-empty
                  v-else
                  :description="
                    l(
                      '测点映射等待类型安全后端接入',
                      'Point mapping awaits a type-safe backend',
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
                      '此 Data 类型或运行时尚不支持模拟',
                      'Simulation unavailable for this Data type or runtime',
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
                      '变化回溯等待后端接入',
                      'Change history awaits backend integration',
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
        min-width="190"
        ><template #default="{ row }">{{
          row.last_good_at || "—"
        }}</template></el-table-column
      >
      <el-table-column :label="l('操作', 'Actions')" width="170" fixed="right"
        ><template #default="{ row }"
          ><el-button
            v-if="role === 'client'"
            link
            type="primary"
            :disabled="!can('get') || busy"
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
import type { Dlt698Feature, Dlt698Point, Dlt698Role } from "@/types/dlt698";
import { dataText, engineeringText } from "@/utils/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
import PointDetailTabs from "@/components/point/PointDetailTabs.vue";
import PointMappingConfig from "@/components/point/PointMappingConfig.vue";
import PointSimulator from "@/components/point/PointSimulator.vue";
import PointChangeHistory from "@/components/point/PointChangeHistory.vue";
import Dlt698DataTree from "./Dlt698DataTree.vue";
const props = defineProps<{
  points: Dlt698Point[];
  role: Dlt698Role;
  deviceName: string;
  preview?: boolean;
  busy?: boolean;
  can: (feature: Dlt698Feature) => boolean;
}>();
const emit = defineEmits<{
  (e: "selection", points: Dlt698Point[]): void;
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
.detail {
  padding: 18px 24px;
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
small {
  color: var(--text-secondary);
}
</style>
