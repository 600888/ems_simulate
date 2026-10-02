<template>
  <div class="opcua-device-security">
    <el-alert
      :title="$t('opcua.deviceSecurityHint')"
      type="info"
      :closable="false"
      show-icon
    />
    <el-form-item :label="$t('opcua.deviceEnableSecurity')" label-width="180px">
      <el-switch
        :model-value="modelValue.mode !== 'None'"
        :disabled="disabled"
        @change="toggleSecurity"
      />
    </el-form-item>
    <template v-if="modelValue.mode !== 'None'">
      <el-form-item
        :label="$t('opcua.securityMode')"
        label-width="180px"
        required
      >
        <el-select v-model="modelValue.mode" :disabled="disabled">
          <el-option label="SignAndEncrypt" value="SignAndEncrypt" />
          <el-option
            label="Sign"
            value="Sign"
            :disabled="modelValue.identity === 'username'"
          />
        </el-select>
      </el-form-item>
      <el-form-item
        :label="$t('opcua.deviceSecurityPolicy')"
        label-width="180px"
      >
        <el-input model-value="Basic256Sha256" readonly />
      </el-form-item>
      <el-form-item label="Application URI" label-width="180px" required>
        <el-input
          v-model="modelValue.application_uri"
          maxlength="255"
          :disabled="disabled"
        />
      </el-form-item>
      <el-form-item
        :label="$t('opcua.applicationCertificate')"
        label-width="180px"
      >
        <el-checkbox
          v-model="modelValue.generate_certificate"
          :disabled="disabled || !!certificateFile || !!privateKeyFile"
        >
          {{ $t("opcua.deviceGenerateCertificate") }}
        </el-checkbox>
        <el-tag v-if="modelValue.certificate_configured" type="success">{{
          $t("opcua.certificateReady")
        }}</el-tag>
      </el-form-item>
      <template v-if="!modelValue.generate_certificate">
        <el-form-item
          :label="$t('device.localCert')"
          label-width="180px"
          required
        >
          <el-upload
            ref="certificateUpload"
            :auto-upload="false"
            :limit="1"
            accept=".crt,.cer,.pem"
            :disabled="disabled"
            :on-change="
              (file: UploadFile) => (certificateFile = file.raw || null)
            "
            :on-remove="() => (certificateFile = null)"
          >
            <el-button :disabled="disabled" plain type="primary">{{
              $t("device.uploadCert")
            }}</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item
          :label="$t('device.privateKey')"
          label-width="180px"
          required
        >
          <el-upload
            ref="privateKeyUpload"
            :auto-upload="false"
            :limit="1"
            accept=".key,.pem"
            :disabled="disabled"
            :on-change="
              (file: UploadFile) => (privateKeyFile = file.raw || null)
            "
            :on-remove="() => (privateKeyFile = null)"
          >
            <el-button :disabled="disabled" plain type="primary">{{
              $t("device.uploadKey")
            }}</el-button>
          </el-upload>
          <el-tag v-if="modelValue.private_key_configured" type="success">{{
            $t("opcua.devicePrivateKeyReady")
          }}</el-tag>
        </el-form-item>
      </template>
      <el-form-item
        :label="$t('opcua.devicePeerCertificate')"
        label-width="180px"
      >
        <el-upload
          ref="peerUpload"
          :auto-upload="false"
          :limit="1"
          accept=".crt,.cer,.pem"
          :disabled="disabled"
          :on-change="(file: UploadFile) => (peerFile = file.raw || null)"
          :on-remove="() => (peerFile = null)"
        >
          <el-button :disabled="disabled" plain type="primary">{{
            $t("device.uploadCert")
          }}</el-button>
        </el-upload>
        <div class="field-tip">
          {{
            $t("opcua.devicePeerCertificateHint", {
              count: modelValue.trusted_count || 0,
            })
          }}
        </div>
      </el-form-item>
      <template v-if="connType === 1">
        <el-form-item :label="$t('opcua.identity')" label-width="180px">
          <el-select v-model="modelValue.identity" :disabled="disabled">
            <el-option :label="$t('opcua.anonymous')" value="anonymous" />
            <el-option
              :label="$t('opcua.username')"
              value="username"
              :disabled="modelValue.mode !== 'SignAndEncrypt'"
            />
          </el-select>
        </el-form-item>
        <template v-if="modelValue.identity === 'username'">
          <el-form-item
            :label="$t('opcua.username')"
            label-width="180px"
            required
          >
            <el-input
              v-model="modelValue.username"
              :disabled="disabled"
              maxlength="128"
              autocomplete="off"
            />
          </el-form-item>
          <el-form-item
            :label="$t('opcua.password')"
            label-width="180px"
            required
          >
            <el-input
              v-model="password"
              type="password"
              show-password
              :disabled="disabled"
              maxlength="1024"
              autocomplete="new-password"
              :placeholder="
                modelValue.password_configured
                  ? $t('opcua.devicePasswordUnchanged')
                  : ''
              "
            />
          </el-form-item>
        </template>
      </template>
      <el-form-item v-else :label="$t('opcua.anonymous')" label-width="180px">
        <el-switch v-model="modelValue.allow_anonymous" :disabled="disabled" />
        <div class="field-tip">{{ $t("opcua.deviceServerUsersHint") }}</div>
      </el-form-item>
      <el-form-item
        v-if="connType === 2"
        :label="$t('opcua.advertisedHost')"
        label-width="180px"
      >
        <el-input
          v-model="modelValue.advertised_host"
          :disabled="disabled"
          maxlength="255"
        />
      </el-form-item>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, type UploadFile } from "element-plus";
