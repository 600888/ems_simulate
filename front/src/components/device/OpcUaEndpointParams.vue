<template>
  <el-divider content-position="left">{{
    $t("opcua.deviceSpecificParams")
  }}</el-divider>
  <el-form-item
    :label="$t('opcua.deviceEndpointPath')"
    label-width="180px"
    required
  >
    <el-input
      v-model="modelValue.endpoint_path"
      :disabled="disabled"
      maxlength="255"
      placeholder="/ems/"
    />
    <div class="field-tip">{{ $t("opcua.deviceEndpointPathHint") }}</div>
  </el-form-item>
  <el-form-item
    v-if="connType === 2"
    :label="$t('opcua.namespaceUri')"
    label-width="180px"
  >
    <el-input
      v-model="modelValue.namespace_uri"
      :disabled="disabled"
      maxlength="255"
      :placeholder="$t('opcua.deviceNamespaceDefault')"
    />
  </el-form-item>
</template>

<script setup lang="ts">
import type { OpcUaDeviceConfig } from "@/types/channel";
defineProps<{
  modelValue: OpcUaDeviceConfig;
  connType: number;
  disabled?: boolean;
}>();
</script>

<style scoped>
.field-tip {
  width: 100%;
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
