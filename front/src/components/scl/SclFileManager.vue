<template>
  <div class="scl-file-manager">
    <div class="toolbar">
      <el-button type="primary" @click="showUpload = true">
        <el-icon><Plus /></el-icon>{{ $t('scl.upload') }}
      </el-button>
      <el-button @click="loadFiles">
        <el-icon><Refresh /></el-icon>{{ $t('scl.refresh') }}
      </el-button>
      <el-input
        v-model="searchText"
        :placeholder="$t('scl.searchFile')"
        clearable
        class="search-input"
        :prefix-icon="Search"
      />
    </div>

    <el-table
      :data="filteredFiles"
      v-loading="loading"
      stripe
      border
      style="width: 100%"
      @row-click="handleRowClick"
    >
      <el-table-column type="index" label="#" width="50" />
      <el-table-column :label="$t('scl.fileName')" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <div class="file-name">{{ row.file_name }}</div>
          <div class="file-summary" v-if="row.ied_name">
            IED: {{ row.ied_name }}
            <template v-if="row.ycCount !== undefined"> | YC={{ row.ycCount }} YX={{ row.yxCount }} YK={{ row.ykCount }} YT={{ row.ytCount }}</template>
          </div>
        </template>
      </el-table-column>
      <el-table-column :label="$t('scl.fileType')" width="80" align="center">
        <template #default="{ row }">
          <el-tag
            :type="(row.file_type || row.extension?.replace('.','').toUpperCase()) === 'ICD' ? 'success' : 'warning'"
            size="small"
          >
            {{ (row.file_type || row.extension?.replace('.','').toUpperCase() || 'ICD') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('scl.iedName')" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.ied_name || row.ied_names?.join(', ') || '-' }}
        </template>
      </el-table-column>
      <el-table-column :label="$t('scl.fileSize')" width="100" align="right">
        <template #default="{ row }">{{ row.size_display || formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column :label="$t('scl.uploadTime')" width="160" align="center">
        <template #default="{ row }">{{ row.upload_time || row.modified_time || '-' }}</template>
      </el-table-column>
      <el-table-column :label="$t('scl.operations')" width="380" fixed="right" align="center">
        <template #default="{ row }">
          <el-button-group>
            <el-button type="primary" link @click.stop="handlePreview(row)">{{ $t('scl.previewAction') }}</el-button>
            <el-button type="success" link @click.stop="handleImport(row)">{{ $t('scl.importAction') }}</el-button>
            <el-button type="warning" link @click.stop="handleXmlView(row)">{{ $t('scl.xmlView') }}</el-button>
            <el-button type="danger" link @click.stop="handleDelete(row)">{{ $t('scl.deleteAction') }}</el-button>
            <el-button type="info" link @click.stop="handleDiff(row)">{{ $t('scl.diffAction') }}</el-button>
          </el-button-group>
        </template>
      </el-table-column>
    </el-table>

    <SclUploadDialog
      v-if="showUpload"
      @close="showUpload = false"
      @success="loadFiles"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { getSclFileList, deleteSclFile } from '@/api/sclApi'
import type { SclFileInfo } from '@/api/sclApi'
import SclUploadDialog from './SclUploadDialog.vue'

const router = useRouter()
const loading = ref(false)
const files = ref<SclFileInfo[]>([])
const searchText = ref('')
const showUpload = ref(false)

const filteredFiles = computed(() => {
  if (!searchText.value) return files.value
  return files.value.filter(f => (f.file_name || f.filename || '').toLowerCase().includes(searchText.value.toLowerCase()))
})

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function loadFiles() {
  loading.value = true
  try {
    const raw = await getSclFileList()
    // 标准化字段名
    files.value = (raw || []).map((f: any) => ({
      ...f,
      file_name: f.file_name || f.filename,
      file_type: f.file_type || (f.extension || '').replace('.', '').toUpperCase(),
    }))
  } catch {
    files.value = []
  } finally {
    loading.value = false
  }
}

function getFileName(row: SclFileInfo): string {
  return row.file_name || row.filename || ''
}

function handleRowClick(row: SclFileInfo) {
  router.push(`/scl/preview/${encodeURIComponent(getFileName(row))}`)
}

function handlePreview(row: SclFileInfo) {
  router.push(`/scl/preview/${encodeURIComponent(getFileName(row))}`)
}

function handleImport(row: SclFileInfo) {
  router.push(`/scl/import?file=${encodeURIComponent(getFileName(row))}`)
}

function handleXmlView(row: SclFileInfo) {
  router.push(`/scl/viewer/${encodeURIComponent(getFileName(row))}`)
}

function handleDiff(row: SclFileInfo) {
  const name = getFileName(row)
  router.push(`/scl/diff?file=${encodeURIComponent(name)}`)
}

async function handleDelete(row: SclFileInfo) {
  const name = getFileName(row)
  try {
    await ElMessageBox.confirm('确定删除文件 "' + name + '"？', '提示', { type: 'warning' })
    await deleteSclFile(name)
    await loadFiles()
  } catch {
    // cancelled
  }
}

onMounted(loadFiles)
</script>

<style scoped>
.scl-file-manager {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: var(--border-radius-base);
  box-shadow: var(--box-shadow-base);
  overflow: hidden;
}
.toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; background: #fafafa; border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}
.search-input { width: 240px; margin-left: auto; }
.file-name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.file-summary { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
</style>
