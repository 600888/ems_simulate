<template>
  <div class="scl-import-wizard">
    <h3 class="wizard-title">{{ $t("scl.importSteps") }}</h3>

    <el-steps
      :active="currentStep"
      finish-status="success"
      align-center
      class="step-bar"
    >
      <el-step :title="$t('scl.stepSelectFile')" />
      <el-step :title="$t('scl.stepPreview')" />
      <el-step :title="$t('scl.stepOptions')" />
      <el-step :title="$t('scl.stepExecute')" />
    </el-steps>

    <div class="step-content">
      <!-- Step 1: 选择文件 -->
      <SclImportStepFile
        v-if="currentStep === 0"
        :files="fileList"
        @update:selected="selectedFile = $event"
        @upload="showUploadDialog = true"
      />

      <!-- Step 2: 预览测点 -->
      <SclImportStepPreview
        v-if="currentStep === 1"
        :preview-data="previewData"
        :loading="previewLoading"
      />

      <!-- Step 3: 配置选项 -->
      <SclImportStepOptions v-if="currentStep === 2" ref="optionsRef" />

      <!-- Step 4: 执行导入 -->
      <SclImportStepExecute
        v-if="currentStep === 3"
        :importing="importing"
        :result="importResult"
        :progress-percent="importProgress"
        :logs="importLogs"
      />
    </div>

    <div class="action-bar">
      <el-button v-if="currentStep > 0" @click="prevStep">{{
        $t("scl.prevStep")
      }}</el-button>
      <span v-else />
      <div>
        <el-button @click="$emit('close')">{{ $t("scl.cancel") }}</el-button>
        <el-button
          v-if="currentStep < 3"
          type="primary"
          :disabled="!canNext"
          @click="nextStep"
        >
          {{ $t("scl.nextStep") }}
        </el-button>
        <el-button
          v-if="currentStep === 3 && !importing && importResult"
          type="primary"
          @click="$emit('close')"
        >
          {{ $t("scl.finish") }}
        </el-button>
        <el-button
          v-if="currentStep === 2"
          type="primary"
          @click="startImport"
          :loading="importing"
        >
          {{ $t("scl.startImport") }}
        </el-button>
      </div>
    </div>

    <SclUploadDialog
      v-if="showUploadDialog"
      @close="showUploadDialog = false"
      @success="handleUploadSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { getSclFileList, previewSclFile, importSclFile } from "@/api/sclApi";
import type {
  SclFileInfo,
  SclPreviewData,
  SclImportResult,
} from "@/api/sclApi";
import { getChannelList } from "@/api/channelApi";
import { acquireAutoRefreshPause } from "@/composables/autoRefreshGate";
import SclImportStepFile from "./SclImportStepFile.vue";
import SclImportStepPreview from "./SclImportStepPreview.vue";
import SclImportStepOptions from "./SclImportStepOptions.vue";
import SclImportStepExecute from "./SclImportStepExecute.vue";
import SclUploadDialog from "./SclUploadDialog.vue";

const emit = defineEmits<{ (e: "close"): void }>();
const router = useRouter();

const currentStep = ref(0);
const fileList = ref<SclFileInfo[]>([]);
const selectedFile = ref("");
const showUploadDialog = ref(false);
const previewData = ref<SclPreviewData | null>(null);
const previewLoading = ref(false);
const optionsRef = ref<InstanceType<typeof SclImportStepOptions>>();
const importing = ref(false);
const importResult = ref<SclImportResult | null>(null);
const importProgress = ref(0);
const importLogs = ref<string[]>([]);
let releaseAutoRefreshPause: (() => void) | null = null;

const canNext = computed(() => {
  if (currentStep.value === 0) return !!selectedFile.value;
  if (currentStep.value === 1) return !!previewData.value;
  return true;
});

onMounted(async () => {
  fileList.value = await getSclFileList();
});

onUnmounted(() => {
  releaseAutoRefreshPause?.();
  releaseAutoRefreshPause = null;
});

async function nextStep() {
  if (currentStep.value === 0 && selectedFile.value) {
    previewLoading.value = true;
    try {
      previewData.value = await previewSclFile(selectedFile.value);
    } catch {
      previewData.value = null;
    } finally {
      previewLoading.value = false;
    }
  }
  currentStep.value++;
}

function prevStep() {
  currentStep.value--;
}

async function startImport() {
  importing.value = true;
  importResult.value = null;
  importProgress.value = 0;
  importLogs.value = [];
  currentStep.value = 3;
  // 暂停后台自动轮询，避免干扰导入
  releaseAutoRefreshPause?.();
  releaseAutoRefreshPause = acquireAutoRefreshPause("scl-import");

  const opts = optionsRef.value;
  if (!opts) {
    await resumeAndExit();
    return;
  }

  importLogs.value.push(`[${time()}] 解析 ICD 文件成功`);
  importProgress.value = 20;

  try {
    const result = await importSclFile({
      file_name: selectedFile.value,
      channel_id: opts.channelId,
      overwrite: opts.overwrite,
      import_goose: opts.importGoose,
      goose_interface: opts.gooseInterface,
      import_reports: opts.importReports,
    });
    importResult.value = result;
    importProgress.value = 100;
    importLogs.value.push(
      `[${time()}] ${result.success ? "✓ 导入完成" : "✗ 导入失败"}`,
    );

    // 导入成功后自动跳转到设备页面
    if (result.success) {
      try {
        const channels = await getChannelList();
        const channel = channels.find((c) => c.id === opts.channelId);
        if (channel) {
          importLogs.value.push(
            `[${time()}] 正在跳转到 ${channel.name} 设备页面...`,
          );
          setTimeout(() => {
            router.push(`/device/${channel.name}`);
          }, 2000);
        }
      } catch {
        // 忽略导航失败
      }
    }
  } catch {
    importResult.value = {
      success: false,
      total_points: 0,
      yc: 0,
      yx: 0,
      yk: 0,
      yt: 0,
      goose_count: 0,
      report_count: 0,
      errors: ["导入失败"],
      warnings: [],
    };
    importLogs.value.push(`[${time()}] ✗ 导入失败`);
  } finally {
    await resumeAndExit();
  }
}

async function resumeAndExit() {
  releaseAutoRefreshPause?.();
  releaseAutoRefreshPause = null;
  importing.value = false;
}

function handleUploadSuccess() {
  showUploadDialog.value = false;
  getSclFileList().then((list) => (fileList.value = list));
}

function time() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
</script>

<style scoped>
.scl-import-wizard {
  height: calc(
    100vh - var(--header-height) - var(--tags-height) - var(--footer-height)
  );
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  padding: 24px;
  background: var(--panel-bg);
  border-radius: var(--border-radius-base);
  box-shadow: var(--box-shadow-base);
  overflow: hidden;
}
.wizard-title {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: var(--text-primary);
}
.step-bar {
  margin-bottom: 28px;
}
.step-content {
  flex: 1;
  overflow: auto;
}
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
  margin-top: 16px;
  flex-shrink: 0;
}
</style>
