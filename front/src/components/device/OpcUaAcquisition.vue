<template>
  <OpcUaSimulation
    v-if="role === 'server'"
    :channel-id="channelId"
    :running="running"
    :active="active"
    :selected-node-id="selectedNodeId"
    :revision="revision"
  />
  <div v-else>
    <OpcUaPageHeading
      :title="t('opcua.subscriptions')"
      :description="t('opcua.subscriptionsDescription')"
    >
      <div class="ua-actions">
        <el-button @click="load">{{ t("opcua.refresh") }}</el-button>
        <el-button type="primary" @click="add"
          >+ {{ t("opcua.addSubscription") }}</el-button
        >
      </div>
    </OpcUaPageHeading>
    <el-table
      :data="subscriptions"
      max-height="360"
      stripe
      highlight-current-row
      class="ua-selectable"
      :current-row-key="selectedSub?.id"
      row-key="id"
      @row-click="selectSub"
    >
      <el-table-column
        prop="id"
        :label="t('opcua.subscriptionName')"
        min-width="220"
        show-overflow-tooltip
      />
      <el-table-column
        prop="publishing_interval_ms"
        :label="t('opcua.publishingMs')"
        width="150"
      />
      <el-table-column
        prop="keepalive_count"
        :label="t('opcua.keepaliveCount')"
        width="120"
      />
      <el-table-column
        prop="lifetime_count"
        :label="t('opcua.lifetimeCount')"
        width="120"
      />
      <el-table-column :label="t('opcua.monitoredItems')" width="100"
        ><template #default="{ row }">{{
          row.items.length
        }}</template></el-table-column
      >
      <el-table-column :label="t('opcua.enabled')" width="100"
        ><template #default="{ row }"
          ><el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{
            t(row.enabled ? "opcua.enabled" : "opcua.disabled")
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column :label="t('opcua.actions')" width="130"
        ><template #default="{ row }"
          ><el-button link type="primary" @click.stop="selectSub(row)">{{
            t("opcua.edit")
          }}</el-button
          ><el-button
            link
            type="danger"
            @click.stop="subscriptions.splice(subscriptions.indexOf(row), 1)"
            >{{ t("opcua.delete") }}</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <section v-if="selectedSub" class="ua-section editor">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.subscriptionSettings") }}</h3>
        <el-switch
          v-model="selectedSub.enabled"
          :active-text="t('opcua.enabled')"
        />
      </div>
      <el-form label-position="top" class="ua-form-grid">
        <el-form-item :label="t('opcua.subscriptionName')"
          ><el-input v-model="selectedSub.id"
        /></el-form-item>
        <el-form-item :label="t('opcua.publishingMs')"
          ><el-input-number
            v-model="selectedSub.publishing_interval_ms"
            :min="50"
            :controls="false"
        /></el-form-item>
        <el-form-item :label="t('opcua.keepaliveCount')"
          ><el-input-number
            v-model="selectedSub.keepalive_count"
            :min="1"
            :controls="false"
        /></el-form-item>
        <el-form-item :label="t('opcua.lifetimeCount')"
          ><el-input-number
            v-model="selectedSub.lifetime_count"
            :min="3"
            :controls="false"
        /></el-form-item>
      </el-form>
      <div class="ua-section-heading">
        <h3>
          {{ selectedSub.id }} · {{ selectedSub.items.length }}
          {{ t("opcua.monitoredItems") }}
        </h3>
        <el-button type="primary" @click="addItem"
          >+ {{ t("opcua.addItem") }}</el-button
        >
      </div>
      <el-table
        :data="selectedSub.items"
        max-height="360"
        stripe
        highlight-current-row
        class="ua-selectable"
        @row-click="selectItem"
      >
        <el-table-column
          prop="node_id"
          label="NodeId"
          min-width="250"
          show-overflow-tooltip
        />
        <el-table-column
          prop="sampling_interval_ms"
          :label="t('opcua.samplingMs')"
          width="140"
        />
        <el-table-column
          prop="queue_size"
          :label="t('opcua.queueSize')"
          width="100"
        />
        <el-table-column
          prop="deadband"
          :label="t('opcua.deadband')"
          width="100"
        />
        <el-table-column prop="mode" :label="t('opcua.mode')" width="120" />
        <el-table-column :label="t('opcua.actions')" width="130"
          ><template #default="{ row, $index }"
            ><el-button link type="primary" @click.stop="selectItem(row)">{{
              t("opcua.edit")
            }}</el-button
            ><el-button
              link
              type="danger"
              @click.stop="selectedSub.items.splice($index, 1)"
              >{{ t("opcua.delete") }}</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <div v-if="selectedItem" class="item-editor">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.itemSettings") }}</h3>
        </div>
        <el-form label-position="top" class="ua-form-grid">
          <el-form-item label="NodeId" class="ua-span-2"
            ><el-input v-model="selectedItem.node_id" placeholder="ns=2;s=..."
          /></el-form-item>
          <el-form-item :label="t('opcua.samplingMs')"
            ><el-input-number
              v-model="selectedItem.sampling_interval_ms"
              :min="0"
              :controls="false"
          /></el-form-item>
          <el-form-item :label="t('opcua.queueSize')"
            ><el-input-number
              v-model="selectedItem.queue_size"
              :min="1"
              :max="10000"
              :controls="false"
          /></el-form-item>
          <el-form-item :label="t('opcua.deadband')"
            ><el-input-number
              v-model="selectedItem.deadband"
              :min="0"
              :controls="false"
          /></el-form-item>
          <el-form-item :label="t('opcua.mode')"
            ><el-select v-model="selectedItem.mode"
              ><el-option
                v-for="mode in ['Disabled', 'Sampling', 'Reporting']"
                :key="mode"
                :label="mode"
                :value="mode" /></el-select
          ></el-form-item>
        </el-form>
      </div>
    </section>
    <section class="ua-section editor">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.revisedParameters") }}</h3>
        <el-checkbox v-model="reconnect">{{
          t("opcua.autoReconnect")
        }}</el-checkbox>
      </div>
      <el-table :data="runtime" stripe max-height="360">
        <el-table-column
          prop="subscription"
          :label="t('opcua.subscriptions')"
          min-width="150"
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
          min-width="170"
        />
        <el-table-column
          prop="sampling_interval_ms"
          :label="t('opcua.revisedSampling')"
          width="160"
        />
        <el-table-column
          prop="queue_size"
          :label="t('opcua.queueSize')"
          width="100"
        />
      </el-table>
    </section>
    <div class="ua-form-footer">
      <el-button type="primary" :loading="saving" @click="save">{{
        t("opcua.saveConfig")
      }}</el-button>
    </div>
    <p class="ua-note footer-note">
      {{ t("opcua.subscriptionHint") }}
    </p>
  </div>
</template>
<script setup lang="ts">
import OpcUaSimulation from "./OpcUaSimulation.vue";
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  getOpcUaCapabilities,
  getOpcUaFeatures,
  saveOpcUaFeature,
} from "@/api/opcuaApi";
import { showError } from "@/api/http";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
  selectedNodeId?: string;
  active?: boolean;
  revision?: number;
}>();
const { t } = useI18n();
const subscriptions = ref<any[]>([]),
  runtime = ref<any[]>([]);
