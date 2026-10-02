<template>
  <el-dialog
    v-model="visible"
    :title="t('opcua.pointsPreview')"
    width="min(780px, calc(100vw - 32px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!importing"
    :show-close="!importing"
    append-to-body
    @close="finish(false)"
  >
    <div v-loading="loading" class="import-preview">
      <p>{{ t("opcua.file") }}: {{ file?.name }}</p>
      <el-alert
        v-if="previewError"
        type="error"
        :closable="false"
        :title="previewError"
      />
      <template v-if="preview">
        <p>
          {{
            t("opcua.importCounts", {
              total: preview.total,
              telemetry: preview.counts["遥测"],
              signal: preview.counts["遥信"],
              control: preview.counts["遥控"],
              adjustment: preview.counts["遥调"],
            })
          }}
        </p>
        <el-alert
          v-if="preview.role === 'client'"
          type="info"
          :closable="false"
          :title="t('opcua.clientPointsHint')"
        />
        <el-table
          v-if="preview.errors.length || preview.conflicts.length"
          :data="[...preview.errors, ...preview.conflicts]"
          max-height="280"
          size="small"
        >
          <el-table-column prop="sheet" label="Sheet" width="90" />
          <el-table-column prop="row" :label="t('opcua.row')" width="60" />
          <el-table-column prop="field" :label="t('opcua.field')" width="140" />
          <el-table-column :label="t('opcua.issue')" min-width="240">
            <template #default="{ row }">{{
              row.message || t("opcua.conflict", { value: row.value })
            }}</template>
          </el-table-column>
        </el-table>
        <el-alert
          v-else
          :type="preview.total ? 'success' : 'warning'"
          :closable="false"
          :title="
            t(preview.total ? 'opcua.previewPassed' : 'opcua.emptyPoints')
          "
        />
        <div class="import-mode">
          <span>{{ t("opcua.conflictPolicy") }}</span>
          <el-radio-group v-model="mode" :disabled="importing">
            <el-radio value="add">{{ t("opcua.addOnly") }}</el-radio>
            <el-radio value="overwrite">{{
              t("opcua.overwritePoints")
            }}</el-radio>
          </el-radio-group>
        </div>
      </template>
    </div>
    <template #footer>
      <div class="import-actions">
        <el-button :disabled="importing" @click="finish(false)">{{
          t("opcua.cancel")
        }}</el-button>
        <el-button :disabled="loading || importing" @click="loadPreview">{{
          t("opcua.refreshPreview")
        }}</el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="!canImport || disabled"
          @click="applyImport"
          >{{ t("opcua.confirmImport") }}</el-button
        >
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, shallowRef } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { getApiErrorMessage, showError } from "@/api/http";
import {
  applyOpcUaPoints,
  previewOpcUaPoints,
  type OpcUaImportPreview,
} from "@/api/opcuaApi";

defineProps<{ disabled?: boolean }>();
const { t } = useI18n();
const visible = ref(false);
const loading = ref(false);
const importing = ref(false);
const file = shallowRef<File | null>(null);
const preview = ref<OpcUaImportPreview | null>(null);
const previewError = ref("");
const mode = ref<"add" | "overwrite">("add");
let channelId = 0;
let requestId = 0;
let complete: ((imported: boolean) => void) | null = null;
const canImport = computed(
  () =>
    !loading.value &&
    !importing.value &&
    preview.value &&
    preview.value.total > 0 &&
    !preview.value.errors.length &&
    (mode.value === "overwrite" || !preview.value.conflicts.length),
);

function finish(imported: boolean) {
  const resolve = complete;
  complete = null;
  requestId++;
  visible.value = false;
  resolve?.(imported);
}

function open(id: number, selectedFile: File): Promise<boolean> {
  finish(false);
  channelId = id;
  file.value = selectedFile;
  preview.value = null;
  previewError.value = "";
  mode.value = "add";
  visible.value = true;
  const result = new Promise<boolean>((resolve) => {
    complete = resolve;
  });
  void loadPreview();
  return result;
}

async function loadPreview() {
  if (!file.value) return;
  const token = ++requestId;
  loading.value = true;
  preview.value = null;
  previewError.value = "";
  try {
    const result = await previewOpcUaPoints(channelId, file.value);
    if (token === requestId) preview.value = result;
  } catch (error) {
    if (token === requestId) {
      previewError.value = getApiErrorMessage(error);
      showError(error);
    }
  } finally {
    if (token === requestId) loading.value = false;
  }
}

async function applyImport() {
  if (!file.value || !preview.value || !canImport.value) return;
  importing.value = true;
  try {
    const result = await applyOpcUaPoints(
      channelId,
      file.value,
      preview.value.sha256,
      mode.value,
    );
    ElMessage.success(t("opcua.imported", result));
    finish(true);
  } catch (error) {
    showError(error);
  } finally {
    importing.value = false;
  }
}

onUnmounted(() => finish(false));
defineExpose({ open });
</script>

<style scoped>
.import-preview {
  min-width: 0;
}
.import-preview p {
  margin: 0 0 14px;
  overflow-wrap: anywhere;
}
.import-preview :deep(.el-alert) {
  margin-bottom: 14px;
}
.import-mode {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 16px;
}
.import-mode :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.import-mode :deep(.el-radio) {
  height: auto;
  min-height: 24px;
  margin-right: 0;
  white-space: normal;
}
.import-mode :deep(.el-radio__label) {
  line-height: 20px;
}
.import-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
.import-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
