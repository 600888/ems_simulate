<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEditMode ? $t('addDevice.titleEdit') : $t('addDevice.titleAdd')"
    width="760px"
    :close-on-click-modal="false"
    @close="handleClose"
    class="device-form-dialog"
  >
    <el-form
      ref="formRef"
      v-loading="loadingChannel"
      :model="form"
      :rules="rules"
      label-width="110px"
      label-position="right"
    >
      <el-tabs v-model="activeTab" class="device-form-tabs">
        <el-tab-pane :label="$t('addDevice.tabBasic')" name="basic">
          <DeviceFormBasic
            :model-value="form"
            :group-options="deviceGroupOptions"
          />

          <DeviceFormConfig
            :model-value="form"
            v-model:media-type="mediaType"
            :protocols="protocols"
            :serial-ports="serialPorts"
            :hydrating="loadingChannel"
          />

          <DeviceFormPoints
            ref="uploadCompRef"
            :protocol-type="form.protocol_type"
            :conn-type="form.conn_type"
            :disabled="saving"
            :is-edit-mode="isEditMode"
            :point-mode="dlt645PointMode"
            @file-change="(f) => (selectedFile = f)"
            @icd-file-change="handleIcdFileChange"
            @point-mode-change="(mode) => (dlt645PointMode = mode)"
          />
        </el-tab-pane>

        <el-tab-pane :label="$t('addDevice.tabProtocol')" name="protocol">
          <DeviceProtocolParams
            ref="protocolParamsCompRef"
            :model-value="protocolParams"
            :protocol-type="form.protocol_type"
            :conn-type="form.conn_type"
          />
        </el-tab-pane>

        <el-tab-pane
          v-if="tlsSupportedProtocol"
          :label="$t('addDevice.tabSecurity')"
          name="security"
        >
          <DeviceSecurityConfig
            ref="securityCompRef"
            :model-value="securityConfig"
            :network-mode="mediaType === 'network'"
            :protocol-type="form.protocol_type"
            :conn-type="form.conn_type"
            :disabled="saving || loadingChannel"
            @certificate-change="(file) => (certificateFile = file)"
            @private-key-change="(file) => (privateKeyFile = file)"
            @ca-certificate-change="(file) => (caCertificateFile = file)"
          />
        </el-tab-pane>
      </el-tabs>

      <!-- 操作进度条 -->
      <div v-if="saving" class="icd-import-progress">
        <el-progress
          :percentage="100"
          :indeterminate="true"
          :duration="3"
          :stroke-width="4"
          :format="() => ''"
        />
        <p class="icd-import-hint">{{ progressText }} ({{ importElapsed }}s)</p>
      </div>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button
          v-if="isIec61850Server && icdFile && !saving"
          type="warning"
          plain
          :icon="View"
          :loading="previewLoading"
          @click="handlePreviewIcd"
        >
          {{ $t("addDevice.previewIcd") }}
        </el-button>
        <el-button
          :disabled="saving || loadingChannel"
          @click="handleClose"
          round
          >{{ $t("common.cancel") }}</el-button
        >
        <el-button
          type="primary"
          :disabled="saving || loadingChannel"
          @click="handleSubmit"
          round
          class="submit-btn"
          :icon="Check"
        >
          {{
            isEditMode
              ? $t("addDevice.saveChanges")
              : $t("addDevice.confirmAdd")
          }}
        </el-button>
      </div>
    </template>
  </el-dialog>

  <!-- GOOSE 预览对话框 -->
  <el-dialog
    v-model="goosePreviewVisible"
    :title="$t('addDevice.icdPreview')"
    width="90%"
    style="max-width: 1100px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <el-alert
      :title="
        $t('addDevice.mmsPoints', {
          total: goosePreviewData?.total || 0,
          yc: goosePreviewData?.yc_count || 0,
          yx: goosePreviewData?.yx_count || 0,
          yk: goosePreviewData?.yk_count || 0,
          yt: goosePreviewData?.yt_count || 0,
        })
      "
      type="success"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <div v-if="gooseControlList.length > 0">
      <el-alert
        :title="
          $t('addDevice.gooseControlBlocks', { count: gooseControlList.length })
        "
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />

      <el-table :data="gooseControlList" border size="small" max-height="350">
        <el-table-column
          prop="go_cb_ref"
          label="GoCBRef"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column
          prop="go_id"
          :label="$t('addDevice.gooseGoId')"
          width="180"
        />
        <el-table-column prop="app_id" label="APPID" width="70" />
        <el-table-column
          prop="dat_set"
          label="DataSet"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column prop="conf_rev" label="ConfRev" width="70" />
        <el-table-column :label="$t('addDevice.macAddress')" width="140">
          <template #default="{ row }">{{ formatMac(row) }}</template>
        </el-table-column>
        <el-table-column
          :label="$t('addDevice.datasetMembers')"
          width="90"
          align="center"
        >
          <template #default="{ row }">{{ row.dataset_member_count }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else-if="previewDone">
      <el-alert
        :title="$t('addDevice.noGooseControl')"
        type="warning"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <el-button type="primary" @click="goosePreviewVisible = false">
        {{ $t("addDevice.close") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch, onMounted, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { Check, View } from "@element-plus/icons-vue";

// 子组件
import DeviceFormBasic from "./DeviceFormBasic.vue";
import DeviceFormConfig from "./DeviceFormConfig.vue";
import DeviceFormPoints from "./DeviceFormPoints.vue";
import DeviceProtocolParams from "./DeviceProtocolParams.vue";
import DeviceSecurityConfig from "./DeviceSecurityConfig.vue";

// API
import {
  createChannel,
  importPoints,
  importDlt645StandardPoints,
  getChannel,
  updateChannel,
  getSerialPorts,
  getProtocolConfig,
  uploadChannelSecurity,
} from "@/api/channelApi";
import { getAllDeviceGroups, type DeviceGroupInfo } from "@/api/deviceGroupApi";
import type {
  ChannelCreateRequest,
  ProtocolOption,
  PointImportResult,
  SecurityConfig,
} from "@/types/channel";
import {
  normalizeDlt645PointMode,
  shouldImportDlt645Standard,
  type Dlt645PointMode,
} from "@/utils/dlt645PointMode";
import {
  getTlsMaterialRequirements,
  shouldSaveChannelSecurity,
} from "@/utils/channelEdit";
import {
  isSerialConnectionType,
  TLS_SUPPORTED_PROTOCOLS,
} from "@/constants/protocol";

const props = defineProps<{
  visible: boolean;
  channelId?: number | null;
  initialGroupId?: number | null;
}>();

const { t } = useI18n();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  (e: "success", deviceName: string, isEdit?: boolean, oldName?: string): void;
  (e: "close"): void;
}>();

// 状态
const formRef = ref<FormInstance>();
const uploadCompRef = ref();
const protocolParamsCompRef = ref<{
  resetDefaults: () => void;
  validate: () => boolean;
}>();
const securityCompRef = ref();
const activeTab = ref<"basic" | "protocol" | "security">("basic");
const originalName = ref("");
const mediaType = ref<"serial" | "network">("network");
const selectedFile = ref<File | null>(null);
const dlt645PointMode = ref<Dlt645PointMode>("standard");
const originalDlt645PointMode = ref<Dlt645PointMode>("standard");
const icdFile = ref<File | null>(null);
const certificateFile = ref<File | null>(null);
const privateKeyFile = ref<File | null>(null);
const caCertificateFile = ref<File | null>(null);
const deviceGroupOptions = ref<DeviceGroupInfo[]>([]);
const serialPorts = ref<Array<{ device: string; description: string }>>([]);
const protocols = ref<ProtocolOption[]>([]);
const protocolParams = reactive({
  schema_version: 1,
  values: {} as Record<string, number | boolean | string>,
});
const securityConfig = reactive<SecurityConfig>({
  tls_enabled: false,
  tls_mode: "one_way",
  certificate_configured: false,
  certificate_filename: null,
  private_key_configured: false,
  private_key_filename: null,
  ca_certificate_configured: false,
  ca_certificate_filename: null,
});
const originalSecuritySettings = ref({
  tls_enabled: false,
  tls_mode: "one_way" as SecurityConfig["tls_mode"],
});

// GOOSE 预览状态
const previewLoading = ref(false);
const goosePreviewVisible = ref(false);
const goosePreviewData = ref<PointImportResult | null>(null);
const previewDone = ref(false);

// 操作进度
const saving = ref(false);
const loadingChannel = ref(false);
const progressText = ref("");
const importElapsed = ref(0);
let progressTimer: number | null = null;
let channelLoadRequest = 0;

const defaultSecurityConfig = (): SecurityConfig => ({
  tls_enabled: false,
  tls_mode: "one_way",
  certificate_configured: false,
  certificate_filename: null,
  private_key_configured: false,
  private_key_filename: null,
  ca_certificate_configured: false,
  ca_certificate_filename: null,
});

const applyPersistedSecurityConfig = (persisted?: SecurityConfig) => {
  const normalized = {
    ...defaultSecurityConfig(),
    ...(persisted || {}),
    // 兼容旧数据库；basic 已整改为会校验 CA 的单向 TLS。
    tls_mode:
      (persisted?.tls_mode as string) === "mutual" ? "mutual" : "one_way",
    // 开关只认后端持久化的布尔值，不根据证书或本地点击状态推断。
    tls_enabled:
      persisted?.tls_enabled === true &&
      TLS_SUPPORTED_PROTOCOLS.has(form.protocol_type) &&
      (form.conn_type === 1 || form.conn_type === 2),
  };
  Object.assign(securityConfig, normalized);
};

const applyPersistedProtocolParams = (
  persisted?: ChannelCreateRequest["protocol_params"],
) => {
  protocolParams.schema_version = persisted?.schema_version || 1;
  // 使用独立对象回填，避免子组件补默认字段时修改接口响应对象，
  // 同时确保认证开关和密码不会被旧协议字段的监听任务覆盖。
  protocolParams.values = { ...(persisted?.values || {}) };
};

const gooseControlList = computed(() => {
  return goosePreviewData.value?.goose?.summary?.gse_controls || [];
});

const isEditMode = computed(() => !!props.channelId);
const isIec61850Server = computed(
  () => form.protocol_type === 4 && form.conn_type === 2,
);
const tlsSupportedProtocol = computed(() =>
  TLS_SUPPORTED_PROTOCOLS.has(form.protocol_type),
);
const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit("update:visible", val),
});