const selectedSubIndex = ref(0),
  selectedItemIndex = ref(0);
const selectedSub = computed(() => subscriptions.value[selectedSubIndex.value]);
const selectedItem = computed(
  () => selectedSub.value?.items[selectedItemIndex.value],
);
function selectSub(row: any) {
  selectedSubIndex.value = subscriptions.value.indexOf(row);
  selectedItemIndex.value = 0;
}
function selectItem(row: any) {
  selectedItemIndex.value = selectedSub.value.items.indexOf(row);
}
function addItem() {
  selectedSub.value.items.push({
    node_id: "",
    sampling_interval_ms: 500,
    queue_size: 10,
    deadband: 0,
    mode: "Reporting",
  });
  selectedItemIndex.value = selectedSub.value.items.length - 1;
}
const reconnect = ref(true),
  saving = ref(false);
async function load() {
  try {
    const features = await getOpcUaFeatures(props.channelId);
    subscriptions.value = features.subscriptions?.subscriptions || [];
    reconnect.value = features.subscriptions?.reconnect ?? true;
    selectedSubIndex.value = Math.max(
      0,
      Math.min(selectedSubIndex.value, subscriptions.value.length - 1),
    );
    const capability = (
      await getOpcUaCapabilities(props.channelId)
    ).capabilities.find((c) => c.name === "subscriptions");
    const states = (capability?.details?.subscriptions || []) as any[];
    runtime.value = states.flatMap((s) =>
      (s.items || []).map((item: any) => ({ ...item, subscription: s.id })),
    );
  } catch (e) {
    showError(e);
  }
}
function add() {
  selectedSubIndex.value = subscriptions.value.length;
  selectedItemIndex.value = 0;
  subscriptions.value.push({
    id: `subscription-${Date.now()}`,
    publishing_interval_ms: 500,
    lifetime_count: 10000,
    keepalive_count: 10,
    enabled: true,
    items: [],
  });
}
async function save() {
  saving.value = true;
  try {
    await saveOpcUaFeature(props.channelId, "subscriptions", {
      subscriptions: subscriptions.value,
      reconnect: reconnect.value,
    });
    ElMessage.success(t("opcua.configSaved"));
    await load();
  } catch (e) {
    showError(e);
  } finally {
    saving.value = false;
  }
}
onMounted(() => {
  if (props.role === "client") void load();
});
watch(
  () => [props.channelId, props.running, props.role],
  () => {
    if (props.role === "client") void load();
  },
);
</script>
<style scoped>
.editor {
  margin-top: 16px;
}
.editor .ua-section-heading > h3 {
  min-width: 0;
  overflow-wrap: anywhere;
}
.editor .ua-section-heading > .ua-code {
  flex: 1 1 220px;
  min-width: 0;
  text-align: right;
}
.item-editor {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--ua-line);
}
.footer-note {
  margin-top: 16px;
}
</style>
