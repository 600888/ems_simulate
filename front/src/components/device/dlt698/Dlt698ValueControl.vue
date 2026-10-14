<template>
  <div class="register">
    <div class="simple-title">
      {{ l("测点值设置", "Point value settings") }}<el-divider />
    </div>
    <Dlt698DataTree :data="current" />
    <el-form label-width="auto" @submit.prevent="save">
      <el-form-item :label="l('设置值', 'New value')">
        <Dlt698DataEditor v-model="draft" locked @valid="valid = $event" />
      </el-form-item>
      <el-button
        type="primary"
        :disabled="disabled || busy || !valid"
        :loading="busy"
        @click="save"
      >
        {{ role === "server" ? l("设置", "Set") : "SET" }}
      </el-button>
      <el-button :disabled="busy" @click="reset">{{
        l("加载当前值", "Load current value")
      }}</el-button>
    </el-form>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Dlt698Data, Dlt698Point, Dlt698Role } from "@/types/dlt698";
import { useDlt698Text } from "@/composables/useDlt698Text";
import Dlt698DataEditor from "./Dlt698DataEditor.vue";
import Dlt698DataTree from "./Dlt698DataTree.vue";
const props = defineProps<{
  point: Dlt698Point;
  role: Dlt698Role;
  disabled?: boolean;
  busy?: boolean;
}>();
const emit = defineEmits<{ (e: "save", value: Dlt698Data): void }>();
const l = useDlt698Text();
const current = computed(
  () => props.point.last_good || props.point.initial_value,
);
const draft = ref<Dlt698Data>(JSON.parse(JSON.stringify(current.value)));
const valid = ref(true);
function reset() {
  draft.value = JSON.parse(JSON.stringify(current.value));
}
function save() {
  if (!props.disabled && !props.busy && valid.value) emit("save", draft.value);
}
watch(() => props.point.code, reset);
</script>
<style scoped>
.register {
  width: 380px;
  max-width: 100%;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--panel-bg);
}
.simple-title {
  color: var(--el-color-primary);
  font-size: 14px;
  font-weight: 600;
}
.simple-title .el-divider {
  margin: 12px 0;
}
.el-form {
  margin-top: 16px;
}
</style>
