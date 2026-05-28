<template>
  <el-dialog
    v-model="visible"
    :title="$t('messageView.title')"
    width="1100px"
    :before-close="handleClose"
    destroy-on-close
    class="message-dialog"
  >
    <div class="toolbar">
      <div class="left-actions">
        <el-button
          :type="autoRefresh ? 'warning' : 'success'"
          @click="toggleAutoRefresh"
          :icon="autoRefresh ? VideoPause : CaretRight"
        >
          {{ autoRefresh ? $t('messageView.pauseRefresh') : $t('messageView.startRefresh') }}
        </el-button>
        <el-button type="danger" @click="handleClear" :icon="Delete">
          {{ $t('messageView.clearMessages') }}
        </el-button>
        <el-select v-model="searchMode" class="search-mode-select">
          <el-option :label="$t('messageView.byDescription')" value="description" />
          <el-option :label="$t('messageView.byData')" value="hex_data" />
        </el-select>
        <el-input
          v-model="searchKeyword"
          :placeholder="searchMode === 'description' ? $t('messageView.searchDesc') : $t('messageView.searchData')"
          :prefix-icon="Search"
          clearable
          class="search-input"
        />
      </div>
      <div class="right-info">
        <span class="msg-count">
          {{ $t('messageView.messageCount', { filtered: filteredMessages.length, total: messages.length }) }}
        </span>
        <el-tag v-if="avgStats && avgStats.pair_count > 0" type="warning" size="small">
          {{ $t('messageView.avgLatency', { ms: avgStats.avg_latency_ms, pairs: avgStats.pair_count }) }}
        </el-tag>
        <el-tag v-if="autoRefresh" type="success" size="small">{{ $t('messageView.autoRefreshing') }}</el-tag>
        <el-tag v-else type="info" size="small">{{ $t('messageView.paused') }}</el-tag>
      </div>
    </div>

    <el-table
      :data="filteredMessages"
      stripe
      height="400"
      class="message-table"
      :row-class-name="getRowClass"
    >
      <el-table-column prop="formatted_time" :label="$t('messageView.time')" width="120" header-align="center" />
      <el-table-column prop="direction" :label="$t('messageView.direction')" width="80" align="center" header-align="center">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'TX' ? 'primary' : 'success'" size="small">
            {{ row.direction === 'TX' ? $t('messageView.send') : $t('messageView.receive') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="length" :label="$t('messageView.length')" width="70" align="center" header-align="center">
        <template #default="{ row }">
          <span class="length-badge">{{ row.length }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="hex_data" :label="$t('messageView.dataHex')" min-width="350" align="center" header-align="center">
        <template #default="{ row }">
          <span class="hex-data" :title="row.hex_data">{{ row.hex_data }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" :label="$t('messageView.parsed')" min-width="280" header-align="center">
        <template #default="{ row }">
          <span class="desc-text" :title="row.description">{{ row.description }}</span>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="handleClose">{{ $t('common.close') }}</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, watch, onUnmounted, computed } from 'vue';
import { useI18n } from 'vue-i18n'
import { getMessages, clearMessages, getAvgTime, type MessageRecord, type AvgTimeStats } from '@/api/deviceApi';
import { CaretRight, VideoPause, Delete, Search } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const { t } = useI18n()
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const messages = ref<MessageRecord[]>([]);
const avgStats = ref<AvgTimeStats | null>(null);
const autoRefresh = ref(true);
const searchKeyword = ref('');
const searchMode = ref<'description' | 'hex_data'>('description');

const filteredMessages = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase();
  if (!keyword) return messages.value;
  return messages.value.filter(msg => {
    const field = searchMode.value === 'description' ? msg.description : msg.hex_data;
    return field?.toLowerCase().includes(keyword);
  });
});
let refreshTimer: ReturnType<typeof setInterval> | null = null;

const fetchMessages = async () => {
  if (!props.deviceName) return;
  try {
    messages.value = await getMessages(props.deviceName, 200);
    avgStats.value = await getAvgTime(props.deviceName);
  } catch (error) {
    console.error('Failed to fetch messages:', error);
  }
};

const startAutoRefresh = () => {
  if (refreshTimer) return;
  refreshTimer = setInterval(fetchMessages, 1000);
};

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
};

const toggleAutoRefresh = () => {
  autoRefresh.value = !autoRefresh.value;
  if (autoRefresh.value) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
};

const handleClear = async () => {
  try {
    await ElMessageBox.confirm(t('messageView.clearConfirm'), t('common.hint'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning',
    });
    const success = await clearMessages(props.deviceName);
    if (success) {
      messages.value = [];
      avgStats.value = null;
      ElMessage.success(t('messageView.cleared'));
    } else {
      ElMessage.error(t('messageView.clearFailed'));
    }
  } catch {
    // 用户取消
  }
};

const handleClose = () => {
  stopAutoRefresh();
  visible.value = false;
};

const getRowClass = ({ row }: { row: MessageRecord }) => {
  return row.direction === 'TX' ? 'tx-row' : 'rx-row';
};

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    fetchMessages();
    if (autoRefresh.value) {
      startAutoRefresh();
    }
  } else {
    stopAutoRefresh();
  }
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style lang="scss" scoped>
.message-dialog {
  :deep(.el-dialog__body) {
    padding: 16px 20px;
  }
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 10px 12px;
  background: var(--panel-bg, #f5f5f5);
  border-radius: 8px;

  .left-actions {
    display: flex;
    gap: 8px;
    align-items: center;

    .search-mode-select {
      width: 100px;
    }

    .search-input {
      width: 200px;
    }
  }

  .right-info {
    display: flex;
    align-items: center;
    gap: 12px;

    .msg-count {
      color: var(--text-secondary, #666);
      font-size: 14px;
    }
  }
}

.message-table {
  border-radius: 8px;
  overflow: hidden;

  :deep(.tx-row) {
    background-color: rgba(59, 130, 246, 0.05);
  }

  :deep(.rx-row) {
    background-color: rgba(16, 185, 129, 0.05);
  }

  .hex-data {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    word-break: break-word;
    overflow-wrap: break-word;
    white-space: normal;
    color: var(--text-primary, #333);
  }

  .length-badge {
    display: inline-block;
    min-width: 32px;
    padding: 2px 6px;
    background: var(--panel-bg, #f0f0f0);
    border-radius: 4px;
    text-align: center;
    font-size: 12px;
    font-weight: 500;
  }

  .desc-text {
    font-size: 13px;
    color: var(--text-secondary, #555);
    word-break: break-all;
  }
}
</style>
