<template>
  <div class="ungrouped-section" v-if="ungroupedDevices.length > 0">
    <div class="ungrouped-header" @click="$emit('toggle')">
      <el-icon><ArrowRight :class="{ 'is-expanded': expanded }" /></el-icon>
      <span>未分组设备 ({{ ungroupedDevices.length }})</span>
    </div>
    <div v-show="expanded" class="ungrouped-list">
      <div
        v-for="device in ungroupedDevices"
        :key="device.id"
        class="ungrouped-item"
        :class="{ 'is-active': currentDeviceName === device.name }"
        @click="$emit('device-click', device)"
      >
        <el-icon><Cpu /></el-icon>
        <span>{{ device.name }}</span>
        <div class="node-actions" v-if="!isCollapse" @click.stop>
          <el-button link size="small" :icon="Edit" @click="$emit('edit-device', device.name)" />
          <el-button link size="small" :icon="Delete" @click="$emit('delete-device', device.name)" />
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ArrowRight, Cpu, Edit, Delete } from "@element-plus/icons-vue";

defineProps<{
  ungroupedDevices: any[];
  expanded: boolean;
  currentDeviceName: string;
  isCollapse: boolean;
}>();

defineEmits<{
  (e: 'toggle'): void;
  (e: 'device-click', device: any): void;
  (e: 'edit-device', name: string): void;
  (e: 'delete-device', name: string): void;
}>();
</script>

<style lang="scss" scoped>
.ungrouped-section {
  margin: 20px 12px 10px;
  border-top: 1px solid var(--sb-border);
  padding-top: 20px;
}

.ungrouped-header {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
  border-radius: 8px;
  transition: all 0.2s;
}

.ungrouped-header:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.ungrouped-header .el-icon {
  margin-right: 10px;
  transition: transform 0.2s;
}

.ungrouped-header .el-icon.is-expanded {
  transform: rotate(90deg);
}

.ungrouped-list {
  padding: 8px 0 0 10px;
}

.ungrouped-item {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  border-radius: 10px;
  margin-bottom: 4px;
  transition: all 0.2s;
  color: var(--text-secondary);
}

.ungrouped-item:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.ungrouped-item.is-active {
  background: var(--item-active-bg);
  color: var(--color-primary);
  font-weight: 600;
  box-shadow: inset 2px 0 0 var(--color-primary);
}

.ungrouped-item .el-icon {
  margin-right: 12px;
  font-size: 18px;
  color: var(--text-secondary);
}

.ungrouped-item span {
  flex: 1;
  font-size: 13.5px;
}

.node-actions {
  display: flex;
  gap: 6px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.ungrouped-item:hover .node-actions {
  opacity: 1;
}

.node-actions .el-button {
  padding: 5px;
  color: var(--text-secondary);
  border-radius: 6px;
}

.node-actions .el-button:hover {
  background-color: var(--item-active-bg);
  color: var(--color-primary);
}
</style>
