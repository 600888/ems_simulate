<template>
  <div class="import-step-file">
    <p class="step-desc">{{ $t('scl.selectIcdFile') }}</p>
    <div class="file-list">
      <div
        v-for="file in files"
        :key="file.file_name"
        class="file-card"
        :class="{ selected: selectedFile === file.file_name }"
        @click="selectedFile = file.file_name"
      >
        <el-radio v-model="selectedFile" :value="file.file_name" class="file-radio">
          <div class="file-card-content">
            <div class="file-card-name">{{ file.file_name }}</div>
            <div class="file-card-meta">
              IED: {{ file.ied_names?.join(', ') }} |
              {{ $t('addDevice.mmsPoints', { total: file.point_summary?.yc + file.point_summary?.yx + file.point_summary?.yk + file.point_summary?.yt || 0, yc: file.point_summary?.yc || 0, yx: file.point_summary?.yx || 0, yk: file.point_summary?.yk || 0, yt: file.point_summary?.yt || 0 }) }}
            </div>
          </div>
        </el-radio>
      </div>
    </div>
    <el-button @click="$emit('upload')" class="upload-btn">
      <el-icon><Plus /></el-icon>{{ $t('scl.uploadNewFile') }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import type { SclFileInfo } from '@/api/sclApi'

const props = defineProps<{ files: SclFileInfo[] }>()
const emit = defineEmits<{
  (e: 'update:selected', fileName: string): void
  (e: 'upload'): void
}>()

const selectedFile = ref('')

watch(selectedFile, (val) => {
  emit('update:selected', val)
})
</script>

<style scoped>
.step-desc { margin: 0 0 12px 0; color: var(--text-secondary); font-size: 13px; }
.file-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.file-card {
  border: 1px solid #e8e8e8; border-radius: 6px; padding: 10px 12px;
  cursor: pointer; transition: all 0.2s;
}
.file-card:hover { border-color: #1890ff; background: #f0f5ff; }
.file-card.selected { border-color: #1890ff; background: #e6f7ff; }
.file-radio { width: 100%; }
.file-card-content { display: flex; flex-direction: column; gap: 4px; }
.file-card-name { font-weight: 600; font-size: 13px; }
.file-card-meta { font-size: 11px; color: #999; }
.upload-btn { margin-top: 8px; }
</style>
