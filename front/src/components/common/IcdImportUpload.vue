<template>
  <div class="icd-import-upload" style="display: contents">
    <!-- 隐藏的文件输入 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".icd,.scd,.cid,.xml"
      style="display: none"
      @change="onFileSelected"
    />

    <el-dialog
      v-model="configVisible"
      title="IEC 61850 GOOSE 导入方式"
      width="560px"
      :close-on-click-modal="false"
      @closed="cancelConfiguration"
    >
      <el-alert
        title="MMS 客户端/服务端角色不会自动决定 GOOSE 方向，请按文件用途选择。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 18px"
      />
      <el-form label-width="120px">
        <el-form-item label="导入视角">
          <el-select v-model="gooseImportMode" style="width: 100%">
            <el-option label="本地 IED：创建发布" value="local_publish" />
            <el-option label="远端 IED：创建订阅" value="remote_subscribe" />
            <el-option label="同时创建发布和订阅（测试）" value="both" />
            <el-option label="仅加载模型，不创建 GOOSE 资源" value="model_only" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="gooseImportMode !== 'model_only'" label="本机网卡">
          <el-select v-model="interfaceName" style="width: 100%" filterable>
            <el-option
              v-for="item in networkInterfaces"
              :key="item.id"
              :label="`${item.display_name} · ${item.mac || '无 MAC'}`"
              :value="item.id"
            />
          </el-select>
          <div v-if="!networkInterfaces.length" class="interface-warning">
            未发现可用二层网卡，将使用兼容值 eth0；启动前仍会由后端校验。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmConfiguration">确认导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" setup>
import { ref } from "vue";
import { importIcdPoints } from "@/api/channelApi";
import { getGooseNetworkInterfaces, type NetworkInterfaceInfo } from "@/api/gooseApi";
import type { PointImportResult } from "@/types/channel";

type GooseImportMode = "model_only" | "local_publish" | "remote_subscribe" | "both";

const emit = defineEmits<{
  (e: "file-change", file: File | null): void;
  (e: "import-start"): void;
  (e: "import-success", result: PointImportResult): void;
  (e: "import-error", error: any): void;
}>();

const fileInputRef = ref<HTMLInputElement | null>(null);
const importing = ref(false);
const configVisible = ref(false);
const gooseImportMode = ref<GooseImportMode>("model_only");
const interfaceName = ref("eth0");
const networkInterfaces = ref<NetworkInterfaceInfo[]>([]);
let selectedFile: File | null = null;
let configResolve: (() => void) | null = null;
let configReject: ((reason?: unknown) => void) | null = null;

const onFileSelected = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  selectedFile = file;
  emit("file-change", file);
  // 重置 input 以便下次选择同一文件
  target.value = "";
};

const openFileDialog = () => {
  fileInputRef.value?.click();
};

const importIcd = async (
  channelId: number,
  defaultMode: GooseImportMode = "model_only"
): Promise<PointImportResult | null> => {
  if (!selectedFile) {
    throw new Error("未选择 ICD 文件");
  }

  const file = selectedFile;
  gooseImportMode.value = defaultMode;
  try {
    const interfaces = await getGooseNetworkInterfaces();
    networkInterfaces.value = interfaces.filter(
      (item) => item.is_up && !item.is_loopback && item.supports_raw_ethernet
    );
    interfaceName.value = networkInterfaces.value[0]?.id || "eth0";
  } catch {
    networkInterfaces.value = [];
    interfaceName.value = "eth0";
  }

  configVisible.value = true;
  await new Promise<void>((resolve, reject) => {
    configResolve = resolve;
    configReject = reject;
  });

  importing.value = true;
  emit("import-start");

  try {
    const result = await importIcdPoints(
      channelId,
      file,
      interfaceName.value,
      gooseImportMode.value
    );
    emit("import-success", result);
    return result;
  } catch (error) {
    emit("import-error", error);
    throw error;
  } finally {
    importing.value = false;
  }
};

const confirmConfiguration = () => {
  const resolve = configResolve;
  configResolve = null;
  configReject = null;
  configVisible.value = false;
  resolve?.();
};

const cancelConfiguration = () => {
  if (!configReject) return;
  const reject = configReject;
  configResolve = null;
  configReject = null;
  reject(new Error("已取消 ICD 导入"));
};

const clear = () => {
  selectedFile = null;
  importing.value = false;
  if (fileInputRef.value) fileInputRef.value.value = "";
};

defineExpose({
  openFileDialog,
  importIcd,
  clear,
  getFile: () => selectedFile,
  importing,
});
</script>

<style scoped>
.interface-warning {
  margin-top: 6px;
  color: var(--el-color-warning);
  font-size: 12px;
  line-height: 1.5;
}
</style>
