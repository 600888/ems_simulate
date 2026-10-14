<template>
  <div class="data-editor" :class="{ 'structured-editor': structured }">
    <div class="data-inputs">
      <div class="data-field">
        <label v-if="structured" :for="`${editorId}-type`">{{
          l("Data 类型", "Data type")
        }}</label>
        <el-select
          :id="`${editorId}-type`"
          v-model="type"
          :disabled="locked"
          @change="resetValue"
          ><el-option
            v-for="item in DLT698_DATA_TYPES"
            :key="item"
            :label="item"
            :value="item"
        /></el-select>
      </div>
      <div v-if="type !== 'Null' || structured" class="data-field">
        <label v-if="structured" :for="`${editorId}-value`">{{
          l("初始值", "Initial value")
        }}</label>
        <el-select
          v-if="type === 'Boolean'"
          :id="`${editorId}-value`"
          v-model="text"
          ><el-option label="true" value="true" /><el-option
            label="false"
            value="false"
        /></el-select>
        <el-input
          v-else-if="type !== 'Null'"
          :id="`${editorId}-value`"
          v-model="text"
          :type="complex ? 'textarea' : 'text'"
          :rows="complex ? 5 : undefined"
          :placeholder="placeholder"
        />
        <el-input
          v-else
          :id="`${editorId}-value`"
          model-value="null"
          disabled
        />
      </div>
    </div>
    <small>{{
      l(
        "原始值按精确 Data 保存；整数使用十进制字符串。",
        "Raw values retain typed Data; integers use decimal strings.",
      )
    }}</small>
    <small v-if="complex"
      >{{
        l("每个子项格式：", "Each child:")
      }}
      {"type":"UInt16","value":"2301"}</small
    >
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <details v-else-if="structured" class="data-preview">
      <summary>{{ l("查看 Data 预览", "View Data preview") }}</summary>
      <pre>{{ JSON.stringify(parsed, null, 2) }}</pre>
    </details>
    <pre v-else>{{ JSON.stringify(parsed, null, 2) }}</pre>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, useId, watch } from "vue";
import {
  DLT698_DATA_TYPES,
  type Dlt698Data,
  type Dlt698DataType,
} from "@/types/dlt698";
import { parseData } from "@/utils/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
const props = defineProps<{
  modelValue: Dlt698Data;
  locked?: boolean;
  structured?: boolean;
}>();
const editorId = useId();
const emit = defineEmits<{
  (e: "update:modelValue", data: Dlt698Data): void;
  (e: "valid", valid: boolean): void;
}>();
const l = useDlt698Text();
const type = ref<Dlt698DataType>(props.modelValue.type);
const text = ref("");
const complex = computed(() => ["Array", "Structure"].includes(type.value));
const placeholder = computed(() =>
  complex.value
    ? '[{"type":"UInt16","value":"2301"}]'
    : type.value.startsWith("Date")
      ? "2026-10-13T00:00:00"
      : type.value === "Time"
        ? "00:00:00"
        : type.value === "OctetString"
          ? "010203FF"
          : "0",
);
const parsed = computed(() => {
  try {
    return parseData(type.value, text.value);
  } catch {
    return null;
  }
});
const error = computed(() => {
  try {
    parseData(type.value, text.value);
    return "";
  } catch (e) {
    return String((e as Error).message);
  }
});
function resetValue() {
  text.value = complex.value
    ? "[]"
    : type.value === "Boolean"
      ? "false"
      : ["VisibleString", "Utf8String", "OctetString", "BitString"].includes(
            type.value,
          )
        ? ""
        : "0";
}
watch(
  () => props.modelValue,
  (data) => {
    type.value = data.type;
    text.value = Array.isArray(data.value)
      ? JSON.stringify(data.value, null, 2)
      : data.value === null
        ? ""
        : String(data.value);
  },
  { immediate: true },
);
watch(
  [type, text],
  () => {
    emit("valid", parsed.value !== null);
    if (
      parsed.value &&
      JSON.stringify(parsed.value) !== JSON.stringify(props.modelValue)
    )
      emit("update:modelValue", parsed.value);
  },
  { immediate: true },
);
</script>
<style scoped>
.data-editor {
  min-width: 0;
  display: grid;
  gap: 10px;
  width: 100%;
}
.data-inputs {
  display: grid;
  gap: 10px;
  min-width: 0;
}
.data-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.data-field label {
  color: var(--text-primary);
  font-size: 13px;
  line-height: 20px;
}
.data-field :deep(.el-select),
.data-field :deep(.el-input) {
  width: 100%;
  min-width: 0;
}
.structured-editor {
  gap: 12px;
}
.structured-editor .data-inputs {
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}
.data-preview {
  border: 1px solid var(--border-color);
  border-radius: 6px;
  overflow: hidden;
}
.data-preview summary {
  padding: 10px 14px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  line-height: 20px;
}
.data-preview summary:hover {
  color: var(--el-color-primary);
}
.data-preview summary:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}
.data-preview pre {
  border-top: 1px solid var(--border-color);
  border-radius: 0;
}
@container (max-width: 560px) {
  .structured-editor .data-inputs {
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
  }
}
small {
  font-size: 12px;
  line-height: 20px;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
}
pre {
  margin: 0;
  padding: 12px;
  background: var(--bg-subtle);
  border-radius: 6px;
  overflow: auto;
  max-height: 200px;
}
</style>
