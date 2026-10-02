<template>
  <div>
    <OpcUaPageHeading
      :title="t('opcua.objectsAndValues')"
      :description="t('opcua.objectsDescription')"
    >
      <el-radio-group v-model="view">
        <el-radio-button value="values">{{
          t("opcua.objectsAndValues")
        }}</el-radio-button>
        <el-radio-button value="definitions">{{
          t("opcua.modelDefinitions")
        }}</el-radio-button>
      </el-radio-group>
    </OpcUaPageHeading>
    <OpcUaObjectsValues
      v-if="view === 'values'"
      :channel-id="channelId"
      :running="running"
      :active="active"
      :revision="revision"
      :variables="nodes"
      @configure="emit('configure', $event)"
    />
    <template v-else>
      <div class="toolbar">
        <el-input
          v-model="search"
          :placeholder="t('opcua.nodeSearch')"
          clearable
          @input="page = 1"
        />
        <el-button @click="loadNodes">{{ t("opcua.refresh") }}</el-button>
        <el-button
          type="primary"
          :disabled="saving || importing"
          @click="editVariable()"
          >{{ t("opcua.addVariable") }}</el-button
        >
        <el-button :disabled="saving || importing" @click="xmlInput?.click()">{{
          t("opcua.importModel")
        }}</el-button>
        <el-button :disabled="!running || !nodes.length" @click="resetValues">{{
          t("opcua.resetValues")
        }}</el-button>
        <el-button
          :disabled="!running"
          :loading="exporting"
          @click="exportModel"
          >{{ t("opcua.exportModel") }}</el-button
        >
        <input
          ref="xmlInput"
          type="file"
          accept=".xml"
          hidden
          @change="selectModel"
        />
      </div>
      <el-alert
        class="hint"
        type="info"
        :closable="false"
        :title="t('opcua.modelHint')"
      />
      <el-table
        v-loading="loading"
        :data="visibleNodes"
        stripe
        row-key="node_id"
        max-height="520"
      >
        <el-table-column
          prop="node_id"
          label="NodeId"
          min-width="230"
          show-overflow-tooltip
        />
        <el-table-column
          prop="browse_name"
          label="BrowseName"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="data_type"
          :label="t('opcua.type')"
          width="100"
        />
        <el-table-column
          prop="initial_value"
          :label="t('opcua.initialValue')"
          width="100"
          show-overflow-tooltip
        />
        <el-table-column :label="t('opcua.access')" width="120">
          <template #default="{ row }">{{
            t(row.writable ? "opcua.readWrite" : "opcua.readOnly")
          }}</template>
        </el-table-column>
        <el-table-column
          prop="point_code"
          :label="t('opcua.pointOwner')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column :label="t('opcua.actions')" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              :disabled="!!row.point_code || saving || importing"
              @click="editVariable(row)"
              >{{ t("opcua.edit") }}</el-button
            >
            <el-button
              link
              type="danger"
              :disabled="!!row.point_code || saving || importing"
              @click="removeVariable(row)"
              >{{ t("opcua.delete") }}</el-button
            >
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="filteredNodes.length"
        :page-size="50"
        v-model:current-page="page"
      />
    </template>

    <el-dialog
      v-model="variableVisible"
      :title="t(editing ? 'opcua.editVariable' : 'opcua.addVariable')"
      width="min(560px, calc(100vw - 32px))"
    >
      <el-form label-position="top">
        <el-form-item label="NodeId"
          ><el-input
            v-model="variable.node_id"
            :disabled="editing"
            placeholder="ns=2;s=..."
        /></el-form-item>
        <el-form-item label="BrowseName"
          ><el-input v-model="variable.browse_name"
        /></el-form-item>
        <el-form-item :label="t('opcua.dataType')">
          <el-select
            v-model="variable.data_type"
            :disabled="running && editing"
            class="variable-type"
          >
            <el-option
              v-for="type in scalarTypes"
              :key="type"
              :label="type"
              :value="type"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('opcua.initialValue')"
          ><el-input v-model="valueText"
        /></el-form-item>
        <el-form-item :label="t('opcua.remoteWrite')"
          ><el-switch v-model="variable.writable"
        /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="variableVisible = false">{{
          t("opcua.cancel")
        }}</el-button>
        <el-button
          type="primary"
          :loading="saving"
          :disabled="saving || importing"
          @click="saveVariable"
          >{{ t("opcua.save") }}</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="modelVisible"
      :title="t('opcua.modelPreview')"
      width="min(760px, calc(100vw - 32px))"
    >
      <template v-if="modelPreview">
        <p class="model-summary">
          {{ modelFile?.name }}；{{
            t("opcua.modelCounts", {
              total: modelPreview.total,
              namespaceUri: modelPreview.namespace_uri,
            })
          }}
        </p>
        <el-table
          v-if="modelPreview.errors.length || modelPreview.conflicts.length"
          :data="[...modelPreview.errors, ...modelPreview.conflicts]"
          max-height="280"
        >
          <el-table-column prop="node_id" label="NodeId" min-width="240" />
          <el-table-column
            prop="message"
            :label="t('opcua.issue')"
            min-width="260"
          />
        </el-table>
        <el-alert
          v-else
          type="success"
          :closable="false"
          :title="t('opcua.previewPassed')"
        />
        <div class="import-mode">
          <span>{{ t("opcua.conflictPolicy") }}</span>
          <el-radio-group v-model="modelMode">
            <el-radio value="add">{{ t("opcua.addOnly") }}</el-radio>
            <el-radio value="overwrite">{{
              t("opcua.overwriteVariables")
            }}</el-radio>
          </el-radio-group>
        </div>
      </template>
      <template #footer>
        <el-button @click="modelVisible = false">{{
          t("opcua.cancel")
        }}</el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="
            importing ||
            saving ||
            !modelPreview ||
            !!modelPreview.errors.length ||
            (modelMode === 'add' && !!modelPreview.conflicts.length)
          "
          @click="importModel"
          >{{ t("opcua.confirmImport") }}</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import OpcUaObjectsValues from "./OpcUaObjectsValues.vue";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { showError } from "@/api/http";