const form = reactive<ChannelCreateRequest>({
  code: "",
  name: "",
  protocol_type: 1,
  conn_type: 2,
  ip: "0.0.0.0",
  port: 502,
  com_port: "",
  baud_rate: 9600,
  data_bits: 8,
  stop_bits: 1,
  parity: "N",
  rtu_addr: "1",
  group_id: null,
  protocol_params: protocolParams,
  dlt645_point_mode: "standard",
});

const rules = computed<FormRules>(() => {
  const base: FormRules = {
    code: [
      { required: true, message: t("addDevice.codeRequired"), trigger: "blur" },
    ],
    name: [
      { required: true, message: t("addDevice.nameRequired"), trigger: "blur" },
    ],
    port: [
      { required: true, message: t("addDevice.portRequired"), trigger: "blur" },
    ],
  };
  // DLT645 电表地址必须为 12 位数字
  if (form.protocol_type === 3) {
    base.rtu_addr = [
      {
        required: true,
        message: t("addDevice.meterAddressRequired"),
        trigger: "blur",
      },
      {
        pattern: /^\d{12}$/,
        message: t("addDevice.meterAddressInvalid"),
        trigger: "blur",
      },
    ];
  }
  return base;
});

// 生命周期与监听
onMounted(async () => {
  try {
    const config = await getProtocolConfig();
    protocols.value = config.protocols;
    await loadSerialPorts();
  } catch (e) {
    console.error("加载系统配置失败", e);
  }
});

