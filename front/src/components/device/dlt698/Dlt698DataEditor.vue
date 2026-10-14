<template>
  <div class="data-editor">
    <el-select v-model="type" :disabled="locked" @change="resetValue">
      <el-option
        v-for="item in DLT698_DATA_TYPES"
        :key="item"
        :label="item"
        :value="item"
      />
    </el-select>
    <el-select v-if="type === 'Boolean'" v-model="text"
      ><el-option label="true" value="true" /><el-option
        label="false"
        value="false"
    /></el-select>
    <el-input
      v-else-if="type !== 'Null'"
      v-model="text"
      :type="complex ? 'textarea' : 'text'"
      :rows="complex ? 5 : undefined"
      :placeholder="placeholder"
    />
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
    <pre v-else>{{ JSON.stringify(parsed, null, 2) }}</pre>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  DLT698_DATA_TYPES,
  type Dlt698Data,
  type Dlt698DataType,
} from "@/types/dlt698";
import { parseData } from "@/utils/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
const props = defineProps<{ modelValue: Dlt698Data; locked?: boolean }>();
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
  display: grid;
  gap: 10px;
  width: 100%;
}
small {
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