import {
  applyOpcUaModel,
  deleteOpcUaVariable,
  exportOpcUaModel,
  listOpcUaVariables,
  previewOpcUaModel,
  resetOpcUaVariables,
  saveOpcUaVariable,
} from "@/api/opcuaApi";
import type { OpcUaModelPreview, OpcUaVariable } from "@/api/opcuaApi";
import {
  OPCUA_SCALAR_TYPES,
  OpcUaScalarError,
  parseOpcUaScalar,
} from "@/utils/opcuaValue";

const props = withDefaults(
  defineProps<{
    channelId: number;
    running: boolean;
    revision: number;
    active?: boolean;
  }>(),
  { active: true },
);
const { t } = useI18n();
const emit = defineEmits<{ changed: []; configure: [nodeId: string] }>();
const view = ref("values");
const scalarTypes = OPCUA_SCALAR_TYPES;
const nodes = ref<OpcUaVariable[]>([]);
const loading = ref(false);
const search = ref("");
const page = ref(1);
const filteredNodes = computed(() => {
  const query = search.value.toLowerCase();
  return nodes.value.filter(
    (node) =>
      node.node_id.toLowerCase().includes(query) ||
      node.browse_name.toLowerCase().includes(query),
  );
});
const visibleNodes = computed(() =>
  filteredNodes.value.slice((page.value - 1) * 50, page.value * 50),
);
const variableVisible = ref(false);
const editing = ref(false);
const saving = ref(false);
const variable = ref<OpcUaVariable>({
  node_id: "ns=2;s=",
  browse_name: "",
  data_type: "Double",
  initial_value: 0,
  writable: false,
});
const valueText = ref("0");
const xmlInput = ref<HTMLInputElement | null>(null);
const modelFile = ref<File | null>(null);
const modelPreview = ref<OpcUaModelPreview | null>(null);
const modelVisible = ref(false);
const modelMode = ref<"add" | "overwrite">("add");
const importing = ref(false);
const exporting = ref(false);