watch(
  () => props.visible,
  async (val) => {
    if (val) {
      activeTab.value = "basic";
      clearPendingPointFiles();
      await loadDeviceGroups();
      if (!isEditMode.value) {
        resetForm();
        if (props.initialGroupId) form.group_id = props.initialGroupId;
      }
    }
  },
);

watch(
  () => [props.visible, props.channelId],
  async ([v, c]) => {
    if (v && c) {
      clearPendingPointFiles();
      await loadChannelData(c as number);
    }
  },
  { immediate: true },
);

watch(
  () => [form.protocol_type, form.conn_type],
  async ([protocolType, connType]) => {
    if (!TLS_SUPPORTED_PROTOCOLS.has(protocolType)) {
      securityConfig.tls_enabled = false;
      if (activeTab.value === "security") activeTab.value = "basic";
    }
    // DLT645 电表地址统一为 12 位数字（补零），避免短地址残留
    if (protocolType === 3 && !loadingChannel.value) {
      form.rtu_addr = String(form.rtu_addr || "").padStart(12, "0");
    }
    if (protocolType === 4 && connType === 2) {
      selectedFile.value = null;
    } else {
      icdFile.value = null;
    }
    uploadCompRef.value?.clearFiles();
    if (!loadingChannel.value) {
      await nextTick();
      protocolParamsCompRef.value?.resetDefaults();
    }
  },
);

