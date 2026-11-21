<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t(copyTask ? 'copyDevice.progressTitle' : 'copyDevice.title')"
    width="640px"
    :close-on-click-modal="false"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
    @closed="handleClosed"
    class="modern-dialog"
  >
    <el-form
      v-if="!copyTask"
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      label-position="right"
      :disabled="loading"
    >
      <el-tabs
        v-model="copyMode"
        class="device-form-tabs copy-device-tabs"
        @tab-change="handleTabChange"
      >
        <el-tab-pane :label="$t('copyDevice.singleCopy')" name="single">
          <div v-if="copyMode === 'single'">
            <el-form-item
              :label="$t('copyDevice.targetName')"
              prop="targetName"
            >
              <el-input
                v-model="form.targetName"
                :placeholder="$t('copyDevice.targetNamePlaceholder')"
                maxlength="100"
              />
            </el-form-item>

            <el-form-item
              :label="$t('copyDevice.targetCode')"
              prop="targetCode"
            >
              <el-input
                v-model="form.targetCode"
                :placeholder="$t('copyDevice.targetCodePlaceholder')"
                maxlength="100"
              />
            </el-form-item>

            <el-form-item :label="$t('copyDevice.targetIp')" prop="targetIp">
              <el-input
                v-model="form.targetIp"
                :placeholder="$t('copyDevice.targetIpPlaceholder')"
              />
            </el-form-item>

            <el-form-item
              :label="$t('copyDevice.targetPort')"
              prop="targetPort"
            >
              <el-input-number
                v-model="form.targetPort"
                :min="1"
                :max="65535"
                style="width: 100%"
              />
            </el-form-item>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="$t('copyDevice.batchCopy')" name="batch">
          <div v-if="copyMode === 'batch'">
            <el-form-item :label="$t('copyDevice.sourceDevice')">
              <el-input :value="sourceDeviceName" disabled />
            </el-form-item>

            <el-form-item
              :label="$t('copyDevice.targetGroup')"
              prop="targetGroupId"
            >
              <el-tree-select
                v-model="form.targetGroupId"
                :data="groupSelectOptions"
                :props="{ label: 'name', value: 'id', children: 'children' }"
                :placeholder="$t('copyDevice.targetGroupPlaceholder')"
                popper-class="device-group-select-popper"
                check-strictly
                style="width: 100%"
              />
            </el-form-item>

            <el-form-item :label="$t('copyDevice.prefix')">
              <el-input
                v-model="form.prefix"
                :placeholder="$t('copyDevice.prefixPlaceholder')"
              />
            </el-form-item>

            <el-form-item :label="$t('copyDevice.suffix')">
              <el-input
                v-model="form.suffix"
                :placeholder="$t('copyDevice.suffixPlaceholder')"
              />
            </el-form-item>

            <el-form-item :label="$t('copyDevice.copyCount')" prop="count">
              <el-input-number
                v-model="form.count"
                :min="1"
                :max="256"
                style="width: 100%"
              />
            </el-form-item>

            <el-form-item :label="$t('copyDevice.ipStart')" prop="ipStart">
              <el-input
                v-model="form.ipStart"
                :placeholder="$t('copyDevice.targetIpPlaceholder')"
              />
            </el-form-item>

            <el-form-item :label="$t('copyDevice.ipOffsets')">
              <div class="ip-offset-row">
                <div v-for="(_, idx) in 4" :key="idx" class="ip-offset-item">
                  <span class="ip-offset-label">{{
                    $t("copyDevice.offsetSegment", { n: idx + 1 })
                  }}</span>
                  <el-input-number
                    v-model="form.ipOffsets[idx]"
                    :min="0"
                    :max="255"
                    :controls="false"
                    size="small"
                    class="ip-offset-input"
                  />
                </div>
              </div>
              <div class="form-tip">
                {{
                  $t("copyDevice.ipPreview", {
                    ip: previewFirstIp,
                    newIp: getPreviewIp(2),
                  })
                }}
              </div>
            </el-form-item>

            <el-form-item
              :label="$t('copyDevice.portOffset')"
              prop="portOffset"
            >
              <el-input-number
                v-model="form.portOffset"
                :min="0"
                :max="10000"
                style="width: 100%"
              />
              <div class="form-tip">
                {{
                  $t("copyDevice.portPreview", {
                    port: sourcePort,
                    newPort: previewFirstPort,
                  })
                }}
              </div>
            </el-form-item>

            <el-alert
              v-if="sourcePointCount > 0"
              type="info"
              :closable="false"
              show-icon
              style="margin-bottom: 16px"
            >
              <template #title>
                {{ $t("copyDevice.copyPoints", { count: sourcePointCount }) }}
              </template>
            </el-alert>

            <el-alert
              v-if="isIec61850"
              type="success"
              :closable="false"
              show-icon
              style="margin-bottom: 16px"
              :title="$t('copyDevice.iec61850Title')"
            >
              <div>{{ $t("copyDevice.iec61850Scope") }}</div>
              <div v-if="modelLabel" class="iec61850-model">
                {{ $t("copyDevice.iec61850Model", { model: modelLabel }) }}
              </div>
            </el-alert>

            <el-form-item :label="$t('copyDevice.copyPreview')">
              <div class="preview-list">
                <div v-for="i in form.count" :key="i" class="preview-item">
                  <span class="preview-name">{{ getPreviewName(i) }}</span>
                  <span class="preview-ip"
                    >{{ getPreviewIp(i) }}:{{ getPreviewPort(i) }}</span
                  >
                </div>
              </div>
            </el-form-item>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-form>

    <section v-else class="copy-progress-page" aria-live="polite">
      <div class="copy-progress-heading">
        <strong>{{ copyTask.source_name }}</strong>
        <el-tag :type="taskTagType">{{ taskStatusLabel }}</el-tag>
      </div>
      <p class="copy-progress-hint">{{ $t("copyDevice.backgroundHint") }}</p>
      <el-progress
        :percentage="copyTask.progress"
        :status="taskProgressStatus"
        :stroke-width="10"
      />
      <div class="copy-summary">
        <span>{{
          $t("copyDevice.completedCount", {
            completed: copyTask.completed,
            total: copyTask.total,
          })
        }}</span>
        <span>{{
          $t("copyDevice.resultCounts", {
            success: copyTask.copied_count,
            failed: copyTask.failed_count,
            skipped: copyTask.skipped_count,
          })
        }}</span>
      </div>
      <el-alert
        v-if="copyTask.error"
        :title="copyTask.error"
        type="error"
        :closable="false"
        show-icon
      />
      <div class="copy-progress-list">
        <article
          v-for="item in copyTask.items"
          :key="item.index"
          class="copy-progress-item"
        >
          <div class="copy-item-heading">
            <strong>{{ item.index }}. {{ item.name }}</strong>
            <el-tag
              size="small"
              :type="
                item.status === 'failed'
                  ? 'danger'
                  : item.status === 'warning'
                    ? 'warning'
                    : item.status === 'completed'
                      ? 'success'
                      : 'info'
              "
              >{{ $t(`copyDevice.taskStates.${item.status}`) }}</el-tag
            >
          </div>
          <el-progress
            :percentage="item.progress"
            :status="
              item.status === 'failed'
                ? 'exception'
                : item.status === 'warning'
                  ? 'warning'
                  : item.status === 'completed'
                    ? 'success'
                    : undefined
            "
            :stroke-width="6"
          />
          <div class="copy-item-stage">
            {{ $t(`copyDevice.stages.${item.stage}`) }}
            <span v-if="item.points_total > 0 && item.stage === 'points'">
              · {{ item.points_completed }} / {{ item.points_total }}</span
            >
          </div>
          <p v-if="item.message" class="copy-item-message">
            {{ item.message }}
          </p>
        </article>
      </div>
    </section>
    <el-alert
      v-if="progressError"
      class="copy-request-error"
      :title="progressError"
      type="error"
      :closable="false"
      show-icon
    />
    <template #footer>
      <div class="dialog-footer">
        <el-button :disabled="submitting" @click="handleClose" round>{{
          $t(
            copyTask?.status === "running"
              ? "copyDevice.runInBackground"
              : copyTask
                ? "common.close"
                : "common.cancel",
          )
        }}</el-button>
        <el-button
          v-if="
            progressError && (copyTask?.status === 'running' || recoveryNeeded)
          "
          type="primary"
          @click="copyTask ? pollCopyTask() : restoreActiveCopyTask()"
          round
          >{{ $t("copyDevice.resumeProgress") }}</el-button
        >
        <el-button
          v-else-if="copyTask && !loading"
          type="primary"
          @click="resetCopyTask"
          round
          >{{ $t("copyDevice.copyAgain") }}</el-button
        >
        <el-button
          v-else-if="!copyTask"
          type="primary"
          :loading="loading"
          @click="handleSubmit"
          round
          class="submit-btn"
          :icon="Check"
        >
          {{ $t("copyDevice.startCopy") }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance, FormRules } from "element-plus";
