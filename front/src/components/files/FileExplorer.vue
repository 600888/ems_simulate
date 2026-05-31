<script lang="ts" setup>
/**
 * IEC 61850 文件浏览器组件
 *
 * 提供远程 IED 文件目录浏览、文件下载/上传/删除、本地缓存管理功能。
 * UI 风格与 GooseManager / ReportsManager 保持一致。
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'
import {
  Folder, Document, Download, Upload, Delete, Refresh, Files,
  ArrowLeft, Search,
} from '@element-plus/icons-vue'
import {
  getFileDirectory,
  downloadRemoteFile,
  uploadRemoteFile,
  deleteRemoteFile,
  getFileCacheList,
  clearFileCache,
  type FileEntry,
  type FileCacheEntry,
} from '@/api/channelApi'

const { t } = useI18n()

const props = defineProps<{
  channelId: number
}>()

// ===== 状态 =====
const loading = ref(false)
const currentDirectory = ref('')
const directoryStack = ref<{ path: string; name: string }[]>([])
const entries = ref<FileEntry[]>([])
const selectedEntry = ref<FileEntry | null>(null)
const downloading = ref(false)
const uploadDialogVisible = ref(false)
const uploading = ref(false)
const searchFilter = ref('')
const cacheList = ref<FileCacheEntry[]>([])
const cacheDialogVisible = ref(false)
const uploadRef = ref()

// ===== 计算属性 =====
const breadcrumbs = computed(() => {
  const crumbs = [{ path: '', name: '/' }]
  for (const item of directoryStack.value) {
    crumbs.push(item)
  }
  return crumbs
})

const filteredEntries = computed(() => {
  if (!searchFilter.value) return entries.value
  const keyword = searchFilter.value.toLowerCase()
  return entries.value.filter(e => e.name.toLowerCase().includes(keyword))
})

const directoryEntries = computed(() => filteredEntries.value.filter(e => e.type === 'directory'))
const fileEntries = computed(() => filteredEntries.value.filter(e => e.type === 'file'))

const sortedEntries = computed(() => [...directoryEntries.value, ...fileEntries.value])

const selectedIsFile = computed(() => selectedEntry.value?.type === 'file')

// ===== 目录浏览 =====

async function loadDirectory(directory: string = '') {
  loading.value = true
  try {
    const result = await getFileDirectory(props.channelId, directory)
    if (result) {
      entries.value = result.entries
      currentDirectory.value = result.directory
    } else {
      entries.value = []
    }
  } catch (e) {
    console.error('加载文件目录失败:', e)
    entries.value = []
  } finally {
    loading.value = false
    selectedEntry.value = null
  }
}

function navigateToDirectory(entry: FileEntry) {
  directoryStack.value.push({
    path: currentDirectory.value,
    name: entry.name,
  })
  loadDirectory(entry.full_path)
}

function navigateToBreadcrumb(path: string, index: number) {
  directoryStack.value = directoryStack.value.slice(0, index)
  loadDirectory(path)
}

function goBack() {
  if (directoryStack.value.length === 0) return
  directoryStack.value.pop()
  const parentPath = directoryStack.value.length > 0
    ? directoryStack.value[directoryStack.value.length - 1].path
    : ''
  loadDirectory(parentPath)
}

function selectEntry(row: FileEntry) {
  selectedEntry.value = row
}

function handleRowDblClick(entry: FileEntry) {
  if (entry.type === 'directory') {
    navigateToDirectory(entry)
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleString()
}

// ===== 文件下载 =====

/** 将 Base64 解码为 Uint8Array */
function base64ToUint8Array(base64: string): Uint8Array {
  const byteChars = atob(base64)
  const byteArray = new Uint8Array(byteChars.length)
  for (let i = 0; i < byteChars.length; i++) {
    byteArray[i] = byteChars.charCodeAt(i)
  }
  return byteArray
}

/** 使用系统保存对话框写入文件（File System Access API） */
async function saveWithPicker(fileName: string, data: Uint8Array): Promise<boolean> {
  const blob = new Blob([data])
  try {
    const handle = await (window as any).showSaveFilePicker({
      suggestedName: fileName,
    })
    const writable = await handle.createWritable()
    await writable.write(blob)
    await writable.close()
    return true
  } catch (e: any) {
    // 用户取消选择
    if (e?.name === 'AbortError') return false
    throw e
  }
}

