<template>
  <div class="scl-validation">
    <div v-if="loading" class="loading"><el-skeleton :rows="3" animated /></div>
    <div v-else-if="!items.length" class="empty">
      <el-empty :description="$t('scl.selectFileFirst')" :image-size="60" />
    </div>
    <div v-else class="validation-list">
      <div
        v-for="(item, idx) in items"
        :key="idx"
        class="validation-item"
        :class="`level-${item.level}`"
      >
        <span class="val-icon">
          <template v-if="item.level === 'error'">❌</template>
          <template v-else-if="item.level === 'warning'">⚠️</template>
          <template v-else>✅</template>
        </span>
        <span class="val-msg">{{ item.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { getSclValidation } from '@/api/sclApi'
import type { SclValidationItem } from '@/api/sclApi'

const props = defineProps<{ fileName: string }>()

const loading = ref(false)
const items = ref<SclValidationItem[]>([])

watch(() => props.fileName, async (name) => {
  if (!name) { items.value = []; return }
  loading.value = true
  try {
    items.value = await getSclValidation(name)
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}, { immediate: true })
</script>

<style scoped>
.scl-validation { height: 100%; overflow: auto; }
.loading { padding: 12px; }
.empty { display: flex; align-items: center; justify-content: center; height: 100px; }
.validation-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; margin-bottom: 4px;
  border-radius: 4px; font-size: 12px;
}
.level-info { background: #f6ffed; }
.level-warning { background: #fffbe6; }
.level-error { background: #fff2f0; }
.val-icon { flex-shrink: 0; }
.val-msg { line-height: 1.4; }
</style>
