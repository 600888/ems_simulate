<template>
  <div class="change-history">
    <div class="config-bar">
      <div class="config-item">
        <span class="label">{{ $t("changeHistory.title") }}</span>
        <el-switch
          v-model="trackingEnabled"
          :active-text="$t('changeHistory.on')"
          :inactive-text="$t('changeHistory.off')"
          @change="handleConfigChange"
        />
      </div>
      <div class="config-item">
        <span class="label">{{ $t("changeHistory.maxLen") }}</span>
        <el-input-number
          v-model="maxlen"
          :min="1"
          :max="100"
          size="small"
          @change="handleConfigChange"
        />
      </div>
      <div class="actions">
        <el-button
          type="primary"
          size="small"
          :icon="Refresh"
          @click="loadHistory"
          >{{ $t("common.refresh") }}</el-button
        >
        <el-button
          type="danger"
          size="small"
          :icon="Delete"
          @click="handleClear"
          >{{ $t("common.clear") }}</el-button
        >
      </div>
    </div>

    <el-table
      :data="history"
      style="width: 100%"
      height="300"
      border
      stripe
      class="history-table"
    >
      <el-table-column
        prop="time"
        :label="$t('changeHistory.time')"
        width="200"
        show-overflow-tooltip
        align="center"
        header-align="center"
      >
        <template #default="scope">
          <span class="timestamp">{{ scope.row.time }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="source_label"
        :label="$t('changeHistory.source')"
        width="120"
        align="center"
        header-align="center"
      >
        <template #default="scope">
          <el-tag :type="getSourceTagType(scope.row.source)" size="small">
            {{ scope.row.source_label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="client_info"
        :label="$t('changeHistory.sourceAddr')"
        width="160"
        align="center"
        header-align="center"
        show-overflow-tooltip
      >
        <template #default="scope">
          <span v-if="scope.row.client_info" class="client-info">
            {{ scope.row.client_info }}
          </span>
          <span v-else class="client-info empty">-</span>
        </template>
      </el-table-column>
      <el-table-column min-width="180" align="center" header-align="center">
        <template #header>
          {{ $t("changeHistory.valueChange") }}
          <el-tooltip
            effect="dark"
            :content="$t('changeHistory.tooltip')"
            placement="top"
          >
            <el-icon
              style="
                margin-left: 4px;
                font-size: 14px;
                vertical-align: middle;
                cursor: help;
              "
              ><QuestionFilled
            /></el-icon>
          </el-tooltip>
        </template>
        <template #default="scope">
          <div class="value-change">
            <span class="old-val">
              {{ scope.row.old_real_value }}
              <span
                v-if="scope.row.old_real_value !== scope.row.old_value"
                class="register-info"
                >({{ scope.row.old_value }})</span
              >
            </span>
            <el-icon class="arrow"><Right /></el-icon>
            <span class="new-val">
              {{ scope.row.new_real_value }}
              <span
                v-if="scope.row.new_real_value !== scope.row.new_value"
                class="register-info"
                >({{ scope.row.new_value }})</span
              >
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        prop="detail"
        :label="$t('changeHistory.detail')"
        min-width="120"
        show-overflow-tooltip
        align="center"
        header-align="center"
      />
    </el-table>

    <div class="history-footer">
      <span>{{
        $t("changeHistory.footer", { count: history.length, max: maxlen })
      }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Refresh,
  Delete,
  Right,
  QuestionFilled,
} from "@element-plus/icons-vue";

const { t } = useI18n();
import {
  getPointChangeHistory,
  setChangeTrackingConfig,
  clearPointChangeHistory,
  type ChangeRecord,
} from "@/api/pointApi";

interface Props {
  deviceName: string;
  pointCode: string;
  active?: boolean;
  slaveId?: number;
}

const props = withDefaults(defineProps<Props>(), {
  active: true,
  slaveId: undefined,
});

const history = ref<ChangeRecord[]>([]);
const trackingEnabled = ref(false);
const maxlen = ref(50);
const loading = ref(false);

const loadHistory = async () => {
  if (!props.pointCode) return;
  loading.value = true;
  try {
    const res = await getPointChangeHistory(
      props.deviceName,
      props.pointCode,
      props.slaveId,
    );
    if (res) {
      history.value = res.history;
      trackingEnabled.value = res.tracking_enabled;
      if (res.maxlen !== undefined) {
        maxlen.value = res.maxlen;
      }
    }
  } catch (error: any) {
    console.error("加载变更历史失败:", error);
    // error message is handled by global interceptor
  } finally {
    loading.value = false;
  }
};

const handleConfigChange = async () => {
  try {
    const success = await setChangeTrackingConfig(
      props.deviceName,
      props.pointCode,
      trackingEnabled.value,
      maxlen.value,
      props.slaveId,
    );
    if (success) {
      ElMessage.success(t("changeHistory.configUpdated"));
      loadHistory();
    }
  } catch (error: any) {
    console.error("更新配置失败:", error);
    // error message is handled by global interceptor
  }
};

const handleClear = () => {
  ElMessageBox.confirm(t("changeHistory.clearConfirm"), t("common.hint"), {
    confirmButtonText: t("common.confirm"),
    cancelButtonText: t("common.cancel"),
    type: "warning",
  })
    .then(async () => {
      try {
        const success = await clearPointChangeHistory(
          props.deviceName,
          props.pointCode,
          props.slaveId,
        );
        if (success) {
          ElMessage.success(t("changeHistory.clearSuccess"));
          loadHistory();
        }
      } catch (error: any) {
        console.error("清空失败:", error);
        // error message is handled by global interceptor
      }
    })
    .catch(() => {});
};

const getSourceTagType = (source: string) => {
  switch (source) {
    case "manual":
      return "primary";
    case "simulation":
      return "success";
    case "mapping":
      return "danger";
    case "protocol":
      return "warning";
    case "client_read":
      return "info";
    default:
      return "info";
  }
};

watch(
  () => props.active,
  (newVal) => {
    if (newVal) {
      loadHistory();
    }
  },
  { immediate: true },
);

// 切换设备或测点时，如果当前处于激活状态则自动加载
watch([() => props.deviceName, () => props.pointCode], () => {
  if (props.active) {
    loadHistory();
  }
});
</script>

<style scoped lang="scss">
.change-history {
  width: 95%;
  padding: 12px;
  background-color: var(--panel-bg);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.config-bar {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 16px;
  flex-wrap: wrap;

  .config-item {
    display: flex;
    align-items: center;
    gap: 8px;

    .label {
      font-size: 14px;
      color: #606266;
    }
  }

  .actions {
    margin-left: auto;
    display: flex;
    gap: 8px;
  }
}

.history-table {
  border-radius: 4px;
  overflow: hidden;

  .timestamp {
    font-size: 13px;
    color: #606266;
  }

  .value-change {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-weight: 500;

    .old-val {
      color: #f56c6c;
    }
    .new-val {
      color: #67c23a;
    }
    .arrow {
      color: #909399;
    }
  }

  .register-info {
    font-size: 11px;
    color: #909399;
    font-weight: normal;
    margin-left: 2px;
  }

  .client-info {
    font-size: 13px;
    color: #606266;
  }

  .client-info.empty {
    color: #c0c4cc;
  }
}

.history-footer {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  text-align: right;
}

:deep(.el-table__row) {
  height: 48px;
}
</style>