import { Check } from "@element-plus/icons-vue";
import {
  startDeviceCopyTask,
  startSingleDeviceCopyTask,
  getDeviceCopyTask,
  getActiveDeviceCopyTask,
  type DeviceCopyTask,
} from "@/api/channelApi";
import { getApiErrorMessage } from "@/api/http";
import type { DeviceGroupTreeNode } from "@/api/deviceGroupApi";

const props = defineProps<{
  visible: boolean;
  channelId: number;
  deviceName: string;
  deviceCode: string;
  deviceIp: string;
  devicePort?: number;
  pointCount?: number;
  protocolType?: number;
  modelName?: string;
  modelPath?: string;
  deviceGroupId?: number | null;
  groupOptions?: DeviceGroupTreeNode[];
}>();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  (e: "success"): void;
  (e: "close"): void;
}>();

const { t } = useI18n();
const formRef = ref<FormInstance>();
const submitting = ref(false);
const recovering = ref(false);
const recoveryNeeded = ref(false);
const copyTask = ref<DeviceCopyTask | null>(null);
const loading = computed(
  () =>
    submitting.value ||
    recovering.value ||
    recoveryNeeded.value ||
    copyTask.value?.status === "running",
);
const progressError = ref("");
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let generation = 0;
let completedTaskId = "";
const taskHasIssues = computed(() =>
  Boolean(
    copyTask.value &&
    (copyTask.value.failed_count ||
      copyTask.value.skipped_count ||
      copyTask.value.warning_count),
  ),
);
const taskTagType = computed(() =>
  copyTask.value?.status === "failed"
    ? "danger"
    : copyTask.value?.status === "running"
      ? "primary"
      : taskHasIssues.value
        ? "warning"
        : "success",
);
const taskProgressStatus = computed(() =>
  copyTask.value?.status === "failed"
    ? "exception"
    : copyTask.value?.status === "running"
      ? undefined
      : taskHasIssues.value
        ? "warning"
        : "success",
);
const taskStatusLabel = computed(() =>
  t(
    copyTask.value?.status === "running"
      ? "copyDevice.taskRunning"
      : copyTask.value?.status === "failed"
        ? "copyDevice.taskFailed"
        : taskHasIssues.value
          ? "copyDevice.taskPartial"
          : "copyDevice.taskFinished",
  ),
);

