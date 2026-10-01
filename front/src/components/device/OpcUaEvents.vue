<template>
  <div>
    <OpcUaPageHeading
      :title="t('opcua.events')"
      :description="t('opcua.eventsDescription')"
    />
    <section class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.eventSettings") }}</h3>
        <el-switch
          v-model="config.enabled"
          :disabled="running"
          :active-text="t('opcua.enabled')"
        />
      </div>
      <el-form label-position="top" class="ua-form-grid" :disabled="running">
        <el-form-item :label="t('opcua.eventSource')"
          ><el-input v-model="config.source_node"
        /></el-form-item>
        <el-form-item :label="t('opcua.eventType')"
          ><el-input v-model="config.event_type"
        /></el-form-item>
        <el-form-item :label="t('opcua.severity')"
          ><el-input-number
            v-model="config.minimum_severity"
            :min="0"
            :max="1000"
            :controls="false"
        /></el-form-item>
      </el-form>
      <div class="ua-form-footer">
        <el-button :disabled="running" type="primary" @click="save">{{
          t("opcua.saveConfig")
        }}</el-button>
      </div>
    </section>
    <section v-if="role === 'server'" class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.emitEvent") }}</h3>
      </div>
      <div class="ua-toolbar emit-toolbar">
        <el-input
          v-model="message"
          :placeholder="t('opcua.eventMessage')"
        /><el-input-number
          v-model="severity"
          :min="0"
          :max="1000"
          :aria-label="t('opcua.severity')"
        /><el-button :disabled="!running" @click="emit">{{
          t("opcua.emitEvent")
        }}</el-button>
      </div>
    </section>
    <OpcUaLive :channel-id="channelId" mode="events" />
  </div>
</template>
<script setup lang="ts">
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import { onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  getOpcUaFeatures,
  saveOpcUaFeature,
  emitOpcUaEvent,
} from "@/api/opcuaApi";
import { showError } from "@/api/http";
import OpcUaLive from "./OpcUaLive.vue";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
}>();
const { t } = useI18n();
const config = ref({
  enabled: false,
  source_node: "i=2253",
  event_type: "i=2041",
  minimum_severity: 0,
});
const message = ref(""),
  severity = ref(500);
async function load() {
  try {
    config.value = {
      ...config.value,
      ...(await getOpcUaFeatures(props.channelId)).events,
    };
  } catch (e) {
    showError(e);
  }
}
async function save() {
  try {
    await saveOpcUaFeature(props.channelId, "events", config.value);
  } catch (e) {
    showError(e);
  }
}
async function emit() {
  try {
    await emitOpcUaEvent(props.channelId, message.value, severity.value);
  } catch (e) {
    showError(e);
  }
}
onMounted(load);
watch(() => props.channelId, load);
</script>
<style scoped>
.emit-toolbar {
  margin-bottom: 0;
}
</style>
