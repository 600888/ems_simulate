<template>
  <el-empty v-if="!block?.publisher" description="请选择一个发布控制块" />
  <div v-else class="control-panel">
    <el-descriptions :column="2" border size="small" label-width="150px">
      <el-descriptions-item label="Name">{{ block.display_name }}</el-descriptions-item>
      <el-descriptions-item label="Type"
        ><el-tag type="primary">Publisher</el-tag></el-descriptions-item
      >
      <el-descriptions-item label="GoCBRef" :span="2">{{
        block.go_cb_ref
      }}</el-descriptions-item>
      <el-descriptions-item label="GoID">{{ block.go_id || "-" }}</el-descriptions-item>
      <el-descriptions-item label="APPID">{{
        formatAppId(block.app_id)
      }}</el-descriptions-item>
      <el-descriptions-item label="DataSet" :span="2">{{
        block.data_set_ref || "-"
      }}</el-descriptions-item>
      <el-descriptions-item label="IED / LD / LN"
        >{{ block.ied_name }} / {{ block.ld_inst }} /
        {{ block.ln_name }}</el-descriptions-item
      >
      <el-descriptions-item label="stNum / sqNum"
        >{{ block.st_num }} / {{ block.sq_num }}</el-descriptions-item
      >
      <el-descriptions-item label="Interface">{{ block.interface }}</el-descriptions-item>
      <el-descriptions-item label="Entries">{{
        block.data_values.length
      }}</el-descriptions-item>
    </el-descriptions>

    <section class="config-section">
      <div class="section-title">发布配置</div>
      <el-form label-width="135px" class="config-form">
        <el-form-item label="发布使能"
          ><el-switch
            v-model="form.enabled"
            active-text="Enabled"
            inactive-text="Disabled"
        /></el-form-item>
        <el-form-item label="Interface">
          <el-select
            v-model="form.interface"
            style="width: 100%"
            placeholder="请选择网卡"
          >
            <el-option
              v-for="item in interfaces"
              :key="item.id"
              :value="item.id"
              class="network-option-item"
            >
              <div class="network-option">
                <el-icon class="network-option-icon"><Monitor /></el-icon>
                <div class="network-option-body">
                  <span class="network-option-name">{{ item.display_name }}</span>
                  <span class="network-option-mac"
                    >MAC: {{ (item.mac || "-").replace(/-/g, ":") }}</span
                  >
                </div>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="GoID"><el-input v-model="form.go_id" /></el-form-item>
        <el-form-item label="APPID"
          ><el-input-number
            v-model="form.app_id"
            :min="0"
            :max="65535"
            controls-position="right"
        /></el-form-item>
        <el-form-item label="DataSet"
          ><el-input v-model="form.data_set_ref"
        /></el-form-item>
        <el-form-item label="ConfRev"
          ><el-input-number v-model="form.conf_rev" :min="1" controls-position="right"
        /></el-form-item>
        <el-form-item label="TTL"
          ><el-input-number v-model="form.time_allowed_to_live" :min="100" :max="60000"
        /></el-form-item>
        <el-form-item label="VLAN ID"
          ><el-input-number v-model="form.vlan_id" :min="0" :max="4095"
        /></el-form-item>
        <el-form-item label="VLAN Priority"
          ><el-input-number v-model="form.vlan_prio" :min="0" :max="7"
        /></el-form-item>
        <el-form-item label="Simulation"
          ><el-switch v-model="form.simulation"
        /></el-form-item>
      </el-form>
    </section>
    <div class="actions">
      <el-button type="primary" :loading="loading" @click="emit('apply', { ...form })"
        >应用配置</el-button
      >
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from "vue";
import { Monitor } from "@element-plus/icons-vue";
import type { NetworkInterfaceInfo } from "@/api/gooseApi";
import type { GooseBlockItem } from "./gooseWorkbench";
const props = defineProps<{
  block: GooseBlockItem | null;
  loading?: boolean;
  interfaces: NetworkInterfaceInfo[];
}>();
interface PublisherForm {
  enabled: boolean;
  interface: string;
  go_id: string;
  data_set_ref: string;
  app_id: number;
  conf_rev: number;
  time_allowed_to_live: number;
  vlan_id: number;
  vlan_prio: number;
  simulation: boolean;
}
const form = reactive<PublisherForm>({
  enabled: false,
  interface: "",
  go_id: "",
  data_set_ref: "",
  app_id: 1,
  conf_rev: 1,
  time_allowed_to_live: 1000,
  vlan_id: 0,
  vlan_prio: 4,
  simulation: true,
});
const emit = defineEmits<{ (e: "apply", form: PublisherForm): void }>();
watch(
  () => props.block?.key,
  () => {
    const publisher = props.block?.publisher;
    if (!publisher) return;
    Object.assign(form, {
      enabled: publisher.is_running,
      interface: publisher.interface,
      go_id: publisher.go_id,
      data_set_ref: publisher.data_set_ref,
      app_id: publisher.app_id,
      conf_rev: publisher.conf_rev,
      time_allowed_to_live: publisher.time_allowed_to_live,
      vlan_id: publisher.vlan_id,
      vlan_prio: publisher.vlan_prio,
      simulation: publisher.simulation,
    });
  },
  { immediate: true }
);
function formatAppId(value: number | null) {
  return value == null ? "-" : `0x${value.toString(16).toUpperCase().padStart(4, "0")}`;
}
</script>

<style scoped lang="scss">
.control-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.config-section {
  padding: 14px 16px;
  border: 1px solid #d8dde5;
  background: #fbfcfe;
}
.section-title {
  margin-bottom: 14px;
  color: #263241;
  font-weight: 700;
}
.config-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 0 18px;
}
.config-form :deep(.el-form-item) {
  margin-bottom: 14px;
}
.config-form :deep(.el-input),
.config-form :deep(.el-input-number) {
  width: 100%;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
@media (max-width: 1000px) {
  .config-form {
    grid-template-columns: 1fr;
  }
}
</style>

<style lang="scss">
.el-select-dropdown__item.network-option-item {
  height: auto;
  min-height: auto;
  padding: 4px 12px;
}
.el-select-dropdown__item.network-option-item:first-child {
  padding-top: 0;
}
.el-select-dropdown__item.network-option-item:last-child {
  padding-bottom: 0;
}
.network-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  .network-option-icon {
    font-size: 16px;
    color: #409eff;
    flex-shrink: 0;
  }
  .network-option-body {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .network-option-name {
    font-size: 13px;
    color: #303133;
    line-height: 1.3;
  }
  .network-option-mac {
    font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", Consolas, monospace;
    font-size: 11px;
    color: #909399;
    line-height: 1.2;
  }
}
</style>
