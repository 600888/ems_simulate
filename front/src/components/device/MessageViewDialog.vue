<template>
  <el-dialog
    v-model="visible"
    title="实时报文查看"
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
          {{ autoRefresh ? '暂停刷新' : '开始刷新' }}
        </el-button>
        <el-button type="danger" @click="handleClear" :icon="Delete">
          清空报文
        </el-button>
      </div>
      <div class="right-info">
        <span class="msg-count">共 {{ messages.length }} 条报文</span>
        <el-tag v-if="autoRefresh" type="success" size="small">自动刷新中</el-tag>
        <el-tag v-else type="info" size="small">已暂停</el-tag>
      </div>
    </div>

    <el-table
      :data="messages"
      stripe
      height="400"
      class="message-table"
      :row-class-name="getRowClass"
    >
      <el-table-column prop="formatted_time" label="时间" width="120" header-align="center" />
      <el-table-column prop="direction" label="方向" width="80" align="center" header-align="center">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'TX' ? 'primary' : 'success'" size="small">
            {{ row.direction === 'TX' ? '发送' : '接收' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="length" label="长度" width="70" align="center" header-align="center">
        <template #default="{ row }">
          <span class="length-badge">{{ row.length }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="hex_data" label="数据 (HEX)" min-width="350" align="center" header-align="center">
        <template #default="{ row }">
          <span class="hex-data" :title="row.hex_data">{{ row.hex_data }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="解析" min-width="280" header-align="center">
        <template #default="{ row }">
          <span class="desc-text" :title="row.description">{{ row.description }}</span>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, watch, onUnmounted, computed } from 'vue';
import { getMessages, clearMessages, type MessageRecord } from '@/api/deviceApi';
import { CaretRight, VideoPause, Delete } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const messages = ref<MessageRecord[]>([]);
const autoRefresh = ref(true);
let refreshTimer: ReturnType<typeof setInterval> | null = null;

const fetchMessages = async () => {
  if (!props.deviceName) return;
  try {
    messages.value = await getMessages(props.deviceName, 200);
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
    await ElMessageBox.confirm('确定要清空所有报文记录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    });
    const success = await clearMessages(props.deviceName);
    if (success) {
      messages.value = [];
      ElMessage.success('报文已清空');
    } else {
      ElMessage.error('清空失败');
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
    word-break: break-all;
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
