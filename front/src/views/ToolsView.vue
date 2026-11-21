<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Connection, Search } from "@element-plus/icons-vue";
import { getApiErrorMessage } from "@/api/http";
import {
  getSubnetScan,
  startSubnetScan,
  stopSubnetScan,
  type SubnetScan,
} from "@/api/toolsApi";

const { t } = useI18n();
const subnet = ref("192.168.1");
const timeoutMs = ref(1000);
const scan = ref<SubnetScan | null>(null);
const starting = ref(false);
const stopping = ref(false);
const onlyReachable = ref(true);
const validationError = ref("");
const requestError = ref("");
let generation = 0;
let disposed = false;
let timer: ReturnType<typeof setTimeout> | undefined;

const busy = computed(
  () => starting.value || stopping.value || scan.value?.status === "running",
);
const rows = computed(() =>
  (scan.value?.results ?? []).filter(
    (row) => !onlyReachable.value || row.reachable,
  ),
);
const progress = computed(() =>
  scan.value ? Math.floor((scan.value.completed / scan.value.total) * 100) : 0,
);
const statusLabel = computed(() => {
  if (!scan.value) return t("tools.ready");
  const labels = {
    running: "running",
    completed: "finished",
    cancelled: "cancelled",
    failed: "failed",
  };
  return t(`tools.${labels[scan.value.status]}`);
});

function validSubnet(value: string): boolean {
  const match =
    /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?:\.(\d{1,3})(?:\/(\d{1,2}))?)?$/.exec(
      value,
    );
  if (!match) return false;
  const octets = match
    .slice(1, 5)
    .filter((part) => part !== undefined)
    .map(Number);
  if (octets.some((part) => part > 255) || octets[0] === 0 || octets[0]! >= 224)
    return false;
  return (
    match[5] === undefined || (Number(match[5]) >= 24 && Number(match[5]) <= 32)
  );
}

async function poll(token = generation) {
  const id = scan.value?.id;
  if (!id || disposed || token !== generation) return;
  clearTimeout(timer);
  requestError.value = "";
  try {
    const result = await getSubnetScan(id);
    if (disposed || token !== generation) return;
    scan.value = result;
    if (result.status === "running")
      timer = setTimeout(() => void poll(token), 500);
  } catch (error) {
    if (!disposed && token === generation)
      requestError.value = getApiErrorMessage(error, t("tools.requestFailed"));
  }
}

async function start() {
  if (busy.value) return;
  const value = subnet.value.trim();
  validationError.value = validSubnet(value) ? "" : t("tools.invalidSubnet");
  if (validationError.value) return;
  const token = ++generation;
  clearTimeout(timer);
  starting.value = true;
  requestError.value = "";
  try {
    const result = await startSubnetScan(value, timeoutMs.value);
    if (disposed) {
      void stopSubnetScan(result.id).catch(() => {});
      return;
    }
    scan.value = result;
    void poll(token);
  } catch (error) {
    requestError.value = getApiErrorMessage(error, t("tools.requestFailed"));
  } finally {
    starting.value = false;
  }
}

async function stop() {
  if (!scan.value || stopping.value) return;
  ++generation;
  clearTimeout(timer);
  stopping.value = true;
  requestError.value = "";
  try {
    scan.value = await stopSubnetScan(scan.value.id);
  } catch (error) {
    requestError.value = getApiErrorMessage(error, t("tools.requestFailed"));
  } finally {
    stopping.value = false;
  }
}

onBeforeUnmount(() => {
  disposed = true;
  ++generation;
  clearTimeout(timer);
  if (scan.value?.status === "running")
    void stopSubnetScan(scan.value.id).catch(() => {});
});
</script>

