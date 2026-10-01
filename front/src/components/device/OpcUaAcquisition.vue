<template>
  <div>
    <OpcUaPageHeading
      :title="t(role === 'server' ? 'opcua.simulation' : 'opcua.subscriptions')"
      :description="
        t(
          role === 'server'
            ? 'opcua.simulationDescription'
            : 'opcua.subscriptionsDescription',
        )
      "
    >
      <div class="ua-actions">
        <el-button @click="load">{{ t("opcua.refresh") }}</el-button>
        <el-button
          type="primary"
          :disabled="running && role === 'server'"
          @click="add"
          >+
          {{
            t(role === "server" ? "opcua.addRule" : "opcua.addSubscription")
          }}</el-button
        >
      </div>
    </OpcUaPageHeading>
    <el-alert
      v-if="running && role === 'server'"
      :title="t('opcua.stopFirst')"
      type="info"
      :closable="false"
    />
    <template v-if="role === 'server'">
      <div class="ua-toolbar">
        <el-input
          v-model="ruleFilter"
          :placeholder="t('opcua.nodeSearch')"
          clearable
        />
        <div class="ua-actions">
          <el-button :disabled="!running" @click="pauseSimulation(true)">{{
            t("opcua.pause")
          }}</el-button>
          <el-button :disabled="!running" @click="pauseSimulation(false)">{{
            t("opcua.resume")
          }}</el-button>
        </div>
      </div>
      <el-table
        :data="filteredRules"
        stripe
        highlight-current-row
        class="ua-selectable"
        :row-class-name="ruleRowClass"
        @row-click="selectRule"
      >
        <el-table-column
          prop="node_id"
          :label="t('opcua.boundVariable')"
          min-width="260"
          show-overflow-tooltip
        />
        <el-table-column :label="t('opcua.rule')" width="130"
          ><template #default="{ row }">{{
            row.kind ? t("opcua." + row.kind) : "—"
          }}</template></el-table-column
        >
        <el-table-column
          prop="interval_ms"
          :label="t('opcua.intervalMs')"
          width="140"
        />
        <el-table-column :label="t('opcua.enabled')" width="110"
          ><template #default="{ row }"
            ><el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{
              t(row.enabled ? "opcua.enabled" : "opcua.disabled")
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column :label="t('opcua.actions')" width="130"
          ><template #default="{ row }"
            ><el-button link type="primary" @click.stop="selectRule(row)">{{
              t("opcua.edit")
            }}</el-button
            ><el-button
              link
              type="danger"
              :disabled="running"
              @click.stop="rules.splice(rules.indexOf(row), 1)"
              >{{ t("opcua.delete") }}</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <section v-if="selectedRule" class="ua-section editor">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.editRule") }}</h3>
          <span class="ua-code">{{ selectedRule.node_id || "NodeId" }}</span>
        </div>
        <el-form label-position="top" :disabled="running" class="ua-form-grid">
          <el-form-item :label="t('opcua.boundVariable')" class="ua-span-2"
            ><el-select v-model="selectedRule.node_id" filterable
              ><el-option
                v-for="node in nodes"
                :key="node.node_id"
                :label="node.browse_name + ' · ' + node.node_id"
                :value="node.node_id" /></el-select
          ></el-form-item>
          <el-form-item :label="t('opcua.rule')"
            ><el-select v-model="selectedRule.kind"
              ><el-option
                v-for="kind in ['fixed', 'random', 'sine', 'step']"
                :key="kind"
                :label="t('opcua.' + kind)"
                :value="kind" /></el-select
          ></el-form-item>
          <el-form-item
            v-if="selectedRule.kind === 'fixed'"
            :label="t('opcua.value')"
            ><el-input v-model="selectedRule.valueText"
          /></el-form-item>
          <template v-else>
            <el-form-item :label="t('opcua.minimum')"
              ><el-input-number
                v-model="selectedRule.minimum"
                :controls="false"
            /></el-form-item>
            <el-form-item :label="t('opcua.maximum')"
              ><el-input-number
                v-model="selectedRule.maximum"
                :controls="false"
            /></el-form-item>
            <el-form-item
              v-if="selectedRule.kind === 'sine'"
              :label="t('opcua.periodSeconds')"
              ><el-input-number
                v-model="selectedRule.period_s"
                :min="0.01"
                :controls="false"
            /></el-form-item>
            <el-form-item
              v-if="selectedRule.kind === 'sine'"
              :label="t('opcua.offsetSeconds')"
              ><el-input-number
                v-model="selectedRule.offset_s"
                :controls="false"
            /></el-form-item>
            <el-form-item
              v-if="selectedRule.kind === 'step'"
              :label="t('opcua.stepSize')"
              ><el-input-number v-model="selectedRule.step" :controls="false"
            /></el-form-item>
          </template>
          <el-form-item :label="t('opcua.intervalMs')"
            ><el-input-number
              v-model="selectedRule.interval_ms"
              :min="50"
              :controls="false"
          /></el-form-item>
          <el-form-item :label="t('opcua.writePolicy')"
            ><el-select v-model="selectedRule.write_policy"
              ><el-option
                v-for="policy in ['pause', 'overwrite', 'reject']"
                :key="policy"
                :label="t('opcua.policy' + policy)"
                :value="policy" /></el-select
          ></el-form-item>
          <el-form-item :label="t('opcua.enabled')"
            ><el-switch v-model="selectedRule.enabled"
          /></el-form-item>
        </el-form>
        <div class="ua-form-footer">
          <el-button
            type="primary"
            :disabled="running"
            :loading="saving"
            @click="save"
            >{{ t("opcua.saveConfig") }}</el-button
          >
        </div>
      </section>
    </template>
    <template v-else>
      <el-table
        :data="subscriptions"
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
              ><el-input
                v-model="selectedItem.node_id"
                placeholder="ns=2;s=..."
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
        <el-table :data="runtime" stripe>
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
    </template>
    <div v-if="role === 'client' || !selectedRule" class="ua-form-footer">
      <el-button
        type="primary"
        :disabled="running && role === 'server'"
        :loading="saving"
        @click="save"
        >{{ t("opcua.saveConfig") }}</el-button
      >
    </div>
    <p class="ua-note footer-note">
      {{
        t(role === "server" ? "opcua.simulationHint" : "opcua.subscriptionHint")
      }}
    </p>
  </div>
</template>
<script setup lang="ts">
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  getOpcUaCapabilities,
  getOpcUaFeatures,
  listOpcUaVariables,
  saveOpcUaFeature,
  pauseOpcUaSimulation,
} from "@/api/opcuaApi";
import type { OpcUaVariable } from "@/api/opcuaApi";
import { showError } from "@/api/http";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
}>();
const { t } = useI18n();
const rules = ref<any[]>([]),
  subscriptions = ref<any[]>([]),
  nodes = ref<OpcUaVariable[]>([]),
  runtime = ref<any[]>([]);
