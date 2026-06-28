<template>
  <div class="sidebar-status" :class="{ collapsed: isCollapse }">
    <div class="status-indicator" :class="statusClass">
      <span class="status-dot"></span>
      <span class="status-label" v-if="!isCollapse">{{ statusText }}</span>
    </div>
    <el-button
      v-if="!isHealthy && !isCollapse"
      class="restart-btn"
      size="small"
      :loading="restarting"
      @click="handleRestart"
    >
      {{ $t("sidebar.restartBackend") }}
    </el-button>
    <el-tooltip
      v-else-if="!isHealthy && isCollapse"
      :content="$t('sidebar.restartBackend')"
      placement="right"
    >
      <el-button
        class="restart-btn-collapsed"
        size="small"
        :loading="restarting"
        @click="handleRestart"
      >
        <el-icon><Refresh /></el-icon>
      </el-button>
    </el-tooltip>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { isTauri, checkBackendStatus, restartBackend } from "@/utils/tauri";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  isCollapse: boolean;
}>();

const { t } = useI18n();
const isHealthy = ref(false);
const restarting = ref(false);
const checking = ref(false);
let timer: ReturnType<typeof setInterval> | null = null;

const statusClass = computed(() => ({
  healthy: isHealthy.value,
  unhealthy: !isHealthy.value,
}));

const statusText = computed(() => {
  if (checking.value && !isHealthy.value) return t("sidebar.checking");
  return isHealthy.value ? t("sidebar.backendHealthy") : t("sidebar.backendDown");
});

const doHealthCheck = async () => {
  if (checking.value) return;
  checking.value = true;
  try {
    const ok = await checkBackendStatus();
    isHealthy.value = ok;
  } catch {
    isHealthy.value = false;
  } finally {
    checking.value = false;
  }
};

const handleRestart = async () => {
  if (restarting.value) return;
  restarting.value = true;
  isHealthy.value = false;
  try {
    if (!isTauri()) {
      ElMessage.warning(t("sidebar.restartUnavailable"));
      return;
    }

    await restartBackend();
    // Rust 已等待健康检查成功；前端再确认一次，确保状态栏与实际服务一致。
    const ok = await checkBackendStatus();
    isHealthy.value = ok;
    if (ok) {
      ElMessage.success(t("sidebar.restartSuccess"));
    } else {
      ElMessage.error(t("sidebar.restartFailed"));
    }
  } catch (error) {
    console.error("Restart backend failed:", error);
    isHealthy.value = false;
    const detail = error instanceof Error ? error.message : String(error || "");
    ElMessage.error(detail || t("sidebar.restartFailed"));
  } finally {
    restarting.value = false;
  }
};

onMounted(() => {
  doHealthCheck();
  timer = setInterval(doHealthCheck, 5000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style lang="scss" scoped>
.sidebar-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-top: 1px solid var(--sb-border, rgba(255, 255, 255, 0.08));
  background: var(--sb-bg-main);
  gap: 6px;
  min-height: 40px;

  &.collapsed {
    flex-direction: column;
    padding: 8px 4px;
    gap: 6px;
  }
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background-color 0.3s;

  .healthy & {
    background-color: #67c23a;
    box-shadow: 0 0 6px rgba(103, 194, 58, 0.5);
    animation: breathe 2s ease-in-out infinite;
  }

  .unhealthy & {
    background-color: #f56c6c;
    box-shadow: 0 0 6px rgba(245, 108, 108, 0.5);
    animation: pulse-red 1.5s ease-in-out infinite;
  }
}

@keyframes breathe {
  0% {
    box-shadow: 0 0 0 0 rgba(103, 194, 58, 0.7);
  }
  70% {
    box-shadow: 0 0 0 5px rgba(103, 194, 58, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(103, 194, 58, 0);
  }
}

@keyframes pulse-red {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.status-label {
  font-size: 12px;
  color: var(--text-secondary, rgba(255, 255, 255, 0.6));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.restart-btn {
  flex-shrink: 0;
  padding: 0 8px;
  height: 26px;
  font-size: 11px;
  border-color: #f56c6c;
  color: #f56c6c;

  &:hover {
    background-color: rgba(245, 108, 108, 0.1);
  }
}

.restart-btn-collapsed {
  padding: 4px;
  height: 26px;
  width: 26px;
  font-size: 12px;
  border-color: #f56c6c;
  color: #f56c6c;

  &:hover {
    background-color: rgba(245, 108, 108, 0.1);
  }
}
</style>
