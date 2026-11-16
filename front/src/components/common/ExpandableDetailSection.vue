<template>
  <section class="detail-section">
    <header class="detail-section-heading">
      <h3>{{ title }}</h3>
      <el-button
        size="small"
        text
        :icon="FullScreen"
        :aria-label="t('common.expandSection', { title })"
        @click="expanded = true"
      >
        {{ t("common.expandView") }}
      </el-button>
    </header>
    <slot :expanded="false" />
    <el-dialog
      v-model="expanded"
      :title="title"
      fullscreen
      append-to-body
      destroy-on-close
      class="detail-section-dialog"
    >
      <div class="detail-section-expanded">
        <slot :expanded="true" />
      </div>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { FullScreen } from "@element-plus/icons-vue";

defineProps<{ title: string }>();
const { t } = useI18n();
const expanded = ref(false);
</script>

<style scoped>
.detail-section {
  min-width: 0;
  margin-top: 16px;
}
.detail-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.detail-section-heading h3 {
  margin: 0;
  min-width: 0;
  font-size: 15px;
  overflow-wrap: anywhere;
}
.detail-section-heading .el-button {
  flex: none;
}
:global(.detail-section-dialog) {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  margin: 0;
}
:global(.detail-section-dialog > .el-dialog__body) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.detail-section-expanded :deep(.el-table .cell),
.detail-section-expanded :deep(.el-descriptions__content) {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.detail-section-expanded :deep(.hex-dump) {
  max-height: none;
}
</style>
