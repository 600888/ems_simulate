<template>
  <div 
    class="data-card" 
    :class="[
      `status-${status === null ? 'info' : status ? 'success' : 'danger'}`,
      { 'has-status': status !== null }
    ]"
  >
    <div class="card-inner">
      <div class="icon-section">
        <el-icon class="feature-icon">
          <component :is="getIconByLabel(label)" />
        </el-icon>
        <span v-if="status === true" class="status-indicator"></span>
      </div>
      
      <div class="content-section">
        <div class="label-row">
          <span class="card-label">{{ label }}</span>
        </div>
        <div class="value-row">
          <span class="card-value">{{ name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { 
  Monitor, Connection, Cpu, Link, 
  Setting, Operation, Connection as PortIcon,
  VideoPlay
} from "@element-plus/icons-vue";

defineProps({
  label: { type: String, required: true },
  name: { type: String, required: true },
  status: { type: Boolean, default: null },
});

const getIconByLabel = (label: string) => {
  const l = label.toLowerCase();
  if (l.includes('地址')) return Connection;
  if (l.includes('端口')) return PortIcon;
  if (l.includes('串口')) return Link;
  if (l.includes('波特率')) return Operation;
  if (l.includes('通讯')) return Cpu;
  if (l.includes('设备状态')) return Monitor;
  if (l.includes('模拟状态')) return VideoPlay;
  return Setting;
};
</script>

<style lang="scss" scoped>
.data-card {
  position: relative;
  min-width: 190px;
  height: 54px;
  background: var(--panel-bg);
  border-radius: 12px;
  border: 1px solid var(--sidebar-border);
  overflow: hidden;
  transition: all 0.3s ease;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
    border-color: var(--color-primary);
    
    .feature-icon { color: var(--color-primary); }
  }
}

.card-inner {
  height: 100%;
  display: flex;
  align-items: center;
  padding: 0 18px;
}

.icon-section {
  position: relative;
  width: 34px;
  height: 34px;
  background: var(--item-hover-bg);
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  flex-shrink: 0;

  .feature-icon {
    font-size: 19px;
    color: var(--text-secondary);
    transition: all 0.3s;
  }
}

.content-section {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  flex: 1;
  /* 解决用户反馈的数值太靠近底部的视觉问题：微调整体中心偏移 */
  margin-top: -2px;
}

.label-row {
  margin-bottom: 2px;
  line-height: 1;
}

.card-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
  letter-spacing: 0.3px;
  opacity: 0.7;
}

.value-row {
  line-height: 1.1;
}

.card-value {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-indicator {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  border: 1.5px solid var(--panel-bg);
}

.status-success {
  border-left: 4px solid #10b981;
  .card-value { color: #10b981; }
}

.status-danger {
  border-left: 4px solid #ef4444;
  .card-value { color: #ef4444; }
}

.status-info {
  border-left: 4px solid var(--color-primary);
}

/* 深色模式修正 */
body.theme-dark {
  .icon-section { background: rgba(255, 255, 255, 0.05); }
  .status-indicator { border-color: #1e293b; }
}
</style>
