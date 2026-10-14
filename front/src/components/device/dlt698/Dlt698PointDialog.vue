<template>
  <el-dialog
    v-model="visible"
    :title="point ? l('编辑测点', 'Edit point') : l('添加测点', 'Add point')"
    width="640px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-form label-width="120px" @submit.prevent="save">
      <el-form-item :label="l('测点编码', 'Point code')"
        ><el-input v-model="draft.code"
      /></el-form-item>
      <el-form-item :label="l('测点名称', 'Point name')"
        ><el-input v-model="draft.name"
      /></el-form-item>
      <el-form-item label="OI"
        ><el-input v-model="oi" maxlength="4" :disabled="draft.standard"
      /></el-form-item>
      <el-form-item :label="l('属性字节', 'Attribute byte')"
        ><el-input-number
          v-model="attribute"
          :min="0"
          :max="255"
          :disabled="draft.standard"
      /></el-form-item>
      <el-form-item :label="l('元素索引', 'Element index')"
        ><el-input-number
          v-model="index"
          :min="0"
          :max="255"
          :disabled="draft.standard"
        /><small>{{
          l(
            "0 = 完整属性；1 起为元素",
            "0 = whole attribute; elements start at 1",
          )
        }}</small></el-form-item
      >
      <el-form-item label="OAD"
        ><el-tag>{{ oad || "—" }}</el-tag></el-form-item
      >
      <el-form-item :label="l('分类', 'Category')"
        ><el-select v-model="draft.category"
          ><el-option
            v-for="category in categories"
            :key="category.value"
            :label="l(category.zh, category.en)"
            :value="category.value" /></el-select
      ></el-form-item>
      <el-form-item :label="l('单位 / 倍率', 'Unit / scaler')"
        ><el-input
          v-model="draft.unit"
          style="width: 150px"
          :disabled="draft.standard" /><el-input-number
          v-model="draft.scaler"
          :min="-12"
          :max="12"
          :disabled="draft.standard"
      /></el-form-item>
      <el-form-item :label="l('远端 SET', 'Remote SET')"
        ><el-switch
          v-model="draft.writable"
          :disabled="draft.standard || role === 'server'"
        /><small>{{
          l(
            role === "server"
              ? "当前服务端发布只读属性"
              : "实际写入权限由对端决定",
            role === "server"
              ? "The server publishes read-only attributes"
              : "The peer controls write permission",
          )
        }}</small></el-form-item
      >
      <el-form-item label="Data"
        ><Dlt698DataEditor
          v-model="draft.initial_value"
          :locked="draft.standard"
          @valid="dataValid = $event"
      /></el-form-item>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
    </el-form>
    <template #footer
      ><el-button @click="visible = false">{{ l("取消", "Cancel") }}</el-button
      ><el-button
        type="primary"
        :disabled="!dataValid || !oad || busy"
        :loading="busy"
        @click="save"
        >{{ l("保存", "Save") }}</el-button
      ></template
    >
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Dlt698Point } from "@/types/dlt698";
import { makeOad, validateData } from "@/utils/dlt698";
import Dlt698DataEditor from "./Dlt698DataEditor.vue";
import { useDlt698Text } from "@/composables/useDlt698Text";
const props = defineProps<{
  modelValue: boolean;
  point?: Dlt698Point;
  busy?: boolean;
  saveError?: string;
  role?: "client" | "server";
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "save", point: Dlt698Point): void;
}>();
const l = useDlt698Text();
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});
const blank = (): Dlt698Point => ({
  code: "",
  name: "",
  oad: "F0010200",
  category: "parameter",
  data_type: "UInt16",
  unit: "",
  scaler: 0,
  standard: false,
  writable: false,
  initial_value: { type: "UInt16", value: "0" },
});
const draft = ref(blank()),
  oi = ref("F001"),
  attribute = ref(2),
  index = ref(0),
  dataValid = ref(true),
  localError = ref("");
const error = computed(() => props.saveError || localError.value);
const categories = [
  { value: "energy", zh: "电能量", en: "Energy" },
  { value: "demand", zh: "最大需量", en: "Demand" },
  { value: "variable", zh: "变量", en: "Variables" },
  { value: "harmonic", zh: "谐波", en: "Harmonics" },
  { value: "parameter", zh: "参数", en: "Parameters" },
];
const oad = computed(() => {
  try {
    return makeOad(oi.value, attribute.value, index.value);
  } catch {
    return "";
  }
});
watch(
  () => props.modelValue,
  (opened) => {
    if (opened) {
      draft.value = JSON.parse(JSON.stringify(props.point || blank()));
      oi.value = draft.value.oad.slice(0, 4);
      attribute.value = parseInt(draft.value.oad.slice(4, 6), 16);
      index.value = parseInt(draft.value.oad.slice(6), 16);
      localError.value = "";
    }
  },
);
function save() {
  if (props.busy || !dataValid.value || !oad.value) return;
  try {
    validateData(draft.value.initial_value);
  } catch (e) {
    localError.value = (e as Error).message;
    return;
  }
  if (!draft.value.code.trim() || !draft.value.name.trim()) {
    localError.value = l(
      "请填写测点编码和名称",
      "Point code and name are required",
    );
    return;
  }
  emit("save", {
    ...draft.value,
    code: draft.value.code.trim(),
    name: draft.value.name.trim(),
    oad: oad.value,
    data_type: draft.value.initial_value.type,
  });
}
</script>
<style scoped>
small {
  margin-left: 12px;
  color: var(--text-secondary);
}
:deep(.el-dialog) {
  max-width: calc(100vw - 32px);
}
</style>
