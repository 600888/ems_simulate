<template>
  <div class="model-page">
    <section class="page-heading">
      <div>
        <div class="eyebrow">IEC 61850 MODELING</div>
        <h1>{{ $t("modeling.projectList.title") }}</h1>
        <p>{{ $t("modeling.projectList.subtitle") }}</p>
      </div>
      <div class="heading-actions">
        <el-button @click="router.push('/scl/manager')">
          <el-icon><FolderOpened /></el-icon
          >{{ $t("modeling.projectList.sclFiles") }}
        </el-button>
        <el-button @click="openImportDialog">
          <el-icon><UploadFilled /></el-icon
          >{{ $t("modeling.projectList.importIcd") }}
        </el-button>
        <el-button type="primary" @click="router.push('/scl/modeling/new')">
          <el-icon><Plus /></el-icon>{{ $t("modeling.projectList.newProject") }}
        </el-button>
      </div>
    </section>

    <section class="filter-card glass-card">
      <el-input
        v-model="filters.keyword"
        clearable
        :placeholder="$t('modeling.projectList.searchPlaceholder')"
        class="keyword-input"
        @keyup.enter="loadProjects"
        @clear="loadProjects"
      >
        <template #prefix
          ><el-icon><Search /></el-icon
        ></template>
      </el-input>
      <el-select
        v-model="filters.status"
        clearable
        :placeholder="$t('modeling.projectList.allStatuses')"
        @change="loadProjects"
      >
        <el-option
          :label="$t('modeling.projectList.statusDraft')"
          value="DRAFT"
        />
        <el-option
          :label="$t('modeling.projectList.statusValid')"
          value="VALID"
        />
        <el-option
          :label="$t('modeling.projectList.statusPublished')"
          value="PUBLISHED"
        />
        <el-option
          :label="$t('modeling.projectList.statusArchived')"
          value="ARCHIVED"
        />
      </el-select>
      <el-button @click="loadProjects"
        ><el-icon><Refresh /></el-icon
        >{{ $t("modeling.projectList.refresh") }}</el-button
      >
      <span class="result-count">{{
        $t("modeling.projectList.totalProjects", { count: total })
      }}</span>
    </section>

    <div v-loading="loading" class="project-area">
      <div v-if="projects.length" class="project-grid">
        <article
          v-for="project in projects"
          :key="project.id"
          class="project-card glass-card"
          @click="openProject(project.id)"
        >
          <div class="card-top">
            <div class="project-icon">
              <el-icon><Connection /></el-icon>
            </div>
            <div class="project-title">
              <h3>{{ project.name }}</h3>
              <code>{{ project.code }}</code>
            </div>
            <el-dropdown trigger="click" @click.stop>
              <el-button
                text
                circle
                :aria-label="$t('modeling.projectList.projectActions')"
                @click.stop
                ><el-icon><MoreFilled /></el-icon
              ></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openProject(project.id)">{{
                    $t("modeling.projectList.openProject")
                  }}</el-dropdown-item>
                  <el-dropdown-item
                    divided
                    class="danger-item"
                    @click="removeProject(project)"
                  >
                    {{ $t("modeling.projectList.deleteProject") }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <p class="description">
            {{
              project.description || $t("modeling.projectList.noDescription")
            }}
          </p>
          <div class="project-meta">
            <el-tag size="small" effect="plain">{{ project.file_type }}</el-tag>
            <el-tag size="small" :type="statusMeta(project.status).type">
              {{ statusMeta(project.status).label }}
            </el-tag>
            <span>{{
              $t("modeling.projectList.nodeCount", {
                count: project.node_count,
              })
            }}</span>
          </div>
          <div class="card-footer">
            <span>{{
              $t("modeling.projectList.revision", { rev: project.revision })
            }}</span>
            <span>{{
              $t("modeling.projectList.updated", {
                date: formatDate(project.updated_at),
              })
            }}</span>
          </div>
        </article>
      </div>

      <el-empty v-else :description="$t('modeling.projectList.noProjects')">
        <el-button type="primary" @click="router.push('/scl/modeling/new')">{{
          $t("modeling.projectList.createFirst")
        }}</el-button>
      </el-empty>
    </div>

    <el-pagination
      v-if="total > filters.pageSize"
      v-model:current-page="filters.page"
      :page-size="filters.pageSize"
      :total="total"
      layout="prev, pager, next"
      @current-change="loadProjects"
    />

    <el-dialog
      v-model="importDialog.visible"
      :title="$t('modeling.projectList.importTitle')"
      width="620px"
      destroy-on-close
    >
      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".icd,.cid,.scd,.iid,.sed,.ssd,.xml"
        :on-change="handleImportFile"
        :on-remove="clearImportFile"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div
          class="el-upload__text"
          v-html="$t('modeling.projectList.importDrop')"
        ></div>
      </el-upload>
      <div v-if="importDialog.previewing" class="import-job-progress">
        <el-progress
          :percentage="importDialog.progress"
          :status="importDialog.progress >= 100 ? 'success' : undefined"
        />
        <span>{{ $t("modeling.projectList.importParsing") }}</span>
        <el-button
          size="small"
          text
          type="danger"
          @click="cancelImportPreview"
          >{{ $t("modeling.projectList.cancelParse") }}</el-button
        >
      </div>
      <div v-if="importDialog.preview" class="import-preview">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="$t('modeling.projectList.fileType')">{{
            importDialog.preview.project.file_type
          }}</el-descriptions-item>
          <el-descriptions-item label="IED">{{
            importDialog.preview.project.ied_name || "--"
          }}</el-descriptions-item>
          <el-descriptions-item
            :label="$t('modeling.projectList.nodeCountLabel')"
            >{{ importDialog.preview.summary.node_count }}</el-descriptions-item
          >
          <el-descriptions-item
            :label="$t('modeling.projectList.lossyExtensions')"
            >{{
              importDialog.preview.summary.extension_count
            }}</el-descriptions-item
          >
        </el-descriptions>
        <el-alert
          v-if="importDialog.preview.summary.extension_count > 0"
          type="warning"
          :closable="false"
          show-icon
          :title="
            $t('modeling.projectList.extensionCount', {
              count: importDialog.preview.summary.extension_count,
            })
          "
          :description="$t('modeling.projectList.extensionTip')"
        />
        <el-form label-position="top" class="import-form">
          <el-form-item :label="$t('modeling.projectList.projectName')"
            ><el-input v-model="importDialog.name"
          /></el-form-item>
          <el-form-item :label="$t('modeling.projectList.projectCode')"
            ><el-input v-model="importDialog.code"
          /></el-form-item>
        </el-form>
        <el-alert
          v-for="warning in importDialog.preview.warnings"
          :key="warning.code"
          type="warning"
          :closable="false"
          show-icon
          :title="warning.message"
        />
      </div>
      <template #footer>
        <el-button @click="importDialog.visible = false">{{
          $t("common.cancel")
        }}</el-button>
        <el-button
          type="primary"
          :loading="importDialog.importing"
          :disabled="
            !importDialog.file ||
            !importDialog.preview ||
            !importDialog.code.trim()
          "
          @click="importModel"
          >{{ $t("modeling.projectList.importAndOpen") }}</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  Connection,
  FolderOpened,
  MoreFilled,
  Plus,
  Refresh,
  Search,
  UploadFilled,
} from "@element-plus/icons-vue";
import { modelingApi, type ImportPreview } from "@/api/modelingApi";
import type { ModelProject } from "@/types/modeling";
import { currentLocale } from "@/composables/useAppSettings";