watch(mediaType, (value) => {
  if (value === "serial") securityConfig.tls_enabled = false;
});

// 核心逻辑
const loadDeviceGroups = async () => {
  deviceGroupOptions.value = await getAllDeviceGroups();
};
const loadSerialPorts = async () => {
  serialPorts.value = await getSerialPorts();
};

const loadChannelData = async (id: number) => {
  const requestId = ++channelLoadRequest;
  loadingChannel.value = true;
  try {
    const data = await getChannel(id);
    if (!data || requestId !== channelLoadRequest) return;
    Object.assign(form, data);
    originalDlt645PointMode.value = normalizeDlt645PointMode(
      data.dlt645_point_mode,
    );
    // DLT645 电表地址回显统一为 12 位数字（兼容历史短地址数据）
    if (form.protocol_type === 3) {
      form.rtu_addr = String(form.rtu_addr || "").padStart(12, "0");
      dlt645PointMode.value = originalDlt645PointMode.value;
    } else {
      dlt645PointMode.value = "standard";
    }
    applyPersistedProtocolParams(data.protocol_params);
    form.protocol_params = protocolParams;
    applyPersistedSecurityConfig(data.security_config);
    originalSecuritySettings.value = {
      tls_enabled: securityConfig.tls_enabled,
      tls_mode: securityConfig.tls_mode,
    };
    originalName.value = data.name || "";
    mediaType.value = isSerialConnectionType(data.conn_type)
      ? "serial"
      : "network";
    // 让子组件先在 loading 状态下完成协议类型与持久化参数的同一轮渲染，
    // 避免协议切换监听器把刚回填的认证配置重置为默认值。
    await nextTick();
  } catch (e) {
    console.error("加载通道失败", e);
  } finally {
    if (requestId === channelLoadRequest) loadingChannel.value = false;
  }
};

const resetForm = () => {
  dlt645PointMode.value = "standard";
  originalDlt645PointMode.value = "standard";
  Object.assign(form, {
    code: "",
    name: "",
    protocol_type: 1,
    conn_type: 2,
    ip: "0.0.0.0",
    port: 502,
    com_port: "COM1",
    baud_rate: 9600,
    data_bits: 8,
    stop_bits: 1,
    parity: "N",
    rtu_addr: "1",
    group_id: null,
    protocol_params: protocolParams,
    dlt645_point_mode: "standard",
  });
  applyPersistedProtocolParams();
  applyPersistedSecurityConfig();
  originalSecuritySettings.value = {
    tls_enabled: false,
    tls_mode: "one_way",
  };
  clearPendingPointFiles();
  goosePreviewData.value = null;
  previewDone.value = false;
};

function clearPendingPointFiles() {
  selectedFile.value = null;
  icdFile.value = null;
  uploadCompRef.value?.clearFiles();
  certificateFile.value = null;
  privateKeyFile.value = null;
  caCertificateFile.value = null;
  securityCompRef.value?.clearFiles();
}

const handleIcdFileChange = async (file: File | null) => {
  icdFile.value = file;
};

// MAC 地址格式化：优先用 ICD 中的，否则按 GOOSE 标准根据 APPID 自动推算
const formatMac = (row: any) => {
  if (row.mac_address) return row.mac_address;
  if (row.app_id) {
    const prefix = "01:0C:CD";
    let appId =
      typeof row.app_id === "number"
        ? row.app_id
        : parseInt(row.app_id, 16) || parseInt(row.app_id, 10) || 0;
    const high = (appId >> 8) & 0xff;
    const low = appId & 0xff;
    return `${prefix}:${high.toString(16).padStart(2, "0").toUpperCase()}:${low.toString(16).padStart(2, "0").toUpperCase()}`;
  }
  return "-";
};

