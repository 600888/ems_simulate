<template>
  <div>
    <OpcUaPageHeading
      :title="t('opcua.diagnostics')"
      :description="t('opcua.diagnosticsDescription')"
    />
    <section class="ua-section">
      <div class="toolbar">
        <el-button @click="load">{{ t("opcua.query") }}</el-button
        ><el-input
          v-model="filter"
          :placeholder="t('opcua.serviceFilter')"
          clearable
        /><el-button @click="exportCsv">{{ t("opcua.exportCsv") }}</el-button>
      </div>
      <div class="ua-section-heading">
        <h3>{{ t("opcua.sessionHistory") }}</h3>
        <span>{{ sessions.length }}</span>
      </div>
      <el-table :data="sessions" stripe max-height="300">
        <el-table-column
          prop="session_id"
          :label="t('opcua.session')"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="application_uri"
          label="Application URI"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column
          prop="username"
          :label="t('opcua.username')"
          width="130"
          show-overflow-tooltip
        />
        <el-table-column prop="state" :label="t('opcua.state')" width="120" />
        <el-table-column
          prop="timestamp"
          :label="t('opcua.sourceTimestamp')"
          min-width="220"
        />
        <el-table-column
          prop="reason"
          :label="t('opcua.reason')"
          min-width="200"
          show-overflow-tooltip
        />
      </el-table>
    </section>
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.serviceCalls") }}</h3>
        <span>{{ visible.length }}</span>
      </div>
      <el-table :data="visible" stripe max-height="420">
        <el-table-column
          prop="timestamp"
          :label="t('opcua.sourceTimestamp')"
          min-width="240"
        />
        <el-table-column
          prop="service"
          :label="t('opcua.service')"
          width="150"
        />
        <el-table-column
          prop="node_id"
          label="NodeId"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column
          prop="status_code"
          :label="t('opcua.quality')"
          min-width="190"
          show-overflow-tooltip
        />
        <el-table-column
          prop="duration_ms"
          :label="t('opcua.durationMs')"
          width="140"
        />
      </el-table>
    </section>
  </div>
</template>
<script setup lang="ts">
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { getOpcUaDiagnostics } from "@/api/opcuaApi";
import { showError } from "@/api/http";
const props = defineProps<{ channelId: number }>();
const { t } = useI18n();
const calls = ref<Record<string, unknown>[]>([]),
  sessions = ref<Record<string, unknown>[]>([]),
  filter = ref("");
const visible = computed(() =>
  calls.value
    .filter((c) =>
      `${c.service} ${c.status_code}`
        .toLowerCase()
        .includes(filter.value.toLowerCase()),
    )
    .slice()
    .reverse(),
);
async function load() {
  try {
    const data = await getOpcUaDiagnostics(props.channelId);
    calls.value = data.calls;
    sessions.value = data.sessions;
  } catch (e) {
    showError(e);
  }
}
function exportCsv() {
  const csv = [
    "time,service,status,duration_ms,node_id",
    ...visible.value.map((c) =>
      [c.timestamp, c.service, c.status_code, c.duration_ms, c.node_id]
        .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`)
        .join(","),
    ),
  ].join("\r\n");
  const url = URL.createObjectURL(
    new Blob(["\uFEFF", csv], { type: "text/csv" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "opcua-calls.csv";
  link.click();
  URL.revokeObjectURL(url);
}
onMounted(load);
watch(() => props.channelId, load);
</script>
<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.toolbar .el-input {
  max-width: 360px;
}
</style>