const { t } = useI18n();
const router = useRouter();
const loading = ref(false);
const projects = ref<ModelProject[]>([]);
const total = ref(0);
const filters = reactive({ keyword: "", status: "", page: 1, pageSize: 20 });
let previewSequence = 0;
const importDialog = reactive<{
  visible: boolean;
  importing: boolean;
  previewing: boolean;
  progress: number;
  jobId?: string;
  file?: File;
  preview?: ImportPreview;
  code: string;
  name: string;
}>({
  visible: false,
  importing: false,
  previewing: false,
  progress: 0,
  code: "",
  name: "",
});

function statusMeta(status: ModelProject["status"]) {
  return (
    {
      DRAFT: {
        label: t("modeling.projectList.statusDraft"),
        type: "info" as const,
      },
      VALID: {
        label: t("modeling.projectList.statusValid"),
        type: "success" as const,
      },
      PUBLISHED: {
        label: t("modeling.projectList.statusPublished"),
        type: "primary" as const,
      },
      ARCHIVED: {
        label: t("modeling.projectList.statusArchived"),
        type: "warning" as const,
      },
    }[status] || { label: status, type: "info" as const }
  );
}

function formatDate(value: string) {
  if (!value) return "--";
  return new Intl.DateTimeFormat(currentLocale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function loadProjects() {
  loading.value = true;
  try {
    const result = await modelingApi.listProjects({
      keyword: filters.keyword,
      status: filters.status,
      page: filters.page,
      page_size: filters.pageSize,
    });
    projects.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

function openProject(projectId: string) {
  router.push(`/scl/modeling/${projectId}`);
}

async function removeProject(project: ModelProject) {
  try {
    await ElMessageBox.confirm(
      t("modeling.projectList.deleteConfirm", { name: project.name }),
      t("modeling.projectList.deleteTitle"),
      {
        type: "warning",
        confirmButtonText: t("common.confirmDelete"),
        cancelButtonText: t("common.cancel"),
      },
    );
    await modelingApi.deleteProject(project.id);
    ElMessage.success(t("modeling.projectList.deleted"));
    await loadProjects();
  } catch (error) {
    if (error !== "cancel" && error !== "close") throw error;
  }
}

function openImportDialog() {
  Object.assign(importDialog, {
    visible: true,
    importing: false,
    previewing: false,
    progress: 0,
    jobId: undefined,
    file: undefined,
    preview: undefined,
    code: "",
    name: "",
  });
}

function clearImportFile() {
  void cancelImportPreview();
  Object.assign(importDialog, {
    file: undefined,
    preview: undefined,
    code: "",
    name: "",
    progress: 0,
  });
}

async function handleImportFile(upload: UploadFile) {
  if (!upload.raw) return;
  await cancelImportPreview();
  const sequence = ++previewSequence;
  importDialog.file = upload.raw;
  importDialog.preview = undefined;
  importDialog.previewing = true;
  importDialog.progress = 0;
  try {
    let job = await modelingApi.startImportPreviewJob(upload.raw);
    importDialog.jobId = job.id;
    while (
      sequence === previewSequence &&
      ["QUEUED", "RUNNING", "CANCELLING"].includes(job.status)
    ) {
      importDialog.progress = job.progress;
      await new Promise((resolve) => window.setTimeout(resolve, 150));
      job = await modelingApi.getJob<ImportPreview>(job.id);
    }
    importDialog.progress = job.progress;
    if (sequence !== previewSequence) return;
    if (job.status === "COMPLETED" && job.result) {
      importDialog.preview = job.result;
      importDialog.code = job.result.project.code;
      importDialog.name = job.result.project.name;
    } else if (job.status === "FAILED") {
      ElMessage.error(job.error || t("modeling.projectList.parseFailed"));
    }
  } finally {
    if (sequence === previewSequence) {
      importDialog.previewing = false;
      importDialog.jobId = undefined;
    }
  }
}

async function cancelImportPreview() {
  previewSequence += 1;
  const jobId = importDialog.jobId;
  if (!jobId) return;
  importDialog.jobId = undefined;
  await modelingApi.cancelJob(jobId);
  importDialog.previewing = false;
}

async function importModel() {
  if (!importDialog.file || !importDialog.preview) return;
  importDialog.importing = true;
  try {
    const result = await modelingApi.importProject(
      importDialog.file,
      importDialog.code.trim(),
      importDialog.name.trim(),
    );
    ElMessage.success(
      t("modeling.projectList.imported", { count: result.summary.node_count }),
    );
    importDialog.visible = false;
    await router.push(`/scl/modeling/${result.project.id}`);
  } finally {
    importDialog.importing = false;
  }
}

onMounted(loadProjects);
</script>

<style scoped lang="scss">
.model-page {
  height: 100%;
  min-height: 0;
  flex: 1;
  padding: 20px 24px;
  overflow: auto;
  box-sizing: border-box;
  background: var(--bg-main);
}

.page-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 18px;
}

.eyebrow {
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.4px;
}
h1 {
  margin: 4px 0;
  color: var(--text-primary);
  font-size: 26px;
}
.page-heading p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}
.heading-actions {
  display: flex;
  gap: 10px;
}
.import-preview {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}
.import-job-progress {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 6px 12px;
  margin-top: 14px;
  color: var(--text-secondary);
  font-size: 12px;
}
.import-job-progress .el-progress {
  grid-column: 1 / -1;
}
.import-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.import-form :deep(.el-form-item) {
  margin-bottom: 0;
}
.filter-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 18px;
}
.keyword-input {
  width: 320px;
}
.filter-card .el-select {
  width: 140px;
}
.result-count {
  margin-left: auto;
  color: var(--text-secondary);
  font-size: 13px;
}
.project-area {
  min-height: 300px;
}
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
  gap: 16px;
}
.project-card {
  padding: 18px;
  cursor: pointer;
  transition:
    transform 0.18s,
    box-shadow 0.18s,
    border-color 0.18s;
}
.project-card:hover {
  transform: translateY(-2px);
  border-color: rgba(59, 130, 246, 0.35);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.09);
}
.card-top {
  display: flex;
  align-items: center;
  gap: 12px;
}
.project-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  color: var(--color-primary);
  background: var(--item-active-bg);
  border-radius: 11px;
  font-size: 21px;
}
.project-title {
  min-width: 0;
  flex: 1;
}
.project-title h3 {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.project-title code {
  color: var(--text-secondary);
  font-size: 12px;
}
.description {
  min-height: 40px;
  margin: 16px 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}
.project-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 13px;
  border-top: 1px solid var(--sidebar-border);
  color: var(--text-secondary);
  font-size: 12px;
}
.el-pagination {
  justify-content: center;
  margin-top: 20px;
}
:deep(.danger-item) {
  color: var(--color-danger);
}

@container (max-width: 900px) {
  .model-page {
    padding: 16px;
  }
  .page-heading {
    align-items: flex-start;
    gap: 14px;
  }
  .filter-card {
    flex-wrap: wrap;
  }
  .keyword-input {
    width: 100%;
  }
  .result-count {
    margin-left: 0;
  }
}
</style>
