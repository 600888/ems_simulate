<template>
  <div>
    <h3>
      {{
        role === "client"
          ? l("记录查询", "Record queries")
          : l("记录管理", "Record management")
      }}
    </h3>
    <el-form inline label-width="100px" class="record-form">
      <el-form-item :label="l('记录模板', 'Template')"
        ><el-select
          v-model="query.template"
          @change="changeTemplate"
          style="width: 180px"
          ><el-option
            v-for="item in templates"
            :key="item.value"
            :value="item.value"
            :label="l(item.zh, item.en)" /></el-select
      ></el-form-item>
      <el-form-item label="OAD"
        ><el-input v-model="query.oad" style="width: 145px"
      /></el-form-item>
      <el-form-item :label="l('选择方式', 'Selector')"
        ><el-select v-model="query.selector" style="width: 200px"
          ><el-option
            value="all"
            :label="l('全部 · RSD 0', 'All · RSD 0')" /><el-option
            value="at"
            :label="l('精确时间 · RSD 1', 'At time · RSD 1')" /><el-option
            value="between"
            :label="l('时间区间 · RSD 2', 'Time range · RSD 2')" /><el-option
            value="sequences"
            :label="
              l('序号区间 · RSD 2', 'Sequence range · RSD 2')
            " /><el-option
            value="latest"
            :label="
              l('最近第 n 次 · RSD 9', 'Nth latest · RSD 9')
            " /></el-select
      ></el-form-item>
      <template v-if="['at', 'between'].includes(query.selector)"
        ><el-form-item :label="l('开始时间', 'Start time')"
          ><el-date-picker
            v-model="query.start"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item
        ><el-form-item
          v-if="query.selector === 'between'"
          :label="l('结束时间', 'End time')"
          ><el-date-picker
            v-model="query.end"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item
      ></template>
      <template v-if="query.selector === 'sequences'"
        ><el-form-item :label="l('开始序号', 'Start sequence')"
          ><el-input v-model="query.start" /></el-form-item
        ><el-form-item :label="l('结束序号', 'End sequence')"
          ><el-input v-model="query.end" /></el-form-item
      ></template>
      <el-form-item v-if="query.selector === 'latest'" label="n"
        ><el-input-number v-model="query.latest" :min="1" :max="65535"
      /></el-form-item>
      <el-form-item :label="l('返回列 OAD', 'Column OADs')"
        ><el-input
          v-model="columnText"
          style="width: 360px"
          placeholder="20210200, 00100201"
      /></el-form-item>
    </el-form>
    <el-alert
      :title="
        l(
          '区间为 [开始, 结束)，不包含结束值。表头按实际响应 RCSD 展示；GET Next 分块由后端收齐。',
          'Ranges are [start, end), excluding the end. Headers follow actual RCSD; the backend assembles GET Next blocks.',
        )
      "
      type="info"
      :closable="false"
      show-icon
    />
    <div class="actions">
      <el-button
        type="primary"
        :disabled="!enabled || busy"
        :loading="querying"
        @click="submit"
        >{{ l("查询", "Query") }}</el-button
      ><el-button :disabled="!querying" @click="emit('cancel')">{{
        l("取消查询", "Cancel query")
      }}</el-button
      ><el-button
        v-if="role === 'server'"
        :disabled="!enabled && !preview"
        @click="showAppend = true"
        >{{ l("新增记录", "Append record") }}</el-button
      ><el-tag v-if="result"
        >{{
          preview
            ? l("草稿记录", "Draft rows")
            : l("响应块数", "Response blocks")
        }}:
        {{
          preview
            ? result.rows.length
            : (result.blocks ?? l("库已自动组装", "Assembled by library"))
        }}</el-tag
      >
    </div>
    <el-alert
      v-if="error || localError"
      :title="error || localError"
      type="error"
      :closable="false"
    />
    <el-alert
      v-if="result?.dar != null"
      :title="`DAR = ${result.dar}`"
      type="warning"
      :closable="false"
    />
    <el-table :data="tableRows" border stripe>
      <el-table-column type="index" width="55" />
      <el-table-column
        v-for="(column, index) in columns"
        :key="`${column.oad}-${index}`"
        :label="`${column.name} · ${column.oad}`"
        min-width="200"
        ><template #default="{ row }"
          ><el-popover trigger="click" width="400"
            ><template #reference
              ><el-button link>{{ dataText(row[index]) }}</el-button></template
            ><Dlt698DataTree
              v-if="row[index]"
              :data="row[index]" /></el-popover></template
      ></el-table-column>
      <template #empty
        ><el-empty
          :description="
            result?.dar != null
              ? l('远端返回 DAR，未取得记录', 'Remote DAR: no records returned')
              : result
                ? l(
                    '查询成功，无匹配记录',
                    'Query succeeded: no matching records',
                  )
                : l('配置条件后发起查询', 'Configure conditions and query')
          "
          :image-size="70"
      /></template>
    </el-table>
    <el-dialog
      v-model="showAppend"
      :title="l('新增记录', 'Append record')"
      width="640px"
      :close-on-click-modal="false"
    >
      <p>
        {{
          l(
            "按返回列顺序填写精确 Data 数组，新增前校验类型与列数量。",
            "Enter typed Data in column order. Type and column count are validated.",
          )
        }}
      </p>
      <el-input
        v-model="rowText"
        type="textarea"
        :rows="8"
        placeholder='[{"type":"DateTimeS","value":"2026-10-13T00:00:00"},{"type":"UInt32","value":"123456"}]'
      />
      <el-alert
        v-if="appendError || localError"
        :title="appendError || localError"
        type="error"
        :closable="false"
      />
      <template #footer
        ><el-button @click="showAppend = false">{{
          l("取消", "Cancel")
        }}</el-button
        ><el-button
          type="primary"
          :disabled="busy"
          :loading="appending"
          @click="append"
          >{{
            preview
              ? l("添加到预览草稿", "Add to preview draft")
              : l("保存记录", "Save record")
          }}</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import type {
  Dlt698Data,
  Dlt698RecordQuery,
  Dlt698RecordResult,
  Dlt698Role,
} from "@/types/dlt698";
import {
  dataText,
  normalizeOad,
  validateData,
  validateRecordQuery,
} from "@/utils/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
import Dlt698DataTree from "./Dlt698DataTree.vue";
const props = defineProps<{
  role: Dlt698Role;
  enabled: boolean;
  preview?: boolean;
  busy: boolean;
  querying?: boolean;
  appending?: boolean;
  result?: Dlt698RecordResult;
  error?: string;
  appendError?: string;
  appendComplete?: number;
}>();
const emit = defineEmits<{
  (e: "query", query: Dlt698RecordQuery): void;
  (e: "cancel"): void;
  (e: "append", query: Dlt698RecordQuery, row: Dlt698Data[]): void;
}>();
const l = useDlt698Text(),
  columnText = ref("20210200, 00100201"),
  localError = ref(""),
  showAppend = ref(false),
  rowText = ref("");
