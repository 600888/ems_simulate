<template>
  <el-tabs v-model="active" class="inner-tabs">
    <el-tab-pane :label="t('table.configControl')" name="configControl" lazy
      ><slot name="configControl"
    /></el-tab-pane>
    <el-tab-pane :label="t('table.propertyEdit')" name="propertyEdit" lazy
      ><slot name="propertyEdit"
    /></el-tab-pane>
    <el-tab-pane :label="t('table.pointMapping')" name="pointMapping" lazy
      ><slot name="pointMapping"
    /></el-tab-pane>
    <el-tab-pane name="simulation" :disabled="client" lazy>
      <template #label
        ><slot name="simulation-label"
          ><el-tooltip :content="t('device.clientNoSim')" :disabled="!client"
            ><span>{{ t("table.simulation") }}</span></el-tooltip
          ></slot
        ></template
      >
      <slot name="simulation" />
    </el-tab-pane>
    <el-tab-pane :label="t('table.changeHistory')" name="changeHistory" lazy
      ><slot name="changeHistory"
    /></el-tab-pane>
  </el-tabs>
</template>
<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
const props = defineProps<{ modelValue: string; client?: boolean }>();
const emit = defineEmits<{ (e: "update:modelValue", value: string): void }>();
const { t } = useI18n();
const active = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});
</script>
