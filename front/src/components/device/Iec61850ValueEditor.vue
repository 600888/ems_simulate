<template>
  <el-select
    v-if="definition"
    :model-value="modelValue === '' ? undefined : modelValue"
    filterable
    clearable
    :placeholder="$t('writeDialog.selectEnum')"
    :disabled="disabled"
    style="width: 100%"
    @update:model-value="$emit('update:modelValue', $event ?? '')"
    @clear="$emit('update:modelValue', '')"
  >
    <el-option
      v-for="item in definition.items"
      :key="item.ord"
      :label="enumOptionLabel(item)"
      :value="item.ord"
    />
  </el-select>
  <el-input
    v-else
    :model-value="modelValue"
    :disabled="disabled"
    :placeholder="$t('writeDialog.inputPlaceholder')"
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>

<script setup lang="ts">
import type { IEC61850EnumDefinition } from "@/api/channelApi";
import { enumOptionLabel } from "@/utils/iec61850Enum";

defineProps<{
  modelValue: string | number;
  definition?: IEC61850EnumDefinition;
  disabled?: boolean;
}>();
defineEmits<{ "update:modelValue": [value: string | number] }>();
</script>
