<template>
  <el-dialog
    v-model="visible"
    :title="t('opcua.autoDiscover')"
    width="900px"
    destroy-on-close
  >
    <p class="ua-muted">{{ t("opcua.discoveryHint") }}</p>
    <el-form label-position="top" class="ua-form-grid" :disabled="busy">
      <el-form-item :label="t('opcua.browseRoot')" class="ua-span-2">
        <el-input v-model="options.node_id" placeholder="i=85" />
      </el-form-item>
      <el-form-item :label="t('opcua.discoveryDepth')">
        <el-input-number v-model="options.max_depth" :min="1" :max="64" />
      </el-form-item>
      <el-form-item :label="t('opcua.discoveryLimit')">
        <el-input-number v-model="options.max_nodes" :min="1" :max="1000" />
      </el-form-item>
      <el-form-item :label="t('opcua.discoveryTimeout')">
        <el-input-number v-model="options.timeout_s" :min="1" :max="60" />
      </el-form-item>
      <el-form-item
        ><el-checkbox v-model="options.include_standard">{{
          t("opcua.discoveryStandard")
        }}</el-checkbox></el-form-item
      >
    </el-form>
    <el-button
      type="primary"
      :disabled="!running"
      :loading="busy"
      @click="discover"
      >{{ t("opcua.autoDiscover") }}</el-button
    >
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="result">
      <p>
        {{
          t("opcua.discoverySummary", {
            visited: result.visited,
            count: result.nodes.length,
          })
        }}
      </p>
      <el-alert
        v-if="result.truncated"
        type="warning"
        :closable="false"
        :title="
          t('opcua.discoveryPartial', {
            reason: t(`opcua.discoveryReason_${result.reason}`),
          })
        "
      />
      <el-alert
        v-if="result.errors.length"
        type="warning"
        :closable="false"
        :title="t('opcua.discoveryErrors', { count: result.errors.length })"
      />
      <el-table
        ref="table"
        :data="result.nodes"
        row-key="node_id"
        max-height="320"
        @selection-change="selected = $event"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column
          prop="display_name"
          :label="t('opcua.name')"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column
          prop="node_id"
          label="NodeId"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column
          prop="data_type"
          :label="t('opcua.dataType')"
          min-width="110"
          show-overflow-tooltip
        />
        <el-table-column
          prop="namespace_uri"
          :label="t('opcua.namespaceUri')"
          min-width="190"
          show-overflow-tooltip
        />
      </el-table>
      <el-collapse v-if="result.errors.length"
        ><el-collapse-item :title="t('opcua.discoveryErrorDetails')">
          <p v-for="issue in result.errors" :key="issue.node_id">
            {{ issue.node_id }}: {{ issue.message }}
          </p>
        </el-collapse-item></el-collapse
      >
    </template>
    <template #footer>
      <el-button @click="visible = false">{{ t("opcua.cancel") }}</el-button>
      <el-button
        type="primary"
        :disabled="busy || !running || !selected.length"
        @click="apply"
      >
        {{ t("opcua.discoveryAdd", { count: selected.length }) }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  discoverOpcUaNodes,
  type OpcUaDiscoveredVariable,
  type OpcUaDiscoveryResult,
} from "@/api/opcuaApi";
const props = defineProps<{ channelId: number; running: boolean }>();
const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{ add: [nodes: OpcUaDiscoveredVariable[]] }>();
const { t } = useI18n();
const options = ref({
  node_id: "i=85",
  max_depth: 16,
  max_nodes: 1000,
  timeout_s: 30,
  include_standard: false,
});
const busy = ref(false),
  error = ref("");
const result = ref<OpcUaDiscoveryResult>();
const selected = ref<OpcUaDiscoveredVariable[]>([]);
const table = ref<{ toggleAllSelection: () => void }>();
let generation = 0;
onBeforeUnmount(() => generation++);
async function discover() {
  const current = ++generation;
  busy.value = true;
  error.value = "";
  result.value = undefined;
  selected.value = [];
  try {
    const response = await discoverOpcUaNodes(props.channelId, {
      ...options.value,
    });
    if (current !== generation) return;
    result.value = response;
    await nextTick();
    if (current === generation) table.value?.toggleAllSelection();
  } catch (e) {
    if (current === generation)
      error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (current === generation) busy.value = false;
  }
}
function apply() {
  emit("add", selected.value);
  visible.value = false;
}
watch(
  () => [props.channelId, props.running, visible.value],
  () => {
    generation++;
    busy.value = false;
    result.value = undefined;
    selected.value = [];
    error.value = "";
  },
);
</script>
