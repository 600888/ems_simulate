<script lang="ts" setup>
/**
 * IEC 61850 File Explorer Component
 *
 * Provides remote IED file directory browsing, file download/upload/delete,
 * and local cache management.
 * UI style consistent with GooseManager / ReportsManager.
 */

import { ref, computed, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { showError, showErrorOnce } from "@/api/http";
import type { UploadFile } from "element-plus";
import {
  Folder,
  Document,
  Download,
  Upload,
  Delete,
  Refresh,
  Files,
  ArrowLeft,
  Search,
} from "@element-plus/icons-vue";
import {
  getFileDirectory,
  downloadRemoteFile,
  uploadRemoteFile,
  deleteRemoteFile,
  getFileCacheList,
  clearFileCache,
  type FileEntry,
  type FileCacheEntry,
} from "@/api/channelApi";

const { t } = useI18n();

const props = defineProps<{
  channelId: number;
}>();

// ===== State =====
const loading = ref(false);
const currentDirectory = ref("");
const directoryStack = ref<{ path: string; name: string }[]>([]);
const entries = ref<FileEntry[]>([]);
const selectedEntry = ref<FileEntry | null>(null);
const downloading = ref(false);
const uploadDialogVisible = ref(false);
const uploading = ref(false);
const searchFilter = ref("");
const cacheList = ref<FileCacheEntry[]>([]);
const cacheDialogVisible = ref(false);
const uploadRef = ref();

// ===== Computed =====
const breadcrumbs = computed(() => {
  const crumbs = [{ path: "", name: "/" }];
  for (const item of directoryStack.value) {
    crumbs.push(item);
  }
  return crumbs;
});

const filteredEntries = computed(() => {
  if (!searchFilter.value) return entries.value;
  const keyword = searchFilter.value.toLowerCase();
  return entries.value.filter((e) => e.name.toLowerCase().includes(keyword));
});

const directoryEntries = computed(() =>
  filteredEntries.value.filter((e) => e.type === "directory"),
);
const fileEntries = computed(() =>
  filteredEntries.value.filter((e) => e.type === "file"),
);

const sortedEntries = computed(() => [
  ...directoryEntries.value,
  ...fileEntries.value,
]);

const selectedIsFile = computed(() => selectedEntry.value?.type === "file");

// ===== Directory browsing =====

async function loadDirectory(directory: string = "") {
  loading.value = true;
  try {
    const result = await getFileDirectory(props.channelId, directory);
    if (result) {
      entries.value = result.entries;
      currentDirectory.value = result.directory;
    } else {
      entries.value = [];
    }
  } catch (e) {
    console.error("Failed to load file directory:", e);
    entries.value = [];
  } finally {
    loading.value = false;
    selectedEntry.value = null;
  }
}

function navigateToDirectory(entry: FileEntry) {
  directoryStack.value.push({
    path: currentDirectory.value,
    name: entry.name,
  });
  loadDirectory(entry.full_path);
}

function navigateToBreadcrumb(path: string, index: number) {
  directoryStack.value = directoryStack.value.slice(0, index);
  loadDirectory(path);
}

function goBack() {
  if (directoryStack.value.length === 0) return;
  directoryStack.value.pop();
  const parentPath =
    directoryStack.value.length > 0
      ? directoryStack.value[directoryStack.value.length - 1].path
      : "";
  loadDirectory(parentPath);
}

function selectEntry(row: FileEntry) {
  selectedEntry.value = row;
}

function handleRowDblClick(entry: FileEntry) {
  if (entry.type === "directory") {
    navigateToDirectory(entry);
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return "-";
  return new Date(ts).toLocaleString();
}

// ===== File download =====

/** Decode Base64 to Uint8Array */
function base64ToUint8Array(base64: string): Uint8Array {
  const byteChars = atob(base64);
  const byteArray = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    byteArray[i] = byteChars.charCodeAt(i);
  }
  return byteArray;
}

/** Save using system save picker (File System Access API) */
async function saveWithPicker(
  fileName: string,
  data: Uint8Array,
): Promise<boolean> {
  const blob = new Blob([data]);
  try {
    const handle = await (window as any).showSaveFilePicker({
      suggestedName: fileName,
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return true;
  } catch (e: any) {
    // User cancelled
    if (e?.name === "AbortError") return false;
    throw e;
  }
}

/** Fallback: auto-download to default directory */
function saveWithFallback(fileName: string, data: Uint8Array) {
  const blob = new Blob([data]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function handleDownload() {
  if (!selectedEntry.value || selectedEntry.value.type === "directory") {
    ElMessage.warning(t("fileExplorer.selectFileFirst"));
    return;
  }

  downloading.value = true;
  try {
    const result = await downloadRemoteFile(
      props.channelId,
      selectedEntry.value.full_path,
    );
    if (result && result.data) {
      const byteArray = base64ToUint8Array(result.data);
      const fileName = selectedEntry.value.name;

      // Prefer system save dialog, fall back to auto-download
      if (window.showSaveFilePicker) {
        const saved = await saveWithPicker(fileName, byteArray);
        if (!saved) {
          // User cancelled save
          return;
        }
      } else {
        saveWithFallback(fileName, byteArray);
      }
      ElMessage.success(
        result.cached
          ? t("fileExplorer.downloadSuccessCached", { name: fileName })
          : t("fileExplorer.downloadSuccess", { name: fileName }),
      );
    } else {
      showErrorOnce(t("fileExplorer.downloadFailed"));
    }
  } catch (e) {
    console.error("File download failed:", e);
    showError(e, t("fileExplorer.downloadFailed"));
  } finally {
    downloading.value = false;
  }
}

// ===== File upload =====

async function handleUploadRequest(param: { file: File }) {
  uploading.value = true;
  try {
    const reader = new FileReader();
    const base64Promise = new Promise<string>((resolve) => {
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.split(",")[1] || result;
        resolve(base64);
      };
      reader.readAsDataURL(param.file);
    });

    const base64Data = await base64Promise;
    const remoteName = currentDirectory.value
      ? `${currentDirectory.value}/${param.file.name}`
      : `/${param.file.name}`;

    const success = await uploadRemoteFile(
      props.channelId,
      remoteName,
      base64Data,
    );
    if (success) {
      ElMessage.success(t("fileExplorer.uploadSuccess"));
      uploadDialogVisible.value = false;
      loadDirectory(currentDirectory.value);
    } else {
      showErrorOnce(t("fileExplorer.uploadFailed"));
    }
  } catch (e) {
    console.error("File upload failed:", e);
    showError(e, t("fileExplorer.uploadFailed"));
  } finally {
    uploading.value = false;
  }
}

function handleUploadExceed() {
  ElMessage.warning(t("fileExplorer.uploadSingleOnly"));
}

// ===== File delete =====

async function handleDelete() {
  if (!selectedEntry.value) {
    ElMessage.warning(t("fileExplorer.selectFileOrDir"));
    return;
  }

  try {
    await ElMessageBox.confirm(
      t("fileExplorer.deleteConfirm", { name: selectedEntry.value.name }),
      t("fileExplorer.deleteConfirmTitle"),
      {
        confirmButtonText: t("common.delete"),
        cancelButtonText: t("common.cancel"),
        type: "warning",
      },
    );

    const success = await deleteRemoteFile(
      props.channelId,
      selectedEntry.value.full_path,
    );
    if (success) {
      ElMessage.success(t("fileExplorer.deleted"));
      loadDirectory(currentDirectory.value);
    } else {
      showErrorOnce(t("fileExplorer.deleteFailed"));
    }
  } catch {
    // User cancelled
  }
}

// ===== Cache management =====

async function handleCacheManage() {
  cacheDialogVisible.value = true;
  cacheList.value = await getFileCacheList(props.channelId);
}

async function handleClearCache() {
  try {
    await ElMessageBox.confirm(
      t("fileExplorer.clearCacheConfirm"),
      t("fileExplorer.clearCacheTitle"),
      {
        confirmButtonText: t("common.clear"),
        cancelButtonText: t("common.cancel"),
        type: "warning",
      },
    );
    const count = await clearFileCache(props.channelId);
    ElMessage.success(t("fileExplorer.cacheCleared", { count }));
    cacheList.value = await getFileCacheList(props.channelId);
  } catch {
    // User cancelled
  }
}

// ===== Watch channelId =====
watch(
  () => props.channelId,
  (newId) => {
    if (newId) {
      directoryStack.value = [];
      selectedEntry.value = null;
      loadDirectory("");
    }
  },
);

// ===== Init =====
onMounted(() => {
  if (props.channelId) {
    loadDirectory("");
  }
});
</script>

<template>
  <div class="file-explorer">
    <!-- Header -->
    <div class="file-header">
      <h3>{{ $t("fileExplorer.title") }}</h3>
      <div class="header-actions">
        <el-button
          type="primary"
          :icon="Refresh"
          @click="loadDirectory(currentDirectory)"
          :loading="loading"
        >
          {{ $t("fileExplorer.refresh") }}
        </el-button>
        <el-button
          type="success"
          :icon="Download"
          @click="handleDownload"
          :loading="downloading"
          :disabled="!selectedIsFile"
        >
          {{ $t("fileExplorer.download") }}
        </el-button>
        <el-button :icon="Upload" @click="uploadDialogVisible = true">
          {{ $t("fileExplorer.upload") }}
        </el-button>
        <el-button
          type="danger"
          :icon="Delete"
          plain
          @click="handleDelete"
          :disabled="!selectedEntry"
        >
          {{ $t("fileExplorer.deleteAction") }}
        </el-button>
        <el-button :icon="Files" @click="handleCacheManage">
          {{ $t("fileExplorer.cacheManagement") }}
        </el-button>
      </div>
    </div>

    <!-- Toolbar: breadcrumb + back + search -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button
          :icon="ArrowLeft"
          :disabled="directoryStack.length === 0"
          @click="goBack"
          text
        >
          {{ $t("fileExplorer.back") }}
        </el-button>
        <div class="breadcrumb-bar">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item
              v-for="(crumb, idx) in breadcrumbs"
              :key="idx"
              @click="navigateToBreadcrumb(crumb.path, idx)"
            >
              <span class="breadcrumb-link">{{ crumb.name || "/" }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="searchFilter"
          :prefix-icon="Search"
          :placeholder="$t('fileExplorer.searchPlaceholder')"
          clearable
          style="width: 200px"
        />
      </div>
    </div>

    <!-- File list -->
    <div class="file-body" v-loading="loading">
      <el-table
        :data="sortedEntries"
        highlight-current-row
        stripe
        border
        style="width: 100%"
        height="100%"
        @row-click="selectEntry"
        @row-dblclick="handleRowDblClick"
      >
        <el-table-column :label="$t('fileExplorer.colName')" min-width="280">
          <template #default="{ row }">
            <div class="file-name-cell">
              <el-icon
                :size="18"
                :color="row.type === 'directory' ? '#e6a23c' : '#409eff'"
              >
                <Folder v-if="row.type === 'directory'" />
                <Document v-else />
              </el-icon>
              <span :class="{ 'dir-name': row.type === 'directory' }">{{
                row.name
              }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('fileExplorer.colSize')"
          width="100"
          prop="size_human"
        />
        <el-table-column
          :label="$t('fileExplorer.colType')"
          width="80"
          align="center"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.type === 'directory' ? 'warning' : 'info'"
              size="small"
            >
              {{
                row.type === "directory"
                  ? $t("fileExplorer.directory")
                  : $t("fileExplorer.file")
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('fileExplorer.colModified')" width="180">
          <template #default="{ row }">
            {{ formatTime(row.last_modified) }}
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('fileExplorer.colPath')"
          min-width="200"
          prop="full_path"
          show-overflow-tooltip
        />
        <el-table-column
          :label="$t('fileExplorer.colOperations')"
          width="140"
          fixed="right"
          align="center"
        >
          <template #default="{ row }">
            <el-button-group>
              <el-button
                type="primary"
                size="small"
                :icon="Download"
                :disabled="row.type === 'directory'"
                @click.stop="
                  selectedEntry = row;
                  handleDownload();
                "
              />
              <el-button
                type="danger"
                size="small"
                :icon="Delete"
                @click.stop="
                  selectedEntry = row;
                  handleDelete();
                "
              />
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && entries.length === 0"
        :description="$t('fileExplorer.emptyDir')"
      />
    </div>

    <!-- Upload dialog -->
    <el-dialog
      v-model="uploadDialogVisible"
      :title="$t('fileExplorer.uploadTitle')"
      width="500px"
      destroy-on-close
    >
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :limit="1"
        :on-exceed="handleUploadExceed"
        :http-request="handleUploadRequest"
        drag
      >
        <el-icon :size="40" class="upload-icon"><Upload /></el-icon>
        <div
          class="el-upload__text"
          v-html="$t('fileExplorer.uploadDropText')"
        />
        <template #tip>
          <div class="el-upload__tip">{{ $t("fileExplorer.uploadTip") }}</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">{{
          $t("common.cancel")
        }}</el-button>
        <el-button
          type="primary"
          @click="uploadRef?.submit()"
          :loading="uploading"
          >{{ $t("fileExplorer.upload") }}</el-button
        >
      </template>
    </el-dialog>

    <!-- Cache management dialog -->
    <el-dialog
      v-model="cacheDialogVisible"
      :title="$t('fileExplorer.cacheTitle')"
      width="600px"
      destroy-on-close
    >
      <el-table :data="cacheList" border stripe size="small" max-height="400">
        <el-table-column
          :label="$t('fileExplorer.colRemotePath')"
          prop="remote_path"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column :label="$t('fileExplorer.colFileSize')" width="100">
          <template #default="{ row }">
            {{ (row.file_size / 1024).toFixed(1) }} KB
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('fileExplorer.colDownloadTime')"
          width="180"
        >
          <template #default="{ row }">
            {{ formatTime(row.download_time) }}
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="cacheDialogVisible = false">{{
          $t("fileExplorer.close")
        }}</el-button>
        <el-button type="danger" @click="handleClearCache">{{
          $t("fileExplorer.clearCache")
        }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="scss" scoped>
.file-explorer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--panel-bg);
  border-radius: 4px;
}

// ===== Header (consistent with ReportsManager) =====
.file-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);

  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }

  .header-actions {
    display: flex;
    gap: 8px;

    @include bp.respond-to("small") {
      flex-wrap: wrap;
    }
  }
}

// ===== Toolbar =====
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  gap: 12px;
  border-bottom: 1px solid #f0f0f0;

  @include bp.respond-to("small") {
    flex-wrap: wrap;
  }

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.breadcrumb-bar {
  .breadcrumb-link {
    cursor: pointer;
    color: var(--color-primary, #409eff);
    transition: color 0.2s;

    &:hover {
      color: var(--el-color-primary-dark-2, #337ecc);
    }
  }
}

// ===== File list body =====
.file-body {
  flex: 1;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;

  .el-table {
    flex: 1;
  }

  .el-empty {
    padding: 48px 0;
  }
}

// ===== File name cell =====
.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;

  .dir-name {
    color: var(--color-primary, #409eff);
    font-weight: 500;
    cursor: pointer;

    &:hover {
      text-decoration: underline;
    }
  }
}

// ===== Upload area =====
.upload-icon {
  color: #c0c4cc;
  margin-bottom: 8px;
}

// ===== Table center (consistent with GooseManager) =====
::deep(.el-table thead th .cell) {
  white-space: nowrap;
}

::deep(.el-table .cell) {
  text-align: center;
}

// ===== Small screen adaptation =====
@include bp.respond-to("small") {
  .file-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>
