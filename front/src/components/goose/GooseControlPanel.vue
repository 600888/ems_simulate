<template>
  <el-empty v-if="!block" description="请选择一个 GOOSE 控制块" />
  <div v-else class="control-panel">
    <el-descriptions :column="2" border size="small" label-width="auto">
      <el-descriptions-item label="名称 (Name)">{{ block.display_name }}</el-descriptions-item>
      <el-descriptions-item label="状态 (State)">
        <el-tag :type="stateTag">{{ stateLabel }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="GoCBRef" :span="2">{{ block.go_cb_ref }}</el-descriptions-item>
      <el-descriptions-item label="GOOSE标识符 (GoID)">{{ block.go_id || '-' }}</el-descriptions-item>
      <el-descriptions-item label="应用标识 (APPID)">{{ formatAppId(block.app_id) }}</el-descriptions-item>
      <el-descriptions-item label="数据集 (DataSet)" :span="2">{{ block.data_set_ref || '-' }}</el-descriptions-item>
      <el-descriptions-item label="IED / LD / LN">{{ block.ied_name }} / {{ block.ld_inst }} / {{ block.ln_name }}</el-descriptions-item>
      <el-descriptions-item label="状态号/顺序号 (stNum/sqNum)">{{ block.st_num }} / {{ block.sq_num }}</el-descriptions-item>
      <el-descriptions-item label="配置版本号 (ConfRev) 预期/接收">
        <span :class="{ mismatch: block.subscription?.config_mismatch }">{{ block.conf_rev }} / {{ block.subscription?.received_conf_rev || '-' }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="网络接口 (Interface)">{{ interfaceLabel }}</el-descriptions-item>
      <el-descriptions-item label="最后更新 (Last update)">{{ formatGooseTime(block.last_update) }}</el-descriptions-item>
      <el-descriptions-item label="报文数 (Messages)">{{ block.message_count || 0 }}</el-descriptions-item>
      <el-descriptions-item label="存活时间 (TTL)">{{ block.subscription?.time_allowed_to_live || 0 }} ms</el-descriptions-item>
    </el-descriptions>

    <section class="config-section">
      <div class="section-title">订阅配置</div>
      <el-form label-width="200px" class="config-form">
        <el-form-item label="订阅使能 (GoEna)">
          <el-switch v-model="form.enabled" active-text="已启用" inactive-text="已禁用" />
        </el-form-item>
        <el-form-item label="网络接口 (Interface)">
          <el-select v-model="form.interface" style="width: 100%" placeholder="请选择网卡">
            <el-option v-for="item in interfaces" :key="item.id" :value="item.id" class="network-option-item">
              <div class="network-option">
                <el-icon class="network-option-icon"><Monitor /></el-icon>
                <div class="network-option-body">
                  <span class="network-option-name">{{ item.display_name }}</span>
                  <span class="network-option-mac">MAC: {{ (item.mac || "-").replace(/-/g, ":") }}</span>
                </div>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="应用标识过滤 (APPID Filter)">
          <el-input-number v-model="form.app_id" :min="0" :max="65535" controls-position="right" />
        </el-form-item>
        <el-form-item label="数据集 (DataSet)">
          <el-input v-model="form.data_set_ref" />
        </el-form-item>
        <el-form-item label="配置版本号 (ConfRev)">
          <el-input-number v-model="form.conf_rev" :min="0" controls-position="right" />
        </el-form-item>
        <el-form-item label="描述 (Description)">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
    </section>
    <div class="actions">
      <el-button type="primary" :loading="loading" @click="apply">应用配置</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import { Monitor } from '@element-plus/icons-vue';
import type { NetworkInterfaceInfo } from '@/api/gooseApi';
import type { GooseBlockItem } from './gooseWorkbench';
import { formatGooseTime } from './gooseWorkbench';

const props = defineProps<{ block: GooseBlockItem | null; loading?: boolean; interfaces: NetworkInterfaceInfo[] }>();
const emit = defineEmits<{ (e: 'apply', value: typeof form): void }>();
const form = reactive({ enabled: false, interface: '', app_id: null as number | null, data_set_ref: '', conf_rev: 0, description: '' });
watch(() => props.block?.key, sync, { immediate: true });
function sync() {
  Object.assign(form, {
    enabled: !!props.block?.enabled,
    app_id: props.block?.app_id ?? null,
    interface: props.block?.interface || '',
    data_set_ref: props.block?.data_set_ref || '',
    conf_rev: props.block?.conf_rev || 0,
    description: props.block?.subscription?.description || '',
  });
}
const stateLabel = computed(() => !props.block?.enabled ? '已禁用' : ({ connected: '已连接', lost: '超时', error: '错误', init: '等待中' }[props.block.state] || props.block.state));
const stateTag = computed(() => !props.block?.enabled ? 'info' : props.block.state === 'connected' ? 'success' : props.block.state === 'init' ? 'primary' : 'danger');
const interfaceLabel = computed(() => {
  const item = props.interfaces.find((candidate) => candidate.id === props.block?.interface);
  return item ? `${item.display_name} (${item.mac || '-'})` : props.block?.interface || '-';
});
function formatAppId(value: number | null) { return value == null ? '-' : `0x${value.toString(16).toUpperCase().padStart(4, '0')}`; }
function apply() { emit('apply', { ...form }); }
</script>

<style scoped lang="scss">
.control-panel { display: flex; flex-direction: column; gap: 14px; }
.config-section { padding: 14px 16px; border: 1px solid #d8dde5; background: #fbfcfe; }
.section-title { margin-bottom: 14px; color: #263241; font-weight: 700; }
.config-form { display: grid; grid-template-columns: repeat(2, minmax(280px, 1fr)); gap: 0 18px; }
.config-form :deep(.el-form-item) { margin-bottom: 14px; }
.config-form :deep(.el-input), .config-form :deep(.el-input-number) { width: 100%; }
.actions { display: flex; justify-content: flex-end; }
.mismatch { color: #d98200; font-weight: 700; }
@media (max-width: 1000px) { .config-form { grid-template-columns: 1fr; } }
</style>

<style lang="scss">
.el-select-dropdown__item.network-option-item {
  height: auto;
  min-height: auto;
  padding: 4px 12px;
}
.el-select-dropdown__item.network-option-item:first-child { padding-top: 0; }
.el-select-dropdown__item.network-option-item:last-child { padding-bottom: 0; }
.network-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  .network-option-icon { font-size: 16px; color: #409eff; flex-shrink: 0; }
  .network-option-body { display: flex; flex-direction: column; min-width: 0; }
  .network-option-name { font-size: 13px; color: #303133; line-height: 1.3; }
  .network-option-mac { font-family: "Cascadia Code","Fira Code","JetBrains Mono",Consolas,monospace; font-size: 11px; color: #909399; line-height: 1.2; }
}
</style>
