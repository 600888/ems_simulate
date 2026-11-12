<template>
  <el-tag
    v-if="fc"
    :color="FC_COLORS[fc] || '#6b7280'"
    effect="dark"
    size="small"
    class="fc-tag"
  >
    {{ fc }}
  </el-tag>
</template>

<script setup lang="ts">
defineProps<{ fc?: string }>();

const FC_COLORS: Record<string, string> = {
  MX: "#3b82f6",
  ST: "#10b981",
  CO: "#f59e0b",
  CF: "#8b5cf6",
  DC: "#6b7280",
  EX: "#ef4444",
  SG: "#06b6d4",
  SR: "#6b7280",
  OR: "#f97316",
  BL: "#94a3b8",
};
</script>

<style scoped>
.fc-tag {
  border: none !important;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  min-width: 36px;
  text-align: center;
}
</style>