// ICD 预览：调用后端接口解析 ICD 文件中的 GOOSE 控制块信息
const handlePreviewIcd = async () => {
  if (!icdFile.value) return;
  previewLoading.value = true;
  try {
    const { previewIcd } = await import("@/api/channelApi");
    const result = await previewIcd(icdFile.value);
    goosePreviewData.value = result;
    previewDone.value = true;
    goosePreviewVisible.value = true;
  } catch (e: any) {
    console.error("预览 ICD 失败", e);
  } finally {
    previewLoading.value = false;
  }
};

// 提交保存：全程使用进度条，按钮不转圈
const handleSubmit = async () => {
  if (!formRef.value || saving.value || loadingChannel.value) return;
  if (protocolParamsCompRef.value?.validate() === false) {
    activeTab.value = "protocol";
    return;
  }
  if (securityConfig.tls_enabled) {
    const hasCertificate =
      securityConfig.certificate_configured || !!certificateFile.value;
    const hasPrivateKey =
      securityConfig.private_key_configured || !!privateKeyFile.value;
    const hasCaCertificate =
      securityConfig.ca_certificate_configured || !!caCertificateFile.value;
    const requirements = getTlsMaterialRequirements(
      securityConfig.tls_mode,
      form.conn_type,
    );
    const missingIdentity =
      requirements.identity && (!hasCertificate || !hasPrivateKey);
    const missingCaCertificate =
      requirements.caCertificate && !hasCaCertificate;
    if (missingIdentity || missingCaCertificate) {
      activeTab.value = "security";
      const messageKey =
        securityConfig.tls_mode === "mutual"
          ? "addDevice.tlsMutualRequired"
          : form.conn_type === 1
            ? "addDevice.tlsOneWayCaRequired"
            : "addDevice.tlsOneWayIdentityRequired";
      ElMessage.error(t(messageKey));
      return;
    }
  }
  form.protocol_params = protocolParams;
  // TreeSelect 清空时部分 Element Plus 版本会返回 undefined；显式提交 null
  // 才能让后台区分“移到未分组”和“未修改分组”。
  if (form.group_id === undefined) form.group_id = null;
  // DLT645 电表地址统一为 12 位数字（补零后校验）
  if (form.protocol_type === 3) {
    form.rtu_addr = String(form.rtu_addr || "").padStart(12, "0");
    form.dlt645_point_mode = dlt645PointMode.value;
  }
  await formRef.value.validate(async (valid) => {
    if (!valid) {
      activeTab.value = "basic";
      return;
    }
    saving.value = true;
    importElapsed.value = 0;
    progressTimer = window.setInterval(() => {
      importElapsed.value++;
    }, 1000);
    try {
      let resultId: number;
      const hasNewSecurityFiles = Boolean(
        certificateFile.value ||
        privateKeyFile.value ||
        caCertificateFile.value,
      );
      const shouldSaveSecurity = shouldSaveChannelSecurity({
        isEdit: isEditMode.value,
        tlsSupported: tlsSupportedProtocol.value,
        tlsEnabled: securityConfig.tls_enabled,
        tlsMode: securityConfig.tls_mode,
        originalTlsEnabled: originalSecuritySettings.value.tls_enabled,
        originalTlsMode: originalSecuritySettings.value.tls_mode,
        hasNewFiles: hasNewSecurityFiles,
      });

      // 1. 保存通道
      progressText.value = t("addDevice.savingChannel");
      if (isEditMode.value && props.channelId) {
        // When TLS also changed, its endpoint performs the single required reload.
        await updateChannel(props.channelId, form, shouldSaveSecurity);
        resultId = props.channelId;
      } else {
        const createRes = await createChannel(form);
        resultId = createRes.channel_id;
      }

      // Serial protocols (including DLT645) do not have TLS configuration.
      if (shouldSaveSecurity) {
        progressText.value = t("addDevice.savingTlsConfig");
        const persistedSecurity = await uploadChannelSecurity(
          resultId,
          securityConfig.tls_enabled,
          securityConfig.tls_mode,
          certificateFile.value,
          privateKeyFile.value,
          caCertificateFile.value,
        );
        applyPersistedSecurityConfig(persistedSecurity);
        originalSecuritySettings.value = {
          tls_enabled: securityConfig.tls_enabled,
          tls_mode: securityConfig.tls_mode,
        };
      }

      // Only import a point table when one was newly selected.
      if (
        form.protocol_type === 3 &&
        shouldImportDlt645Standard(
          dlt645PointMode.value,
          isEditMode.value,
          originalDlt645PointMode.value,
        )
      ) {
        progressText.value = t("addDevice.importingDlt645");
        await importDlt645StandardPoints(resultId);
      } else if (!isIec61850Server.value && selectedFile.value) {
        progressText.value = t("addDevice.importingPoints");
        await importPoints(resultId, selectedFile.value);
      }

      // 4. ICD 文件导入
      if (isIec61850Server.value && icdFile.value) {
        progressText.value = t("addDevice.icdImporting");
        const { importIcdPoints } = await import("@/api/channelApi");
        await importIcdPoints(resultId, icdFile.value, "eth0", "model_only");
      }

      emit("success", form.name, isEditMode.value, originalName.value);
      dialogVisible.value = false;
    } catch (e: any) {
      console.error(e.message || t("addDevice.operationFailed"));
    } finally {
      if (progressTimer) {
        clearInterval(progressTimer);
        progressTimer = null;
      }
      saving.value = false;
    }
  });
};

