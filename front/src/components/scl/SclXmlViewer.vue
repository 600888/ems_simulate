<template>
  <div class="scl-xml-viewer">
    <div class="top-bar">
      <span class="file-title">{{ $t('scl.rawXml') }}: {{ fileName }}</span>
      <div class="top-actions">
        <el-button @click="copyContent">{{ $t('scl.copy') }}</el-button>
        <el-button @click="downloadContent">{{ $t('scl.download') }}</el-button>
      </div>
    </div>
    <div class="xml-content" v-loading="loading">
      <div class="line-numbers" v-if="lines.length">
        <div v-for="(_, i) in lines" :key="i" class="line-num">{{ i + 1 }}</div>
      </div>
      <pre class="xml-code"><code>{{ content }}</code></pre>
    </div>
    <div class="bottom-bar">
      <span>{{ $t('scl.totalFiles', { count: lines.length }) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showErrorOnce } from '@/api/http'
import { getSclFileContent } from '@/api/sclApi'

const route = useRoute()
const fileName = ref('')
const content = ref('')
const loading = ref(false)

const lines = computed(() => content.value.split('\n'))

watch(() => route.params.fileName, async (name) => {
  if (name) {
    fileName.value = name as string
    await loadContent()
  }
}, { immediate: true })

async function loadContent() {
  loading.value = true
  try {
    content.value = await getSclFileContent(fileName.value)
  } catch {
    content.value = ''
  } finally {
    loading.value = false
  }
}

async function copyContent() {
  try {
    await navigator.clipboard.writeText(content.value)
    ElMessage.success('已复制')
  } catch {
    showErrorOnce('复制失败')
  }
}

function downloadContent() {
  const blob = new Blob([content.value], { type: 'application/xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName.value
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.scl-xml-viewer {
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
.xml-content {
  flex: 1; display: flex; overflow: auto;
  background: #fafafa; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px;
}
.line-numbers {
  padding: 12px 16px; background: #f0f0f0; color: #999;
  text-align: right; user-select: none; min-width: 48px;
  border-right: 1px solid #e8e8e8;
}
.line-num { line-height: 1.6; }
.xml-code {
  flex: 1; margin: 0; padding: 12px 20px;
  white-space: pre; overflow: visible;
}
.bottom-bar {
  padding: 8px 16px; background: #f5f5f5; border-top: 1px solid #e8e8e8;
  font-size: 13px; color: var(--text-secondary); flex-shrink: 0;
}
</style>
