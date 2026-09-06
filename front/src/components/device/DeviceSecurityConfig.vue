<template>
  <div class="security-config-form">
    <el-alert
      v-if="!networkMode"
      :title="$t('device.tlsNotSupportedSerial')"
      type="info"
      :closable="false"
      show-icon
    />

    <el-alert
      v-else-if="!tlsSupported"
      :title="$t('device.tlsNotSupportedProtocol')"
      type="info"
      :closable="false"
      show-icon
    />

    <template v-else>
      <el-form-item :label="$t('device.enableTls')">
        <el-switch v-model="modelValue.tls_enabled" :disabled="disabled" />
      </el-form-item>

      <template v-if="modelValue.tls_enabled">
        <el-form-item :label="$t('device.tlsMode')" required>
          <el-radio-group v-model="modelValue.tls_mode" :disabled="disabled">
            <el-radio-button value="one_way">{{
              $t("device.tlsOneWay")
            }}</el-radio-button>
            <el-radio-button value="mutual">{{
              $t("device.tlsMutual")
            }}</el-radio-button>
          </el-radio-group>
          <div class="mode-description">
            <template v-if="modelValue.tls_mode === 'one_way'">
              {{
                $t(
                  connType === 1
                    ? "device.tlsOneWayClientDesc"
                    : "device.tlsOneWayServerDesc",
                )
              }}
            </template>
            <template v-else>
              {{ $t("device.tlsMutualDesc") }}
            </template>
          </div>
        </el-form-item>

        <el-form-item :label="$t('device.tlsVersion')" required>
          <el-radio-group v-model="modelValue.tls_version" :disabled="disabled">
            <el-radio-button value="1.2">TLS 1.2</el-radio-button>
            <el-radio-button value="1.3">TLS 1.3</el-radio-button>
          </el-radio-group>
          <div class="mode-description">
            {{ $t("device.tlsVersionDesc") }}
          </div>
        </el-form-item>

        <el-form-item
          v-if="materialRequirements.identity"
          :label="$t('device.localCert')"
          required
        >
          <div class="file-config">
            <div class="file-action-row">
              <el-upload
                class="certificate-upload"
                ref="certificateUploadRef"
                action="#"
                :auto-upload="true"
                :limit="1"
                :disabled="disabled"
                :http-request="handleCertificate"
                accept=".crt,.cer,.pem"
              >
                <el-button type="primary" plain :disabled="disabled">{{
                  $t("device.uploadCert")
                }}</el-button>
              </el-upload>
              <el-tag
                v-if="modelValue.certificate_configured && !certificateSelected"
                class="persisted-file"
                type="success"
                effect="plain"
              >
                {{
                  $t("device.savedFile", {
                    filename:
                      modelValue.certificate_filename || $t("device.certFile"),
                  })
                }}
              </el-tag>
            </div>
            <div class="el-upload__tip">{{ $t("device.certTip") }}</div>
          </div>
        </el-form-item>

        <el-form-item
          v-if="materialRequirements.identity"
          :label="$t('device.privateKey')"
          required
        >
          <div class="file-config">
            <div class="file-action-row">
              <el-upload
                class="certificate-upload"
                ref="privateKeyUploadRef"
                action="#"
                :auto-upload="true"
                :limit="1"
                :disabled="disabled"
                :http-request="handlePrivateKey"
                accept=".key,.pem"
              >
                <el-button type="primary" plain :disabled="disabled">{{
                  $t("device.uploadKey")
                }}</el-button>
              </el-upload>
              <el-tag
                v-if="modelValue.private_key_configured && !privateKeySelected"
                class="persisted-file"
                type="success"
                effect="plain"
              >
                {{
                  $t("device.savedFile", {
                    filename:
                      modelValue.private_key_filename || $t("device.keyFile"),
                  })
                }}
              </el-tag>
            </div>
            <div class="el-upload__tip">{{ $t("device.keyTip") }}</div>
          </div>
        </el-form-item>

        <el-form-item
          v-if="materialRequirements.caCertificate"
          :label="$t('device.caCert')"
          required
        >
          <div class="file-config">
            <div class="file-action-row">
              <el-upload
                class="certificate-upload"
                ref="caCertificateUploadRef"
                action="#"
                :auto-upload="true"
                :limit="1"
                :disabled="disabled"
                :http-request="handleCaCertificate"
                accept=".crt,.cer,.pem"
              >
                <el-button type="primary" plain :disabled="disabled">{{
                  $t("device.uploadCaCert")
                }}</el-button>
              </el-upload>
              <el-tag
                v-if="
                  modelValue.ca_certificate_configured && !caCertificateSelected
                "
                class="persisted-file"
                type="success"
                effect="plain"
              >
                {{
                  $t("device.savedFile", {
                    filename:
                      modelValue.ca_certificate_filename || $t("device.caFile"),
                  })
                }}
              </el-tag>
            </div>
            <div class="el-upload__tip">
              {{ $t("device.caTip") }}
            </div>
          </div>
        </el-form-item>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { supportsTlsProtocol } from "@/constants/protocol";
import type { SecurityConfig } from "@/types/channel";
import { getTlsMaterialRequirements } from "@/utils/channelEdit";

const props = defineProps<{
  modelValue: SecurityConfig;
  networkMode: boolean;
  protocolType: number;
  connType: number;
  disabled?: boolean;
}>();

const tlsSupported = computed(() => supportsTlsProtocol(props.protocolType));
const materialRequirements = computed(() =>
  getTlsMaterialRequirements(props.modelValue.tls_mode, props.connType),
);

const emit = defineEmits<{
  (event: "certificate-change", file: File): void;
  (event: "private-key-change", file: File): void;
  (event: "ca-certificate-change", file: File): void;
}>();

const certificateUploadRef = ref();
const privateKeyUploadRef = ref();
const caCertificateUploadRef = ref();
const certificateSelected = ref(false);
const privateKeySelected = ref(false);
const caCertificateSelected = ref(false);

function handleCertificate(options: any) {
  certificateSelected.value = true;
  emit("certificate-change", options.file);
  return Promise.resolve();
}

function handlePrivateKey(options: any) {
  privateKeySelected.value = true;
  emit("private-key-change", options.file);
  return Promise.resolve();
}

function handleCaCertificate(options: any) {
  caCertificateSelected.value = true;
  emit("ca-certificate-change", options.file);
  return Promise.resolve();
}

function clearFiles() {
  certificateUploadRef.value?.clearFiles();
  privateKeyUploadRef.value?.clearFiles();
  caCertificateUploadRef.value?.clearFiles();
  certificateSelected.value = false;
  privateKeySelected.value = false;
  caCertificateSelected.value = false;
}

defineExpose({ clearFiles });
</script>

<style scoped>
.security-config-form {
  min-height: 220px;
  padding-top: 8px;
}

.mode-description {
  width: 100%;
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.file-config {
  width: 100%;
}

.file-action-row {
  display: grid;
  grid-template-columns: 300px max-content;
  align-items: start;
  column-gap: 12px;
  min-height: 32px;
}

.certificate-upload {
  min-width: 0;
}

.persisted-file {
  align-self: start;
  width: fit-content;
  margin-top: 5.5px;
}
</style>