<template>
  <div class="tools-container">
    <aside class="tools-sidebar">
      <el-menu default-active="subnet" class="tools-menu">
        <el-menu-item index="subnet">
          <el-icon><Connection /></el-icon>
          <span>{{ t("tools.subnetScan") }}</span>
        </el-menu-item>
      </el-menu>
    </aside>
    <main class="tools-content">
      <h3>{{ t("tools.subnetScan") }}</h3>
      <p class="description">{{ t("tools.description") }}</p>
      <div class="scan-card">
        <el-form label-position="top" @submit.prevent="start">
          <el-form-item :label="t('tools.subnet')" :error="validationError">
            <el-input
              v-model="subnet"
              :disabled="busy"
              :placeholder="t('tools.placeholder')"
              :aria-label="t('tools.subnet')"
              clearable
              @input="validationError = ''"
            />
          </el-form-item>
          <p class="input-hint">{{ t("tools.inputHint") }}</p>
          <div class="scan-controls">
            <div class="timeout-control">
              <span>{{ t("tools.timeout") }}</span>
              <el-select
                v-model="timeoutMs"
                :disabled="busy"
                :aria-label="t('tools.timeout')"
              >
                <el-option
                  v-for="value in [500, 1000, 2000, 5000]"
                  :key="value"
                  :value="value"
                  :label="t('tools.milliseconds', { value })"
                />
              </el-select>
            </div>
            <el-button
              v-if="scan?.status === 'running'"
              :loading="stopping"
              @click="stop"
              >{{ t("tools.stop") }}</el-button
            >
            <el-button
              v-else
              type="primary"
              :icon="Search"
              :loading="starting"
              native-type="submit"
              >{{ t("tools.start") }}</el-button
            >
          </div>
        </el-form>
      </div>

      <div class="scan-stats" aria-live="polite">
        <div>
          <strong>{{ scan?.total ?? "—" }}</strong
          ><span>{{ t("tools.total") }}</span>
        </div>
        <div>
          <strong>{{ scan?.completed ?? 0 }}</strong
          ><span>{{ t("tools.completed") }}</span>
        </div>
        <div class="reachable-stat">
          <strong>{{ scan?.reachable ?? 0 }}</strong
          ><span>{{ t("tools.reachable") }}</span>
        </div>
        <div>
          <strong>{{ scan?.unreachable ?? 0 }}</strong
          ><span>{{ t("tools.unreachable") }}</span>
        </div>
      </div>

      <div class="progress-header">
        <span
          >{{ statusLabel
          }}<template v-if="scan"> · {{ scan.subnet }}</template></span
        >
        <span v-if="scan">{{ scan.completed }} / {{ scan.total }}</span>
      </div>
      <el-progress
        :percentage="progress"
        :show-text="false"
        :aria-label="t('tools.progress')"
        :status="scan?.status === 'completed' ? 'success' : undefined"
      />
      <el-alert
        v-if="requestError || scan?.error"
        class="scan-error"
        type="error"
        :closable="false"
        show-icon
        :title="requestError || scan?.error || ''"
      />
      <el-button
        v-if="requestError && scan?.status === 'running'"
        class="retry-button"
        @click="poll()"
        >{{ t("tools.retry") }}</el-button
      >
      <div class="results-header">
        <span>{{ t("tools.ip") }}</span>
        <el-switch
          v-model="onlyReachable"
          :active-text="t('tools.onlyReachable')"
        />
      </div>
      <el-table
        :data="rows"
        height="230"
        :empty-text="
          !scan
            ? t('tools.empty')
            : onlyReachable
              ? t('tools.noReachable')
              : t('tools.noResults')
        "
        row-key="ip"
      >
        <el-table-column prop="ip" :label="t('tools.ip')" min-width="150" />
        <el-table-column :label="t('tools.status')" min-width="110">
          <template #default="{ row }">
            <el-tag
              :type="row.reachable ? 'success' : 'info'"
              effect="plain"
              size="small"
              >{{
                t(row.reachable ? "tools.reachable" : "tools.unreachable")
              }}</el-tag
            >
          </template>
        </el-table-column>
        <el-table-column :label="t('tools.latency')" min-width="110">
          <template #default="{ row }">{{
            row.latency_ms === null ? "—" : `${row.latency_ms} ms`
          }}</template>
        </el-table-column>
      </el-table>
      <p class="scan-note">{{ t("tools.note") }}</p>
    </main>
  </div>
</template>

<style scoped lang="scss">
.tools-container {
  display: flex;
  height: 660px;
  max-height: calc(var(--app-viewport-height, 100vh) - 120px);
  container-type: inline-size;
  background: var(--bg-main);
  border-radius: 12px;
  overflow: hidden;
}
.tools-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--panel-bg);
  border-right: 1px solid var(--sidebar-border);
}
.tools-menu {
  border-right: none;
  background: transparent;
  .el-menu-item {
    height: 40px;
    line-height: 40px;
    margin: 2px 8px;
    border-radius: 8px;
    color: var(--text-secondary);
    &:hover {
      background: var(--item-hover-bg);
    }
    &.is-active {
      background: var(--item-active-bg);
      color: var(--color-primary);
      font-weight: 500;
    }
    .el-icon {
      font-size: 18px;
    }
  }
}
.tools-content {
  flex: 1;
  min-width: 0;
  padding: 24px 28px;
  overflow-y: auto;
  h3 {
    margin: 0 0 8px;
    font-size: 18px;
    color: var(--text-primary);
  }
}
.description,
.input-hint,
.scan-note {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.description {
  margin: 0 0 16px;
}
.scan-card {
  padding: 16px;
  background: var(--panel-bg);
  border: 1px solid var(--sidebar-border);
  border-radius: 12px;
}
.input-hint {
  margin: 4px 0 16px;
}
.scan-controls,
.timeout-control,
.progress-header,
.results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.timeout-control {
  justify-content: flex-start;
  font-size: 12px;
  color: var(--text-secondary);
  .el-select {
    width: 120px;
  }
}
.scan-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0;
  > div {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px;
    background: var(--panel-bg);
    border: 1px solid var(--sidebar-border);
    border-radius: 8px;
  }
  strong {
    font-size: 24px;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }
  span {
    font-size: 12px;
    color: var(--text-secondary);
  }
  .reachable-stat strong {
    color: var(--el-color-success);
  }
}
.progress-header {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.results-header {
  margin: 12px 0 8px;
  font-size: 13px;
  color: var(--text-primary);
}
.scan-error,
.retry-button {
  margin-top: 12px;
}
.scan-note {
  margin: 12px 0 0;
}
@container (max-width: 700px) {
  .tools-sidebar {
    width: 150px;
  }
  .tools-content {
    padding: 16px;
  }
  .scan-controls {
    flex-wrap: wrap;
  }
  .scan-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 460px) {
  .tools-sidebar {
    width: 110px;
  }
  .tools-menu .el-menu-item {
    padding: 0 8px;
    margin: 2px 4px;
    white-space: normal;
    line-height: 1.4;
  }
  .tools-menu .el-menu-item .el-icon {
    display: none;
  }
  .tools-content {
    padding: 12px;
  }
  .scan-card {
    padding: 12px;
  }
  .timeout-control,
  .results-header,
  .progress-header {
    flex-wrap: wrap;
  }
}
</style>
