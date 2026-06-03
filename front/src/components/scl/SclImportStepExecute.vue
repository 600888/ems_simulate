<template>
  <div class="import-step-execute">
    <div v-if="!result">
      <div class="progress-section">
        <el-progress
          :percentage="progressPercent"
          :stroke-width="20"
          :text-inside="true"
          striped
          striped-flow
          :status="progressStatus"
        />
      </div>

      <div class="log-section">
        <h5>{{ $t('scl.importLog') }}</h5>
        <div class="log-list" ref="logRef">
          <div v-for="(log, i) in logs" :key="i" class="log-item">{{ log }}</div>
        </div>
      </div>
    </div>

    <div v-else class="result-section">
      <el-result
        :icon="result.success ? 'success' : 'error'"
        :title="result.success ? $t('scl.importSuccess') : $t('scl.importFailed')"
      >
        <template #extra>
          <div class="result-stats">
            <p>遥测: {{ result.yc }} | 遥信: {{ result.yx }} | 遥控: {{ result.yk }} | 遥调: {{ result.yt }}</p>
            <p v-if="result.goose_count">GOOSE: {{ result.goose_count }}</p>
            <p v-if="result.report_count">报告: {{ result.report_count }}</p>
            <div v-if="result.errors.length" class="result-errors">
              <p v-for="(e, i) in result.errors" :key="i" class="error-item">❌ {{ e }}</p>
            </div>
          </div>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import type { SclImportResult } from '@/api/sclApi'

const props = defineProps<{
  importing: boolean
  result: SclImportResult | null
  progressPercent: number
  logs: string[]
}>()

const logRef = ref<HTMLElement>()

const progressStatus = () => {
  if (props.progressPercent >= 100) return 'success'
  return ''
}
</script>

<style scoped>
.progress-section { margin-bottom: 24px; }
.log-section { margin-top: 8px; }
.log-section h5 { margin: 0 0 8px 0; font-size: 13px; }
.log-list {
  max-height: 300px; overflow: auto;
  background: #1a1a2e; color: #8be9fd; padding: 12px; border-radius: 6px;
  font-family: 'Consolas', monospace; font-size: 12px; line-height: 1.6;
}
.log-item { white-space: nowrap; }
.result-stats { text-align: left; font-size: 13px; }
.result-errors { margin-top: 8px; }
.error-item { color: #ff4d4f; font-size: 12px; }
</style>
