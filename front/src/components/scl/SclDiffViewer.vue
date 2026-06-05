<template>
  <div class="scl-diff-viewer">
    <div class="diff-toolbar">
      <span>{{ $t('scl.fileA') }}:</span>
      <el-select v-model="fileA" style="width: 200px">
        <el-option v-for="f in fileOptions" :key="f" :value="f" :label="f" />
      </el-select>
      <el-button @click="swapFiles">⇄ {{ $t('scl.swapFiles') }}</el-button>
      <span>{{ $t('scl.fileB') }}:</span>
      <el-select v-model="fileB" style="width: 200px">
        <el-option v-for="f in fileOptions" :key="f" :value="f" :label="f" />
      </el-select>
      <el-button type="primary" :disabled="!fileA || !fileB" @click="startDiff" :loading="loading">
        🔍 {{ $t('scl.startCompare') }}
      </el-button>
    </div>

    <div v-if="loading" class="diff-loading">
      <el-skeleton :rows="8" animated />
    </div>

    <SclDiffResult
      v-else-if="diffResult"
      :diff-result="diffResult"
      :tree-a="treeA"
      :tree-b="treeB"
      :file-a="fileA"
      :file-b="fileB"
    />
    <el-empty v-else :description="$t('scl.selectFileFirst')" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getSclFileList, getSclTree, diffSclFiles } from '@/api/sclApi'
import type { SclFileInfo, SclTreeNode, SclDiffResult as SclDiffResultType } from '@/api/sclApi'
import SclDiffResult from './SclDiffResult.vue'

const route = useRoute()
const loading = ref(false)
const fileList = ref<SclFileInfo[]>([])
const fileOptions = ref<string[]>([])
const fileA = ref('')
const fileB = ref('')
const treeA = ref<SclTreeNode[]>([])
const treeB = ref<SclTreeNode[]>([])
const diffResult = ref<SclDiffResultType | null>(null)

onMounted(async () => {
  fileList.value = await getSclFileList()
  fileOptions.value = fileList.value.map(f => f.filename || f.file_name || '')
  // 如果路由 query 指定了 file，自动填入 fileA
  if (route.query.file) {
    fileA.value = route.query.file as string
  }
})

watch(() => route.query.file, (file) => {
  if (file && !fileA.value) {
    fileA.value = file as string
  }
})

function swapFiles() {
  const tmp = fileA.value
  fileA.value = fileB.value
  fileB.value = tmp
}

async function startDiff() {
  if (!fileA.value || !fileB.value) return
  loading.value = true
  try {
    const [ta, tb, result] = await Promise.all([
      getSclTree(fileA.value),
      getSclTree(fileB.value),
      diffSclFiles(fileA.value, fileB.value),
    ])
    treeA.value = ta
    treeB.value = tb
    diffResult.value = result
  } catch {
    diffResult.value = null
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.scl-diff-viewer {
  height: calc(100vh - var(--header-height) - var(--tags-height) - var(--footer-height));
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: var(--border-radius-base);
  box-shadow: var(--box-shadow-base);
  overflow: hidden;
  padding: 16px;
}
.diff-toolbar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 16px; flex-wrap: wrap; flex-shrink: 0;
}
.diff-loading { padding: 24px; }
</style>
