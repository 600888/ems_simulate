<template>
  <div class="action-buttons-container">
    <div class="action-buttons" v-if="!isCollapse">
      <el-button-group>
        <el-button type="primary" @click="$emit('add-device')" :icon="Plus">
          添加设备
        </el-button>
        <el-button type="success" @click="$emit('add-group')" :icon="FolderAdd">
          添加分组
        </el-button>
      </el-button-group>
    </div>
    <div class="add-device-btn-collapse" v-else>
      <el-tooltip content="添加设备" placement="right">
        <el-button type="primary" circle @click="$emit('add-device')" :icon="Plus" />
      </el-tooltip>
      <el-tooltip content="添加分组" placement="right">
        <el-button type="success" circle @click="$emit('add-group')" :icon="FolderAdd" />
      </el-tooltip>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { Plus, FolderAdd } from "@element-plus/icons-vue";

defineProps<{
  isCollapse: boolean;
}>();

defineEmits<{
  (e: 'add-device'): void;
  (e: 'add-group'): void;
}>();
</script>

<style lang="scss" scoped>
.action-buttons {
  padding: 5px 20px 25px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-buttons .el-button-group {
  display: flex;
  width: 100%;
  gap: 10px;
}

.action-buttons .el-button {
  flex: 1;
  border-radius: 10px !important;
  border: none;
  font-weight: 600;
  height: 42px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  margin: 0 !important;
  color: var(--sb-btn-text);
  overflow: hidden;
}

.action-buttons .el-button--primary {
  background: var(--sb-btn-primary-bg);
  border: 1px solid rgba(59, 130, 246, 0.1);
}

.action-buttons .el-button--primary:hover {
  background: var(--sb-btn-primary-hover);
  transform: translateY(-2px);
  color: #fff;
}

.action-buttons .el-button--success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.1);
}

.action-buttons .el-button--success:hover {
  background: #10b981;
  transform: translateY(-2px);
  color: #fff;
}

.add-device-btn-collapse {
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  width: 100%;
  
  .el-button {
    margin: 0 !important;
  }
}
</style>
