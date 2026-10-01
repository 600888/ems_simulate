<template>
  <div v-loading="loading">
    <OpcUaPageHeading
      :title="t('opcua.runtime')"
      :description="status?.endpoint_url || 'OPC UA'"
    >
      <el-button @click="refresh">{{ t("opcua.refreshStatus") }}</el-button>
    </OpcUaPageHeading>
    <div class="ua-metrics">
      <div class="ua-metric">
        <span>{{ t("opcua.connectionStatus") }}</span
        ><strong :class="status?.running ? 'ua-good' : 'ua-muted'">{{
          t(status?.running ? "opcua.running" : "opcua.stopped")
        }}</strong>
      </div>
      <div class="ua-metric">
        <span>{{ t("opcua.runtimeNodeCount") }}</span
        ><strong>{{ status?.node_count ?? "—" }}</strong>
      </div>
      <div class="ua-metric">
        <span>{{ t("opcua.enabledCapabilities") }}</span
        ><strong>{{ capabilities.filter((c) => c.enabled).length }}</strong>
      </div>
      <div class="ua-metric">
        <span>{{ t("opcua.runningCapabilities") }}</span
        ><strong>{{ capabilities.filter((c) => c.running).length }}</strong>
      </div>
    </div>
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.endpointConfig") }}</h3>
      </div>
      <el-descriptions v-if="status" :column="2" border>
        <el-descriptions-item :label="t('opcua.connectionStatus')">{{
          t(status.running ? "opcua.running" : "opcua.stopped")
        }}</el-descriptions-item>
        <el-descriptions-item label="Endpoint">{{
          status.endpoint_url || "-"
        }}</el-descriptions-item>
        <el-descriptions-item
          v-if="status.node_count !== null && status.node_count !== undefined"
          :label="t('opcua.runtimeNodeCount')"
          >{{ status.node_count }}</el-descriptions-item
        >
        <el-descriptions-item :label="t('opcua.lastError')">{{
          status.error || "-"
        }}</el-descriptions-item>
      </el-descriptions>
    </section>
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.serviceOverview") }}</h3>
      </div>
      <el-table :data="capabilities" stripe>
        <el-table-column :label="t('opcua.capability')" width="180">
          <template #default="{ row }"
            ><el-tag
              :type="row.running ? 'success' : 'info'"
              size="small"
              effect="light"
              >{{ labels[row.name] || row.name }}</el-tag
            ></template
          >
        </el-table-column>
        <el-table-column :label="t('opcua.state')" width="150">
          <template #default="{ row }">{{
            t(
              !row.enabled
                ? "opcua.disabled"
                : row.running
                  ? "opcua.running"
                  : "opcua.notRunning",
            )
          }}</template>
        </el-table-column>
        <el-table-column prop="reason" :label="t('opcua.reason')" />
      </el-table>
    </section>
    <el-alert
      v-if="status?.error"
      :title="status.error"
      type="error"
      :closable="false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import { useI18n } from "vue-i18n";
import { showError } from "@/api/http";
import { getOpcUaCapabilities, getOpcUaStatus } from "@/api/opcuaApi";
import type { OpcUaCapability, OpcUaStatus } from "@/api/opcuaApi";

const props = defineProps<{ channelId: number; running: boolean }>();
const { t } = useI18n();
const status = ref<OpcUaStatus | null>(null);
const capabilities = ref<OpcUaCapability[]>([]);
const loading = ref(false);
const labels = computed<Record<string, string>>(() => ({
  transport: t("opcua.transport"),
  address_space: t("opcua.addressSpaceCapability"),
  model_io: t("opcua.modelIoCapability"),
  simulation: t("opcua.simulation"),
  subscriptions: t("opcua.subscriptions"),
  history: t("opcua.history"),
  events: t("opcua.events"),
}));

async function refresh() {
  loading.value = true;
  const results = await Promise.allSettled([
    getOpcUaStatus(props.channelId),
    getOpcUaCapabilities(props.channelId),
  ]);
  if (results[0].status === "fulfilled") status.value = results[0].value;
  else showError(results[0].reason);
  if (results[1].status === "fulfilled")
    capabilities.value = results[1].value.capabilities;
  else showError(results[1].reason);
  loading.value = false;
}

watch(
  () => [props.channelId, props.running],
  () => {
    void refresh();
  },
);
onMounted(() => {
  void refresh();
});
</script>

<style scoped>
.refresh {
  margin-bottom: 12px;
}
.capabilities {
  margin-top: 20px;
}
</style>