function applyTask(task: DeviceCopyTask) {
  copyTask.value = task;
  if (task.status !== "running" && completedTaskId !== task.id) {
    completedTaskId = task.id;
    emit("success");
  }
}

async function pollCopyTask(id = copyTask.value?.id, token = generation) {
  if (!id || disposed || token !== generation) return;
  clearTimeout(pollTimer);
  progressError.value = "";
  try {
    const task = await getDeviceCopyTask(id);
    if (disposed || token !== generation) return;
    applyTask(task);
    if (task.status === "running")
      pollTimer = setTimeout(() => void pollCopyTask(id, token), 500);
  } catch (error) {
    if (!disposed && token === generation)
      progressError.value = getApiErrorMessage(
        error,
        t("copyDevice.progressFailed"),
      );
  }
}

async function restoreActiveCopyTask(clearError = true) {
  const token = generation;
  recovering.value = true;
  recoveryNeeded.value = true;
  if (clearError) progressError.value = "";
  try {
    const task = await getActiveDeviceCopyTask();
    if (disposed || token !== generation) return;
    recoveryNeeded.value = false;
    if (task) {
      progressError.value = "";
      applyTask(task);
      void pollCopyTask(task.id, token);
    }
  } catch (error) {
    if (!disposed && token === generation)
      progressError.value = getApiErrorMessage(
        error,
        t("copyDevice.progressFailed"),
      );
  } finally {
    if (token === generation) recovering.value = false;
  }
}

function resetCopyTask() {
  if (loading.value) return;
  ++generation;
  clearTimeout(pollTimer);
  copyTask.value = null;
  progressError.value = "";
  recoveryNeeded.value = false;
}

