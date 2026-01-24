<template>
  <div class="device-form-basic">
    <el-divider content-position="left">基本信息</el-divider>
    
    <el-form-item label="设备编码" prop="code">
      <el-input v-model="modelValue.code" placeholder="请输入设备编码，如 PCS1" />
    </el-form-item>
    
    <el-form-item label="设备名称" prop="name">
      <el-input v-model="modelValue.name" placeholder="请输入设备名称" />
    </el-form-item>
    
    <el-form-item label="所属设备组">
      <el-tree-select
        v-model="modelValue.group_id"
        :data="groupOptions"
        :props="{ label: 'name', value: 'id', children: 'children' }"
        placeholder="选择设备组（可选，不选则为未分组）"
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