/** 回退方式：自动下载到默认目录 */
function saveWithFallback(fileName: string, data: Uint8Array) {
  const blob = new Blob([data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function handleDownload() {
  if (!selectedEntry.value || selectedEntry.value.type === 'directory') {
    ElMessage.warning('请选择一个文件进行下载')
    return
  }

  downloading.value = true
  try {
    const result = await downloadRemoteFile(props.channelId, selectedEntry.value.full_path)
    if (result && result.data) {
      const byteArray = base64ToUint8Array(result.data)
      const fileName = selectedEntry.value.name

      // 优先使用系统保存对话框，不支持时回退到自动下载
      if (window.showSaveFilePicker) {
        const saved = await saveWithPicker(fileName, byteArray)
        if (!saved) {
          // 用户取消了保存
          return
        }
      } else {
        saveWithFallback(fileName, byteArray)
      }
      ElMessage.success(`文件下载成功: ${fileName}${result.cached ? ' (缓存)' : ''}`)
    } else {
      ElMessage.error('文件下载失败')
    }
  } catch (e) {
    console.error('文件下载失败:', e)
    ElMessage.error('文件下载失败')
  } finally {
    downloading.value = false
  }
}

// ===== 文件上传 =====

async function handleUploadRequest(param: { file: File }) {
  uploading.value = true
  try {
    const reader = new FileReader()
    const base64Promise = new Promise<string>((resolve) => {
      reader.onload = () => {
        const result = reader.result as string
        const base64 = result.split(',')[1] || result
        resolve(base64)
      }
      reader.readAsDataURL(param.file)
    })

    const base64Data = await base64Promise
    const remoteName = currentDirectory.value
      ? `${currentDirectory.value}/${param.file.name}`
      : `/${param.file.name}`

    const success = await uploadRemoteFile(props.channelId, remoteName, base64Data)
    if (success) {
      ElMessage.success('文件上传成功')
      uploadDialogVisible.value = false
      loadDirectory(currentDirectory.value)
    } else {
      ElMessage.error('文件上传失败')
    }
  } catch (e) {
    console.error('文件上传失败:', e)
    ElMessage.error('文件上传失败')
  } finally {
    uploading.value = false
  }
}

function handleUploadExceed() {
  ElMessage.warning('一次只能上传一个文件')
}

// ===== 文件删除 =====

async function handleDelete() {
  if (!selectedEntry.value) {
    ElMessage.warning('请选择一个文件或目录')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定删除远程文件 "${selectedEntry.value.name}" 吗？此操作不可撤销。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )

    const success = await deleteRemoteFile(props.channelId, selectedEntry.value.full_path)
    if (success) {
      ElMessage.success('文件已删除')
      loadDirectory(currentDirectory.value)
    } else {
      ElMessage.error('删除失败')
    }
  } catch {
    // 用户取消
  }
}

// ===== 缓存管理 =====

async function handleCacheManage() {
  cacheDialogVisible.value = true
  cacheList.value = await getFileCacheList(props.channelId)
}

async function handleClearCache() {
  try {
    await ElMessageBox.confirm('确定清空所有本地缓存文件吗？', '确认', {
      confirmButtonText: '清空', cancelButtonText: '取消', type: 'warning',
    })
    const count = await clearFileCache(props.channelId)
    ElMessage.success(`已清理 ${count} 个缓存文件`)
    cacheList.value = await getFileCacheList(props.channelId)
  } catch {
    // 用户取消
  }
}

// ===== 监听 channelId =====
watch(
  () => props.channelId,
  (newId) => {
    if (newId) {
      directoryStack.value = []
      selectedEntry.value = null
      loadDirectory('')
    }
  },
)

// ===== 初始化 =====
onMounted(() => {
  if (props.channelId) {
    loadDirectory('')
  }
})
</script>

<template>
  <div class="file-explorer">
    <!-- 头部 -->
    <div class="file-header">
      <h3>文件浏览器</h3>
      <div class="header-actions">
        <el-button type="primary" :icon="Refresh" @click="loadDirectory(currentDirectory)" :loading="loading">
          刷新
        </el-button>
        <el-button type="success" :icon="Download" @click="handleDownload"
          :loading="downloading" :disabled="!selectedIsFile">
          下载
        </el-button>
        <el-button :icon="Upload" @click="uploadDialogVisible = true">
          上传
        </el-button>
        <el-button type="danger" :icon="Delete" plain @click="handleDelete"
          :disabled="!selectedEntry">
          删除
        </el-button>
        <el-button :icon="Files" @click="handleCacheManage">
          缓存管理
        </el-button>
      </div>
    </div>

    <!-- 工具条：面包屑 + 返回 + 搜索 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button :icon="ArrowLeft" :disabled="directoryStack.length === 0" @click="goBack" text>
          返回
        </el-button>
        <div class="breadcrumb-bar">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item
              v-for="(crumb, idx) in breadcrumbs"
              :key="idx"
              @click="navigateToBreadcrumb(crumb.path, idx)"
            >
              <span class="breadcrumb-link">{{ crumb.name || '/' }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="searchFilter"
          :prefix-icon="Search"
          placeholder="搜索文件名"
          clearable
          style="width: 200px"
        />
      </div>
    </div>

    <!-- 文件列表 -->
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
        <el-table-column label="名称" min-width="280">
          <template #default="{ row }">
            <div class="file-name-cell">
              <el-icon :size="18" :color="row.type === 'directory' ? '#e6a23c' : '#409eff'">
                <Folder v-if="row.type === 'directory'" />
                <Document v-else />
              </el-icon>
              <span :class="{ 'dir-name': row.type === 'directory' }">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100" prop="size_human" />
        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.type === 'directory' ? 'warning' : 'info'" size="small">
              {{ row.type === 'directory' ? '目录' : '文件' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="修改时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.last_modified) }}
          </template>
        </el-table-column>
        <el-table-column label="路径" min-width="200" prop="full_path" show-overflow-tooltip />
        <el-table-column label="操作" width="140" fixed="right" align="center">
          <template #default="{ row }">
            <el-button-group>
              <el-button
                type="primary"
                size="small"
                :icon="Download"
                :disabled="row.type === 'directory'"
                @click.stop="selectedEntry = row; handleDownload()"
              />
              <el-button
                type="danger"
                size="small"
                :icon="Delete"
                @click.stop="selectedEntry = row; handleDelete()"
              />
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && entries.length === 0"
        description="空目录或 IED 不支持文件服务"
      />
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadDialogVisible" title="上传文件到 IED" width="500px" destroy-on-close>
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :limit="1"
        :on-exceed="handleUploadExceed"
        :http-request="handleUploadRequest"
        drag
      >
        <el-icon :size="40" class="upload-icon"><Upload /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或 <em>点击选择文件</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">文件将上传至 IED 当前目录</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="uploadRef?.submit()" :loading="uploading">上传</el-button>
      </template>
    </el-dialog>

    <!-- 缓存管理对话框 -->
    <el-dialog v-model="cacheDialogVisible" title="本地缓存管理" width="600px" destroy-on-close>
      <el-table :data="cacheList" border stripe size="small" max-height="400">
        <el-table-column label="远程路径" prop="remote_path" min-width="200" show-overflow-tooltip />
        <el-table-column label="文件大小" width="100">
          <template #default="{ row }">
            {{ (row.file_size / 1024).toFixed(1) }} KB
          </template>
        </el-table-column>
        <el-table-column label="下载时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.download_time) }}
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="cacheDialogVisible = false">关闭</el-button>
        <el-button type="danger" @click="handleClearCache">清空缓存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="scss" scoped>
.file-explorer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-radius: 4px;
}

// ===== 头部 (与 ReportsManager 一致) =====
.file-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;

  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }

  .header-actions {
    display: flex;
    gap: 8px;

    @include bp.respond-to('small') {
      flex-wrap: wrap;
    }
  }
}

// ===== 工具条 =====
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  gap: 12px;
  border-bottom: 1px solid #f0f0f0;

  @include bp.respond-to('small') {
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

// ===== 文件列表主体 =====
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

// ===== 文件名单元格 =====
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

// ===== 上传区域 =====
.upload-icon {
  color: #c0c4cc;
  margin-bottom: 8px;
}

// ===== 表格居中 (与 GooseManager 一致) =====
::deep(.el-table thead th .cell) {
  white-space: nowrap;
}

::deep(.el-table .cell) {
  text-align: center;
}

// ===== 小屏适配 =====
@include bp.respond-to('small') {
  .file-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>
