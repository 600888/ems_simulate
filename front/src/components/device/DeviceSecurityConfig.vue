<template>
  <div class="security-config-form">
    <el-alert
      v-if="!networkMode"
      title="串口模式不支持 TLS"
      type="info"
      :closable="false"
      show-icon
    />

    <el-alert
      v-else-if="!tlsSupported"
      title="当前协议暂不支持 TLS"
      type="info"
      :closable="false"
      show-icon
    />

    <template v-else>
      <el-form-item label="启用 TLS">
        <el-switch v-model="modelValue.tls_enabled" :disabled="disabled" />
      </el-form-item>

      <template v-if="modelValue.tls_enabled">
        <el-form-item label="TLS 模式" required>
          <el-radio-group v-model="modelValue.tls_mode" :disabled="disabled">
            <el-radio-button value="basic">基础 TLS</el-radio-button>
            <el-radio-button value="mutual">双向认证 TLS</el-radio-button>
          </el-radio-group>
          <div class="mode-description">
            <template v-if="modelValue.tls_mode === 'basic'">
              仅加密链路，不校验对端证书身份。
            </template>
            <template v-else>
              使用 CA 双向校验证书，并校验服务端主机名或 IP。
            </template>
          </div>
        </el-form-item>

        <el-form-item label="本端证书" required>
          <el-upload
            ref="certificateUploadRef"
            action="#"
            :auto-upload="true"
            :limit="1"
            :disabled="disabled"
            :http-request="handleCertificate"
            accept=".crt,.cer,.pem"
          >
            <el-button type="primary" plain :disabled="disabled"
              >上传证书</el-button
            >
            <template #tip>
              <div class="el-upload__tip">
                支持 .crt、.cer、.pem
                <span
                  v-if="
                    modelValue.certificate_configured && !certificateSelected
                  "
                >
                  ，当前：{{ modelValue.certificate_filename || "已上传" }}
                </span>
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item label="私钥" required>
          <el-upload
            ref="privateKeyUploadRef"
            action="#"
            :auto-upload="true"
            :limit="1"
            :disabled="disabled"
            :http-request="handlePrivateKey"
            accept=".key,.pem"
          >
            <el-button type="primary" plain :disabled="disabled"
              >上传私钥</el-button
            >
            <template #tip>
              <div class="el-upload__tip">
                支持 .key、.pem
                <span
                  v-if="
                    modelValue.private_key_configured && !privateKeySelected
                  "
                >
                  ，当前：{{ modelValue.private_key_filename || "已上传" }}
                </span>
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item
          v-if="modelValue.tls_mode === 'mutual'"
          label="CA 证书"
          required
        >
          <el-upload
            ref="caCertificateUploadRef"
            action="#"
            :auto-upload="true"
            :limit="1"
            :disabled="disabled"
            :http-request="handleCaCertificate"
            accept=".crt,.cer,.pem"
          >
            <el-button type="primary" plain :disabled="disabled"
              >上传 CA 证书</el-button
            >
            <template #tip>
              <div class="el-upload__tip">
                用于双向校验对端证书，支持 .crt、.cer、.pem
                <span
                  v-if="
                    modelValue.ca_certificate_configured &&
                    !caCertificateSelected
                  "
                >
                  ，当前：{{ modelValue.ca_certificate_filename || "已上传" }}
                </span>
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { SecurityConfig } from "@/types/channel";

const props = defineProps<{
  modelValue: SecurityConfig;
  networkMode: boolean;
  protocolType: number;
  disabled?: boolean;
}>();

const tlsSupported = computed(
  () => props.protocolType === 1 || props.protocolType === 2,
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
</style>