const selectedRuleIndex = ref(0),
  selectedSubIndex = ref(0),
  selectedItemIndex = ref(0);
const selectedRule = computed(() => rules.value[selectedRuleIndex.value]);
const selectedSub = computed(() => subscriptions.value[selectedSubIndex.value]);
const selectedItem = computed(
  () => selectedSub.value?.items[selectedItemIndex.value],
);
const ruleFilter = ref("");
const filteredRules = computed(() =>
  rules.value.filter((r) =>
    `${r.node_id} ${r.kind}`
      .toLowerCase()
      .includes(ruleFilter.value.toLowerCase()),
  ),
);
function selectRule(row: any) {
  selectedRuleIndex.value = rules.value.indexOf(row);
}
function ruleRowClass({ row }: { row: any }) {
  return row === selectedRule.value ? "ua-current-row" : "";
}
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
    rules.value = (features.simulation?.rules || []).map((r: any) => ({
      ...r,
      valueText: JSON.stringify(r.value ?? 0),
    }));
    subscriptions.value = features.subscriptions?.subscriptions || [];
    reconnect.value = features.subscriptions?.reconnect ?? true;
    selectedRuleIndex.value = Math.max(
      0,
      Math.min(selectedRuleIndex.value, rules.value.length - 1),
    );
    selectedSubIndex.value = Math.max(
      0,
      Math.min(selectedSubIndex.value, subscriptions.value.length - 1),
    );
    if (props.role === "server")
      nodes.value = (await listOpcUaVariables(props.channelId)).nodes;
    else {
      const capability = (
        await getOpcUaCapabilities(props.channelId)
      ).capabilities.find((c) => c.name === "subscriptions");
      const states = (capability?.details?.subscriptions || []) as any[];
      runtime.value = states.flatMap((s) =>
        (s.items || []).map((item: any) => ({ ...item, subscription: s.id })),
      );
    }
  } catch (e) {
    showError(e);
  }
}
function add() {
  if (props.role === "server") {
    selectedRuleIndex.value = rules.value.length;
    rules.value.push({
      node_id: "",
      kind: "sine",
      minimum: 0,
      maximum: 100,
      period_s: 10,
      offset_s: 0,
      interval_ms: 500,
      step: 1,
      valueText: "0",
      write_policy: "pause",
      enabled: true,
    });
  } else {
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
}
async function pauseSimulation(paused: boolean) {
  try {
    await pauseOpcUaSimulation(props.channelId, paused);
  } catch (e) {
    showError(e);
  }
}
async function save() {
  saving.value = true;
  try {
    const config =
      props.role === "server"
        ? {
            rules: rules.value.map(({ valueText, ...rule }) => ({
              ...rule,
              value: JSON.parse(valueText),
            })),
          }
        : { subscriptions: subscriptions.value, reconnect: reconnect.value };
    await saveOpcUaFeature(
      props.channelId,
      props.role === "server" ? "simulation" : "subscriptions",
      config,
    );
    ElMessage.success(t("opcua.configSaved"));
    await load();
  } catch (e) {
    showError(e);
  } finally {
    saving.value = false;
  }
}
onMounted(load);
watch(() => [props.channelId, props.running], load);
</script>
<style scoped>
.editor {
  margin-top: 16px;
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
