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
        <el-form-item label="证书" required>
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

const tlsSupported = computed(() => props.protocolType === 1);

const emit = defineEmits<{
  (event: "certificate-change", file: File): void;
  (event: "private-key-change", file: File): void;
}>();

const certificateUploadRef = ref();
const privateKeyUploadRef = ref();
const certificateSelected = ref(false);
const privateKeySelected = ref(false);

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

function clearFiles() {
  certificateUploadRef.value?.clearFiles();
  privateKeyUploadRef.value?.clearFiles();
  certificateSelected.value = false;
  privateKeySelected.value = false;
}

defineExpose({ clearFiles });
</script>

<style scoped>
.security-config-form {
  min-height: 220px;
  padding-top: 8px;
}
</style>