onBeforeUnmount(() => {
  disposed = true;
  ++generation;
  clearTimeout(pollTimer);
});
const copyMode = ref<"single" | "batch">("single");

const form = reactive({
  targetName: "",
  targetCode: "",
  targetIp: "",
  targetPort: 502,
  prefix: "",
  suffix: "_COPY",
  count: 2,
  targetGroupId: 0,
  ipStart: "",
  ipOffsets: [0, 0, 0, 1],
  portOffset: 0,
});

const isValidIpv4 = (value: string): boolean => {
  const parts = value?.trim().split(".") || [];
  return (
    parts.length === 4 &&
    parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)
  );
};

const rules: FormRules = {
  targetName: [
    {
      required: true,
      message: t("copyDevice.targetNameRequired"),
      trigger: "blur",
    },
  ],
  targetCode: [
    {
      required: true,
      message: t("copyDevice.targetCodeRequired"),
      trigger: "blur",
    },
  ],
  targetIp: [
    {
      required: true,
      message: t("copyDevice.targetIpRequired"),
      trigger: "blur",
    },
    {
      validator: (_rule, value: string, callback) => {
        callback(
          isValidIpv4(value)
            ? undefined
            : new Error(t("copyDevice.targetIpInvalid")),
        );
      },
      trigger: "blur",
    },
  ],
  ipStart: [
    {
      required: true,
      message: t("copyDevice.targetIpRequired"),
      trigger: "blur",
    },
    {
      validator: (_rule, value: string, callback) => {
        callback(
          isValidIpv4(value)
            ? undefined
            : new Error(t("copyDevice.targetIpInvalid")),
        );
      },
      trigger: "blur",
    },
  ],
  targetPort: [
    {
      required: true,
      message: t("copyDevice.targetPortRequired"),
      trigger: "blur",
    },
  ],
  count: [
    { required: true, message: t("copyDevice.countRequired"), trigger: "blur" },
  ],
};

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit("update:visible", val),
});

const sourceDeviceName = computed(() => props.deviceName || "");
const sourcePort = computed(() => props.devicePort || 502);
const sourcePointCount = computed(() => props.pointCount || 0);
const isIec61850 = computed(() => props.protocolType === 4);
const modelLabel = computed(() => {
  if (props.modelName) return props.modelName;
  if (!props.modelPath) return "";
  return props.modelPath.split(/[\\/]/).pop() || props.modelPath;
});
const groupSelectOptions = computed(() => [
  {
    id: 0,
    name: t("copyDevice.ungrouped"),
    children: [],
  },
  ...(props.groupOptions || []),
]);

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      if (copyTask.value) {
        if (copyTask.value.status === "running") void pollCopyTask();
        return;
      }
      void restoreActiveCopyTask();
      form.targetGroupId = props.deviceGroupId || 0;
      form.targetName = `${props.deviceName}_COPY`;
      form.targetCode = `${props.deviceCode}_COPY`;
      form.targetIp = props.deviceIp || "0.0.0.0";
      form.targetPort = props.devicePort || 502;
      // 默认起始IP = 源IP末段+1，避免第一台复制设备与源设备端点冲突
      const startParts = (props.deviceIp || "0.0.0.0").split(".");
      if (startParts.length === 4) {
        const lastOctet = parseInt(startParts[3], 10);
        startParts[3] = String(lastOctet + 1 > 255 ? 0 : lastOctet + 1);
        form.ipStart = startParts.join(".");
      } else {
        form.ipStart = "0.0.0.1";
      }
      form.ipOffsets = [0, 0, 0, 1];
      copyMode.value = "single";
      formRef.value?.clearValidate();
    }
  },
  { immediate: true },
);

const previewFirstIp = computed(() => getPreviewIp(1));
const previewFirstPort = computed(() => getPreviewPort(1));

function getPreviewName(index: number): string {
  return `${form.prefix}${sourceDeviceName.value}${form.suffix}${index}`;
}

function getPreviewIp(index: number): string {
  const startParts = form.ipStart.split(".").map((p) => parseInt(p, 10));
  if (startParts.length !== 4) return form.ipStart;
  const values = startParts.map(
    (seg, k) => seg + form.ipOffsets[k] * (index - 1),
  );
  // 256 进制进位：第4段溢出向第3段进位，依此类推
  for (let k = 3; k > 0; k--) {
    if (values[k] > 255) {
      values[k - 1] += Math.floor(values[k] / 256);
      values[k] %= 256;
    }
  }
  if (values[0] > 255) {
    return t("copyDevice.ipOutOfRange");
  }
  return values.join(".");
}

