<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t('copyDevice.title')"
    width="480px"
    :close-on-click-modal="false"
    @close="handleClose"
    class="modern-dialog"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      label-position="right"
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
                :max="100"
                style="width: 100%"
              />
            </el-form-item>

            <el-form-item :label="$t('copyDevice.ipStart')" prop="ipStart">
              <div class="ip-segment-input">
                <template v-for="(_, idx) in 4" :key="idx">
                  <el-input-number
                    v-model="form.ipStartSegments[idx]"
                    :min="0"
                    :max="255"
                    :controls="false"
                    class="ip-segment"
                  />
                  <span v-if="idx < 3" class="ip-dot">.</span>
                </template>
              </div>
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
                <div
                  v-for="i in Math.min(form.count, 5)"
                  :key="i"
                  class="preview-item"
                >
                  <span class="preview-name">{{ getPreviewName(i) }}</span>
                  <span class="preview-ip"
                    >{{ getPreviewIp(i) }}:{{ getPreviewPort(i) }}</span
                  >
                </div>
                <div v-if="form.count > 5" class="preview-more">
                  {{ $t("copyDevice.moreDevices", { count: form.count - 5 }) }}
                </div>
              </div>
            </el-form-item>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose" round>{{
          $t("common.cancel")
        }}</el-button>
        <el-button
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
import { ref, computed, reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { Check } from "@element-plus/icons-vue";
import { copyDevice, copySingleDevice } from "@/api/channelApi";
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
const loading = ref(false);
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
  ipStartSegments: [0, 0, 0, 0],
  ipOffsets: [0, 0, 0, 1],
  portOffset: 0,
});

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
        const parts = value?.trim().split(".") || [];
        const valid =
          parts.length === 4 &&
          parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255);
        callback(
          valid ? undefined : new Error(t("copyDevice.targetIpInvalid")),
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
      form.targetGroupId = props.deviceGroupId || 0;
      form.targetName = `${props.deviceName}_COPY`;
      form.targetCode = `${props.deviceCode}_COPY`;
      form.targetIp = props.deviceIp || "0.0.0.0";
      form.targetPort = props.devicePort || 502;
      // 默认起始IP = 源IP末段+1，避免第一台复制设备与源设备端点冲突
      const startParts = (props.deviceIp || "0.0.0.0")
        .split(".")
        .map((p) => parseInt(p, 10));
      if (startParts.length === 4) {
        startParts[3] = startParts[3] + 1 > 255 ? 0 : startParts[3] + 1;
        form.ipStartSegments = startParts;
      } else {
        form.ipStartSegments = [0, 0, 0, 1];
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
  const values = form.ipStartSegments.map(
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
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    loading.value = true;
    try {
      const result =
        copyMode.value === "single"
          ? await copySingleDevice({
              channel_id: props.channelId,
              target_name: form.targetName.trim(),
              target_code: form.targetCode.trim(),
              target_ip: form.targetIp.trim(),
              target_port: form.targetPort,
            })
          : await copyDevice({
              channel_id: props.channelId,
              count: form.count,
              prefix: form.prefix,
              suffix: form.suffix,
              ip_start: form.ipStartSegments.join("."),
              ip_offsets: form.ipOffsets,
              port_offset: form.portOffset,
              target_group_id:
                form.targetGroupId === 0 ? null : form.targetGroupId,
            });
      ElMessage.success(
        t("copyDevice.copySuccess", { count: result.copied_count }),
      );
      emit("success");
      dialogVisible.value = false;
      window.location.reload();
    } catch (e: any) {
      console.error(e.message || "复制失败");
    } finally {
      loading.value = false;
    }
  });
};

const handleTabChange = () => {
  formRef.value?.clearValidate();
};

const handleClose = () => {
  dialogVisible.value = false;
  emit("close");
};
</script>

<style lang="scss" scoped>
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}

.ip-segment-input {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;

  .ip-segment {
    flex: 1;
  }

  .ip-dot {
    color: #909399;
    font-weight: 600;
  }
}

.ip-offset-row {
  display: flex;
  gap: 6px;
  width: 100%;
}

.ip-offset-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  flex: 1;
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

.preview-more {
  text-align: center;
  color: #909399;
  font-size: 12px;
  padding-top: 8px;
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