import { useI18n } from "vue-i18n";
import type { OpcUaDeviceConfig } from "@/types/channel";
import { opcuaFileBase64 } from "@/utils/opcuaDeviceConfig";

const props = defineProps<{
  modelValue: OpcUaDeviceConfig;
  connType: number;
  disabled?: boolean;
}>();
const { t } = useI18n();
const certificateFile = ref<File | null>(null);
const privateKeyFile = ref<File | null>(null);
const peerFile = ref<File | null>(null);
const password = ref("");
const certificateUpload = ref();
const privateKeyUpload = ref();
const peerUpload = ref();

function toggleSecurity(enabled: string | number | boolean) {
  props.modelValue.mode = enabled ? "SignAndEncrypt" : "None";
  if (!enabled) {
    props.modelValue.identity = "anonymous";
    password.value = "";
  }
}

function validate(): boolean {
  if (props.modelValue.mode === "None") return true;
  if (
    !props.modelValue.generate_certificate &&
    (!(certificateFile.value || props.modelValue.certificate_configured) ||
      !(privateKeyFile.value || props.modelValue.private_key_configured))
  ) {
    ElMessage.error(t("opcua.deviceIdentityRequired"));
    return false;
  }
  if (
    props.modelValue.identity === "username" &&
    !password.value &&
    !props.modelValue.password_configured
  ) {
    ElMessage.error(t("opcua.devicePasswordRequired"));
    return false;
  }
  return true;
}

async function payload(): Promise<Partial<OpcUaDeviceConfig>> {
  if (props.modelValue.mode === "None") return {};
  const fields: Partial<OpcUaDeviceConfig> = {};
  if (certificateFile.value)
    fields.certificate = await opcuaFileBase64(certificateFile.value);
  if (privateKeyFile.value)
    fields.private_key = await opcuaFileBase64(privateKeyFile.value);
  if (peerFile.value)
    fields.peer_certificate = await opcuaFileBase64(peerFile.value);
  if (password.value) fields.password = password.value;
  return fields;
}

function clearFiles() {
  certificateFile.value = privateKeyFile.value = peerFile.value = null;
  password.value = "";
  certificateUpload.value?.clearFiles();
  privateKeyUpload.value?.clearFiles();
  peerUpload.value?.clearFiles();
}
defineExpose({ validate, payload, clearFiles });
</script>

<style scoped>
.opcua-device-security > .el-alert {
  margin-bottom: 18px;
}
.field-tip {
  width: 100%;
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.el-tag {
  margin-left: 10px;
}
</style>
