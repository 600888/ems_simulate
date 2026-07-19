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
      <el-form-item :label="$t('copyDevice.sourceDevice')">
        <el-input :value="sourceDeviceName" disabled />
      </el-form-item>

      <el-form-item :label="$t('copyDevice.targetGroup')" prop="targetGroupId">
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

      <el-form-item :label="$t('copyDevice.ipOffset')" prop="ipStartOffset">
        <el-input-number
          v-model="form.ipStartOffset"
          :min="0"
          :max="254"
          style="width: 100%"
        />
        <div class="form-tip">
          {{
            $t("copyDevice.ipPreview", { ip: sourceIp, newIp: previewFirstIp })
          }}
        </div>
      </el-form-item>

      <el-form-item :label="$t('copyDevice.portOffset')" prop="portOffset">
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
import { copyDevice } from "@/api/channelApi";
import type { DeviceGroupTreeNode } from "@/api/deviceGroupApi";

const props = defineProps<{
  visible: boolean;
  channelId: number;
  deviceName: string;
  deviceIp: string;
  devicePort?: number;
  pointCount?: number;
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

const form = reactive({
  prefix: "",
  suffix: "_COPY",
  count: 2,
  targetGroupId: 0,
  ipStartOffset: 1,
  portOffset: 0,
});

const rules: FormRules = {
  count: [
    { required: true, message: t("copyDevice.countRequired"), trigger: "blur" },
  ],
};

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit("update:visible", val),
});

const sourceDeviceName = computed(() => props.deviceName || "");
const sourceIp = computed(() => props.deviceIp || "0.0.0.0");
const sourcePort = computed(() => props.devicePort || 502);
const sourcePointCount = computed(() => props.pointCount || 0);
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
  if (form.ipStartOffset === 0) {
    return sourceIp.value;
  }
  try {
    const parts = sourceIp.value.split(".");
    if (parts.length !== 4) return sourceIp.value;
    const lastOctet = parseInt(parts[3], 10);
    const newOctet = lastOctet + form.ipStartOffset + index - 1;
    parts[3] = String(newOctet > 255 ? newOctet - 256 : newOctet);
    return parts.join(".");
  } catch {
    return sourceIp.value;
  }
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
      const result = await copyDevice({
        channel_id: props.channelId,
        count: form.count,
        prefix: form.prefix,
        suffix: form.suffix,
        ip_start_offset: form.ipStartOffset,
        port_offset: form.portOffset,
        target_group_id: form.targetGroupId === 0 ? null : form.targetGroupId,
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

.preview-list {
  background: #f5f7fa;
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
  border-bottom: 1px solid #ebeef5;

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
    border-bottom: 1px solid #ebeef5;
    margin-right: 0;

    .el-dialog__title {
      font-size: 18px;
      font-weight: 600;
      color: #303133;
    }
  }

  .el-dialog__body {
    padding: 24px;
  }

  .el-dialog__footer {
    padding: 16px 24px 20px;
    border-top: 1px solid #ebeef5;
  }
}
</style>