const query = reactive<Dlt698RecordQuery>({
  template: "daily",
  oad: "50040200",
  selector: "all",
  start: "",
  end: "",
  latest: 1,
  columns: [],
});
const templates = [
  { value: "daily", oad: "50040200", zh: "日冻结", en: "Daily freeze" },
  { value: "monthly", oad: "50060200", zh: "月冻结", en: "Monthly freeze" },
  { value: "power_loss", oad: "30110200", zh: "掉电事件", en: "Power loss" },
  {
    value: "initialization",
    oad: "31000200",
    zh: "初始化事件",
    en: "Initialization",
  },
];
const columns = computed(
  () =>
    props.result?.columns ||
    columnText.value
      .split(",")
      .filter((x) => x.trim())
      .map((oad) => ({ oad: oad.trim(), name: "Data" })),
);
const tableRows = computed(() =>
  props.result?.dar != null ? [] : props.result?.rows || [],
);
function changeTemplate() {
  query.oad = templates.find((t) => t.value === query.template)!.oad;
}
function payload() {
  return {
    ...query,
    oad: normalizeOad(query.oad),
    columns: columnText.value
      .split(",")
      .filter((x) => x.trim())
      .map(normalizeOad),
  };
}
function submit() {
  localError.value = "";
  try {
    const value = payload();
    validateRecordQuery(value);
    emit("query", value);
  } catch (e) {
    localError.value = (e as Error).message;
  }
}
function append() {
  localError.value = "";
  try {
    const value = payload();
    const row: Dlt698Data[] = JSON.parse(rowText.value);
    if (!Array.isArray(row) || row.length !== value.columns.length)
      throw new Error(l("记录列数量不匹配", "Record column count mismatch"));
    row.forEach(validateData);
    emit("append", value, row);
  } catch (e) {
    localError.value = (e as Error).message;
  }
}
watch(
  () => props.appendComplete,
  () => {
    showAppend.value = false;
  },
);
watch(
  () => props.role,
  () => {
    showAppend.value = false;
  },
);
</script>
<style scoped>
.actions {
  display: flex;
  gap: 10px;
  margin: 16px 0;
  flex-wrap: wrap;
}
.record-form {
  margin: 16px 0;
}
h3 {
  margin: 0 0 16px;
}
p {
  color: var(--text-secondary);
}
</style>
