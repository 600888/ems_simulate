<template>
  <el-dialog
    :model-value="visible"
    :title="t('opcua.publisherSettings')"
    width="min(840px, 95vw)"
    @update:model-value="emit('close')"
  >
    <el-tabs v-model="tab">
      <el-tab-pane :label="t('opcua.publisherSettings')" name="publisher">
        <el-form label-position="top" class="settings-grid">
          <el-form-item label="PublisherId"
            ><el-input v-model="draft.publisher_id" maxlength="128"
          /></el-form-item>
          <el-form-item :label="t('opcua.brokerUrl')"
            ><el-input
              v-model="draft.broker_url"
              placeholder="mqtt://127.0.0.1:1883"
          /></el-form-item>
          <el-form-item label="WriterGroup"
            ><el-input v-model="draft.writer_group_name"
          /></el-form-item>
          <el-form-item :label="t('opcua.publishingMs')"
            ><el-input-number
              v-model="draft.publishing_interval_ms"
              :min="50"
              :max="3600000"
          /></el-form-item>
        </el-form>
        <el-descriptions :column="2" border
          ><el-descriptions-item :label="t('opcua.transport')"
            >MQTT 3.1.1 · QoS 0</el-descriptions-item
          ><el-descriptions-item :label="t('opcua.encoding')"
            >JSON · OPC UA 1.04</el-descriptions-item
          ></el-descriptions
        >
        <p class="ua-muted">{{ t("opcua.mqttProfileHint") }}</p>
        <h4>{{ t("opcua.messageContentMask") }}</h4>
        <el-checkbox-group v-model="draft.message_content"
          ><el-checkbox
            v-for="flag in messageFlags"
            :key="flag"
            :value="flag"
            >{{ flag }}</el-checkbox
          ></el-checkbox-group
        >
        <h4>{{ t("opcua.fieldContentMask") }}</h4>
        <el-checkbox-group v-model="draft.field_content"
          ><el-checkbox v-for="flag in fieldFlags" :key="flag" :value="flag">{{
            t(
              `opcua.${flag === "status_code" ? "quality" : flag === "source_timestamp" ? "sourceTimestamp" : "serverTimestamp"}`,
            )
          }}</el-checkbox></el-checkbox-group
        >
      </el-tab-pane>
      <el-tab-pane :label="t('opcua.datasetSettings')" name="datasets">
        <div class="ua-toolbar">
          <el-select v-model="writerIndex"
            ><el-option
              v-for="(writer, index) in draft.writers"
              :key="index"
              :value="index"
              :label="`${writer.writer_id} · ${writer.name}`" /></el-select
          ><el-button @click="addWriter('variables')">{{
            t("opcua.addVariableDataset")
          }}</el-button
          ><el-button @click="addWriter('events')">{{
            t("opcua.addEventDataset")
          }}</el-button
          ><el-button
            type="danger"
            plain
            :disabled="!writer"
            @click="removeWriter"
            >{{ t("opcua.delete") }}</el-button
          >
        </div>
        <template v-if="writer">
          <el-form label-position="top" class="settings-grid">
            <el-form-item label="DataSetWriterId"
              ><el-input-number
                v-model="writer.writer_id"
                :min="1"
                :max="65535"
            /></el-form-item>
            <el-form-item :label="t('opcua.datasetName')"
              ><el-input v-model="writer.name"
            /></el-form-item>
            <el-form-item :label="t('opcua.dataTopic')"
              ><el-input v-model="writer.topic"
            /></el-form-item>
            <el-form-item :label="t('opcua.metadataTopic')"
              ><el-input v-model="writer.metadata_topic"
            /></el-form-item>
            <el-form-item
              v-if="writer.kind === 'variables'"
              label="KeyFrameCount"
              ><el-input-number
                v-model="writer.key_frame_count"
                :min="1"
                :max="1000"
            /></el-form-item>
            <el-form-item :label="t('opcua.enabled')"
              ><el-switch v-model="writer.enabled"
            /></el-form-item>
          </el-form>
          <el-table
            v-if="writer.kind === 'variables'"
            :data="writer.fields"
            max-height="300"
            ><el-table-column
              prop="node_id"
              label="NodeId"
              min-width="220"
            /><el-table-column :label="t('opcua.fieldAlias')" min-width="180"
              ><template #default="{ row }"
                ><el-input
                  v-model="row.alias"
                  maxlength="128" /></template></el-table-column
            ><el-table-column width="80"
              ><template #default="{ $index }"
                ><el-button
                  link
                  type="danger"
                  @click="writer!.fields.splice($index, 1)"
                  >{{ t("opcua.remove") }}</el-button
                ></template
              ></el-table-column
            ></el-table
          >
          <template v-else
            ><el-checkbox-group v-model="writer.event_fields"
              ><el-checkbox
                v-for="field in EVENT_FIELDS"
                :key="field"
                :value="field"
                >{{ field }}</el-checkbox
              ></el-checkbox-group
            >
            <p class="ua-muted">
              {{ t("opcua.eventSources") }}:
              {{ writer.source_nodes.join(", ") || "—" }}
            </p></template
          >
          <p class="ua-muted">{{ t("opcua.datasetDragHint") }}</p>
        </template>
      </el-tab-pane>
    </el-tabs>
    <template #footer
      ><el-button @click="emit('close')">{{ t("opcua.cancel") }}</el-button
      ><el-button type="primary" @click="apply">{{
        t("opcua.applyDraft")
      }}</el-button></template
    >
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  defaultWriter,
  EVENT_FIELDS,
  type UaPublisher,
  type UaWriter,
} from "@/utils/opcuaPubSub";
const props = defineProps<{
  visible: boolean;
  config: UaPublisher;
  initialTab?: "publisher" | "datasets";
  writerId?: number;
}>();
const emit = defineEmits<{ close: []; apply: [config: UaPublisher] }>();
const { t } = useI18n();
const draft = ref<UaPublisher>(JSON.parse(JSON.stringify(props.config))),
  tab = ref("publisher"),
  writerIndex = ref(0);
const writer = computed(() => draft.value.writers[writerIndex.value]);
const messageFlags = [
    "publisher_id",
    "writer_group_name",
    "sequence_number",
    "timestamp",
    "status",
    "metadata_version",
  ],
  fieldFlags = ["status_code", "source_timestamp", "server_timestamp"];
watch(
  () => props.visible,
  (open) => {
    if (open) {
      draft.value = JSON.parse(JSON.stringify(props.config));
      writerIndex.value = Math.max(
        0,
        draft.value.writers.findIndex((w) => w.writer_id === props.writerId),
      );
      tab.value = props.initialTab || "publisher";
    }
  },
);
function addWriter(kind: UaWriter["kind"]) {
  const ids = new Set(draft.value.writers.map((w) => w.writer_id));
  let id = 1;
  while (ids.has(id)) id++;
  draft.value.writers.push(defaultWriter(id, kind));
  writerIndex.value = draft.value.writers.length - 1;
}
function removeWriter() {
  draft.value.writers.splice(writerIndex.value, 1);
  writerIndex.value = Math.max(0, writerIndex.value - 1);
}
function apply() {
  if (
    new Set(draft.value.writers.map((w) => w.writer_id)).size !==
    draft.value.writers.length
  ) {
    ElMessage.warning(t("opcua.duplicateWriter"));
    return;
  }
  emit("apply", JSON.parse(JSON.stringify(draft.value)));
  emit("close");
}
</script>
<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}
.ua-muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
@media (max-width: 600px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