async function resetValues() {
  try {
    await ElMessageBox.confirm(
      t("opcua.resetValuesConfirm"),
      t("opcua.resetValues"),
      { type: "warning" },
    );
    const result = await resetOpcUaVariables(props.channelId);
    ElMessage.success(t("opcua.valuesReset", result));
    emit("changed");
  } catch (error) {
    if (error !== "cancel" && error !== "close") showError(error);
  }
}

async function loadNodes() {
  loading.value = true;
  try {
    nodes.value = (await listOpcUaVariables(props.channelId)).nodes;
  } catch (error) {
    showError(error);
  } finally {
    loading.value = false;
  }
}

function editVariable(node?: OpcUaVariable) {
  editing.value = !!node;
  variable.value = node
    ? { ...node }
    : {
        node_id: "ns=2;s=",
        browse_name: "",
        data_type: "Double",
        initial_value: 0,
        writable: false,
      };
  const initial = variable.value.initial_value;
  valueText.value =
    typeof initial === "object" && initial !== null
      ? String(
          (initial as { integer?: string; base64?: string }).integer ??
            (initial as { base64?: string }).base64 ??
            "",
        )
      : String(initial);
  variableVisible.value = true;
}

async function saveVariable() {
  saving.value = true;
  try {
    const payload = {
      ...variable.value,
      initial_value: parseOpcUaScalar(
        valueText.value,
        variable.value.data_type,
      ),
    };
    await saveOpcUaVariable(props.channelId, payload);
    variableVisible.value = false;
    await loadNodes();
    emit("changed");
    ElMessage.success(t("opcua.variableSaved"));
  } catch (error) {
    if (error instanceof OpcUaScalarError)
      showError(
        t(error.type === "Boolean" ? "opcua.badBoolean" : "opcua.badNumber", {
          type: error.type,
        }),
      );
    else showError(error);
  } finally {
    saving.value = false;
  }
}

async function removeVariable(node: OpcUaVariable) {
  try {
    await ElMessageBox.confirm(
      t("opcua.deleteVariableConfirm", { nodeId: node.node_id }),
      t("opcua.confirmDelete"),
      { type: "warning" },
    );
    await deleteOpcUaVariable(props.channelId, node.node_id);
    await loadNodes();
    emit("changed");
  } catch (error) {
    if (error !== "cancel" && error !== "close") showError(error);
  }
}

async function selectModel(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  modelFile.value = file;
  modelPreview.value = null;
  try {
    modelPreview.value = await previewOpcUaModel(props.channelId, file);
    modelMode.value = "add";
    modelVisible.value = true;
  } catch (error) {
    showError(error);
  }
}

async function importModel() {
  if (!modelFile.value || !modelPreview.value) return;
  importing.value = true;
  try {
    const result = await applyOpcUaModel(
      props.channelId,
      modelFile.value,
      modelPreview.value.sha256,
      modelMode.value,
    );
    modelVisible.value = false;
    await loadNodes();
    emit("changed");
    ElMessage.success(t("opcua.modelImported", result));
  } catch (error) {
    showError(error);
  } finally {
    importing.value = false;
  }
}

async function exportModel() {
  exporting.value = true;
  try {
    const blob = await exportOpcUaModel(props.channelId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `opcua-channel-${props.channelId}.xml`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    showError(error);
  } finally {
    exporting.value = false;
  }
}

watch(
  () => [props.channelId, props.revision],
  () => {
    page.value = 1;
    void loadNodes();
  },
);
onMounted(() => {
  void loadNodes();
});
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.toolbar > .el-input {
  flex: 1 1 240px;
  min-width: 0;
  max-width: 300px;
}
.toolbar > .el-button {
  flex-shrink: 0;
}
.hint {
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: safe flex-end;
}
.import-mode {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.import-mode :deep(.el-radio-group) {
  flex-wrap: wrap;
  gap: 8px 18px;
}
.import-mode :deep(.el-radio) {
  margin-right: 0;
  height: auto;
  min-height: 32px;
}
.model-summary {
  overflow-wrap: anywhere;
}
.variable-type {
  width: 100%;
}
</style>
