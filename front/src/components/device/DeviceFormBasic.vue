<template>
  <div class="device-form-basic">
    <el-divider content-position="left">{{ $t('device.basicInfo') }}</el-divider>
    
    <el-form-item :label="$t('device.code')" prop="code">
      <el-input v-model="modelValue.code" :placeholder="$t('device.codePlaceholder')" />
    </el-form-item>
    
    <el-form-item :label="$t('device.name')" prop="name">
      <el-input v-model="modelValue.name" :placeholder="$t('device.namePlaceholder')" />
    </el-form-item>
    
    <el-form-item :label="$t('device.group')">
      <el-tree-select
        v-model="modelValue.group_id"
        :data="groupOptions"
        :props="{ label: 'name', value: 'id', children: 'children' }"
        :placeholder="$t('device.groupPlaceholder')"
        check-strictly
        clearable
        style="width: 100%"
      />
    </el-form-item>
  </div>
</template>

<script lang="ts" setup>
import type { ChannelCreateRequest } from '@/types/channel';
import type { DeviceGroupInfo } from '@/api/deviceGroupApi';

defineProps<{
  modelValue: ChannelCreateRequest;
  groupOptions: DeviceGroupInfo[];
}>();
</script>

<style lang="scss" scoped>
.device-form-basic {
  margin-bottom: 20px;
}
</style>
