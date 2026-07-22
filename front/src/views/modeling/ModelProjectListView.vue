<template>
  <div class="model-page">
    <section class="page-heading">
      <div>
        <div class="eyebrow">IEC 61850 MODELING</div>
        <h1>模型工程</h1>
        <p>从零建立、维护并校验 ICD / CID / SCD 模型。</p>
      </div>
      <div class="heading-actions">
        <el-button @click="router.push('/scl/manager')">
          <el-icon><FolderOpened /></el-icon>SCL 文件
        </el-button>
        <el-button @click="openImportDialog">
          <el-icon><UploadFilled /></el-icon>导入 ICD/CID
        </el-button>
        <el-button type="primary" @click="router.push('/scl/modeling/new')">
          <el-icon><Plus /></el-icon>从 0 新建模型
        </el-button>
      </div>
    </section>

    <section class="filter-card glass-card">
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="搜索工程名称或编码"
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
        placeholder="全部状态"
        @change="loadProjects"
      >
        <el-option label="草稿" value="DRAFT" />
        <el-option label="校验通过" value="VALID" />
        <el-option label="已发布" value="PUBLISHED" />
        <el-option label="已归档" value="ARCHIVED" />
      </el-select>
      <el-button @click="loadProjects"
        ><el-icon><Refresh /></el-icon>刷新</el-button
      >
      <span class="result-count">共 {{ total }} 个工程</span>
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
              <el-button text circle aria-label="工程操作" @click.stop
                ><el-icon><MoreFilled /></el-icon
              ></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openProject(project.id)"
                    >打开工程</el-dropdown-item
                  >
                  <el-dropdown-item
                    divided
                    class="danger-item"
                    @click="removeProject(project)"
                  >
                    删除工程
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <p class="description">{{ project.description || "暂无工程描述" }}</p>
          <div class="project-meta">
            <el-tag size="small" effect="plain">{{ project.file_type }}</el-tag>
            <el-tag size="small" :type="statusMeta(project.status).type">
              {{ statusMeta(project.status).label }}
            </el-tag>
            <span>{{ project.node_count }} 个节点</span>
          </div>
          <div class="card-footer">
            <span>版本 r{{ project.revision }}</span>
            <span>{{ formatDate(project.updated_at) }} 更新</span>
          </div>
        </article>
      </div>

      <el-empty v-else description="还没有模型工程">
        <el-button type="primary" @click="router.push('/scl/modeling/new')"
          >从 0 新建第一个模型</el-button
        >
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
      title="导入 IEC 61850 模型"
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
        <div class="el-upload__text">拖入 ICD/CID，或<em>点击选择</em></div>
      </el-upload>
      <div v-if="importDialog.previewing" class="import-job-progress">
        <el-progress
          :percentage="importDialog.progress"
          :status="importDialog.progress >= 100 ? 'success' : undefined"
        />
        <span>后台解析中，可关闭或取消而不创建工程</span>
        <el-button size="small" text type="danger" @click="cancelImportPreview"
          >取消解析</el-button
        >
      </div>
      <div v-if="importDialog.preview" class="import-preview">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="文件类型">{{
            importDialog.preview.project.file_type
          }}</el-descriptions-item>
          <el-descriptions-item label="IED">{{
            importDialog.preview.project.ied_name || "--"
          }}</el-descriptions-item>
          <el-descriptions-item label="节点数">{{
            importDialog.preview.summary.node_count
          }}</el-descriptions-item>
          <el-descriptions-item label="保真扩展">{{
            importDialog.preview.summary.extension_count
          }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="importDialog.preview.summary.extension_count > 0"
          type="warning"
          :closable="false"
          show-icon
          :title="`发现 ${importDialog.preview.summary.extension_count} 个保真扩展片段`"
          description="这些内容通常来自厂商 Private 或当前工具尚未结构化支持的 XML。导入后会保留原文并默认只读，正常情况下不会影响发布；若后续确认无法原位回写，系统会明确标记为有损风险并阻止发布。"
        />
        <el-form label-position="top" class="import-form">
          <el-form-item label="工程名称"
            ><el-input v-model="importDialog.name"
          /></el-form-item>
          <el-form-item label="工程编码"
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
        <el-button @click="importDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="importDialog.importing"
          :disabled="
            !importDialog.file ||
            !importDialog.preview ||
            !importDialog.code.trim()
          "
          @click="importModel"
          >导入并打开</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
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
      DRAFT: { label: "草稿", type: "info" as const },
      VALID: { label: "校验通过", type: "success" as const },
      PUBLISHED: { label: "已发布", type: "primary" as const },
      ARCHIVED: { label: "已归档", type: "warning" as const },
    }[status] || { label: status, type: "info" as const }
  );
}

function formatDate(value: string) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
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
      `工程“${project.name}”及其全部模型节点将被永久删除。`,
      "删除模型工程",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
      },
    );
    await modelingApi.deleteProject(project.id);
    ElMessage.success("模型工程已删除");
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
      ElMessage.error(job.error || "SCL 后台解析失败");
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
    ElMessage.success(`已导入 ${result.summary.node_count} 个模型节点`);
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