const handleClose = () => {
  channelLoadRequest++;
  loadingChannel.value = false;
  clearPendingPointFiles();
  dialogVisible.value = false;
  goosePreviewVisible.value = false;
  goosePreviewData.value = null;
  previewDone.value = false;
  emit("close");
};
</script>

<style lang="scss">
.device-form-dialog {
  .el-dialog__header {
    position: relative;
    display: flex;
    align-items: center;
    min-height: 54px;
    margin-right: 0;
    padding: 0 56px 0 22px;
    border-bottom: 1px solid var(--sidebar-border);

    .el-dialog__title {
      line-height: 1;
      font-size: 18px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }

    .el-dialog__headerbtn {
      top: 0;
      right: 4px;
      width: 50px;
      height: 54px;
    }
  }

  .el-dialog__body {
    padding: 10px 28px 18px;
  }

  .el-dialog__footer {
    padding: 14px 22px 18px;
    border-top: 1px solid var(--sidebar-border);
  }
}
.submit-btn {
  padding-left: 20px;
  padding-right: 20px;
  font-weight: 600;
}
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.device-form-tabs {
  min-height: 420px;

  .el-tabs__header {
    margin: 0 0 16px;
  }

  .el-tabs__nav-wrap {
    padding: 0;
    overflow: hidden;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 10px;
    background: var(--el-fill-color-light);

    &::after {
      display: none;
    }
  }

  .el-tabs__nav-scroll,
  .el-tabs__nav {
    width: 100%;
  }

  .el-tabs__nav {
    display: flex;
  }

  .el-tabs__item {
    flex: 1;
    justify-content: center;
    height: 38px;
    padding: 0 16px;
    border-radius: 9px;
    color: var(--el-text-color-secondary);
    font-weight: 500;
    transition:
      color 0.2s ease,
      background-color 0.2s ease,
      box-shadow 0.2s ease;

    &:hover {
      color: var(--el-color-primary);
    }

    &.is-active {
      color: var(--el-color-primary);
      background: var(--el-bg-color);
      box-shadow: 0 1px 4px rgb(0 0 0 / 10%);
      font-weight: 600;
    }
  }

  .el-tabs__active-bar {
    display: none;
  }

  .el-tab-pane {
    padding-top: 0;
  }
}
.icd-import-progress {
  padding: 24px 0 12px;
  text-align: center;
  :deep(.el-progress) {
    padding-right: 0;
  }
  :deep(.el-progress-bar) {
    margin-right: 0;
    width: 100%;
  }
  :deep(.el-progress__text) {
    display: none;
  }
}
.icd-import-hint {
  margin-top: 10px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}
</style>