function getPreviewPort(index: number): number {
  if (form.portOffset === 0) {
    return sourcePort.value;
  }
  return sourcePort.value + form.portOffset * index;
}

const handleSubmit = async () => {
  if (!formRef.value || loading.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    submitting.value = true;
    progressError.value = "";
    try {
      const result =
        copyMode.value === "single"
          ? await startSingleDeviceCopyTask({
              channel_id: props.channelId,
              target_name: form.targetName.trim(),
              target_code: form.targetCode.trim(),
              target_ip: form.targetIp.trim(),
              target_port: form.targetPort,
            })
          : await startDeviceCopyTask({
              channel_id: props.channelId,
              count: form.count,
              prefix: form.prefix,
              suffix: form.suffix,
              ip_start: form.ipStart.trim(),
              ip_offsets: form.ipOffsets,
              port_offset: form.portOffset,
              target_group_id:
                form.targetGroupId === 0 ? null : form.targetGroupId,
            });
      if (!disposed) {
        applyTask(result);
        void pollCopyTask();
      }
    } catch (error) {
      progressError.value = getApiErrorMessage(
        error,
        t("copyDevice.taskStartFailed"),
      );
      await restoreActiveCopyTask(false);
    } finally {
      submitting.value = false;
    }
  });
};

const handleTabChange = () => {
  formRef.value?.clearValidate();
};

const handleClose = () => {
  if (submitting.value) return;
  dialogVisible.value = false;
};

const handleClosed = () => {
  if (copyTask.value?.status !== "running") resetCopyTask();
  emit("close");
};
</script>

<style lang="scss" scoped>
.copy-progress-heading,
.copy-item-heading,
.copy-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: var(--text-primary);
}
.copy-progress-heading strong,
.copy-item-heading strong {
  min-width: 0;
  overflow-wrap: anywhere;
}
.copy-item-heading .el-tag {
  flex-shrink: 0;
}
.copy-progress-hint,
.copy-summary,
.copy-item-stage,
.copy-item-message {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.copy-progress-hint {
  margin: 12px 0 18px;
}
.copy-summary {
  flex-wrap: wrap;
  margin: 12px 0;
}
.copy-progress-list {
  max-height: 380px;
  overflow-y: auto;
  margin-top: 16px;
}
.copy-progress-item {
  padding: 14px 0;
  border-bottom: 1px solid var(--sidebar-border);
}
.copy-item-heading {
  margin-bottom: 10px;
  font-size: 13px;
}
.copy-item-stage {
  margin-top: 6px;
}
.copy-item-message {
  margin: 4px 0 0;
  color: var(--el-color-warning);
  overflow-wrap: anywhere;
}
.copy-request-error {
  margin-top: 12px;
}
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}

.ip-offset-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.ip-offset-item {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.ip-offset-input {
  flex: 1;
  min-width: 0;
}

.ip-offset-label {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}

.iec61850-model {
  margin-top: 4px;
  font-family: monospace;
  overflow-wrap: anywhere;
}

.preview-list {
  background: var(--bg-subtle);
  border-radius: 8px;
  padding: 12px;
  max-height: 200px;
  overflow-y: auto;
  width: 100%;
}

.preview-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-color);

  &:last-child {
    border-bottom: none;
  }
}

.preview-name {
  font-size: 13px;
  color: #303133;
}

.preview-ip {
  font-size: 13px;
  color: #409eff;
  font-family: monospace;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.submit-btn {
  min-width: 100px;
}
</style>

<style lang="scss">
.modern-dialog {
  border-radius: 16px;
  overflow: hidden;

  .el-dialog__header {
    padding: 20px 24px 16px;
    border-bottom: 1px solid var(--border-color);
    margin-right: 0;

    .el-dialog__title {
      font-size: 18px;
      font-weight: 600;
      color: #303133;
    }
  }

  .el-dialog__body {
    padding: 10px 24px 24px;
  }

  .el-dialog__footer {
    padding: 16px 24px 20px;
    border-top: 1px solid var(--border-color);
  }

  .copy-device-tabs {
    min-height: 0;
  }
}
</style>
