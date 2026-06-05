<template>
  <div class="scl-preview">
    <div class="top-bar">
      <span class="file-title">{{ $t('scl.filePreview') }}: {{ fileName }}</span>
      <el-tag v-if="fileType" :type="fileType === 'ICD' ? 'success' : 'warning'" size="small">{{ fileType }}</el-tag>
      <div class="top-actions">
        <el-button @click="handleExportXml">{{ $t('scl.exportXml') }}</el-button>
        <el-button @click="handleReparse">{{ $t('scl.reparse') }}</el-button>
      </div>
    </div>

    <div class="content-row">
      <div class="tree-panel">
        <SclTreePanel
          :tree-data="treeData"
          :selected-path="selectedPath"
          @node-select="handleNodeSelect"
        />
      </div>
      <div class="detail-panel">
        <el-tabs v-model="activeTab">
          <el-tab-pane :label="$t('scl.nodeDetail')" name="detail">
            <SclDetailPanel :file-name="fileName" :node-path="selectedPath" :tree-node="selectedNode" />
          </el-tab-pane>
          <el-tab-pane :label="$t('scl.validationResult')" name="validation">
            <SclValidationResults :file-name="fileName" />
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <div class="bottom-bar">
      <span>{{ statusText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getSclTree } from '@/api/sclApi'
import type { SclTreeNode, SclFileInfo } from '@/api/sclApi'
import SclTreePanel from './SclTreePanel.vue'
import SclDetailPanel from './SclDetailPanel.vue'
import SclValidationResults from './SclValidationResults.vue'

const route = useRoute()
const fileName = ref('')
const fileType = ref('')
const treeData = ref<SclTreeNode[]>([])
const selectedPath = ref('')
const selectedNode = ref<SclTreeNode | null>(null)
const activeTab = ref('detail')
const loading = ref(false)

const statusText = ref('')

watch(() => route.params.fileName, async (name) => {
  if (name) {
    fileName.value = name as string
    await loadData()
  }
}, { immediate: true })

async function loadData() {
  if (!fileName.value) return
  loading.value = true
  try {
    const tree = await getSclTree(fileName.value)
    treeData.value = tree
    updateStatus(tree)
    // 从文件名后缀推断类型
    const ext = (fileName.value || '').split('.').pop()?.toUpperCase()
    fileType.value = ext === 'ICD' ? 'ICD' : ext === 'SCD' ? 'SCD' : ext || ''
  } catch {
    treeData.value = []
  } finally {
    loading.value = false
  }
}

function updateStatus(tree: SclTreeNode[]) {
  let total = 0, doCount = 0, daCount = 0, dsCount = 0, goCount = 0
  const count = (nodes: SclTreeNode[]) => {
    for (const n of nodes) {
      total++
      if (n.type === 'DO') doCount++
      if (n.type === 'DA') daCount++
      if (n.type === 'DataSet') dsCount++
      if (n.type === 'GoCB') goCount++
      if (n.children) count(n.children)
    }
  }
  count(tree)
  statusText.value = `节点数: ${total} | DO: ${doCount} | DA: ${daCount} | DS: ${dsCount} | GoCB: ${goCount}`
}

function handleNodeSelect(path: string, node: SclTreeNode) {
  selectedPath.value = path
  selectedNode.value = node
}

function handleExportXml() {
  window.open(`#/scl/viewer/${fileName.value}`, '_blank')
}

function handleReparse() {
  loadData()
}
</script>

<style scoped>
.scl-preview {
  height: calc(100vh - var(--header-height) - var(--tags-height) - var(--footer-height));
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: var(--border-radius-base);
  box-shadow: var(--box-shadow-base);
  overflow: hidden;
}
.top-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; background: #fafafa; border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}
.file-title { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.top-actions { margin-left: auto; display: flex; gap: 8px; }
.content-row { flex: 1; display: flex; overflow: hidden; }
.tree-panel {
  width: 360px; min-width: 260px;
  padding: 12px; border-right: 1px solid #e8e8e8; overflow: auto;
  background: #fafafa;
}
.detail-panel { flex: 1; padding: 16px; overflow: auto; background: #fff; }
.bottom-bar {
  padding: 8px 16px; background: #f5f5f5; border-top: 1px solid #e8e8e8;
  font-size: 13px; color: var(--text-secondary); flex-shrink: 0;
}
</style>
