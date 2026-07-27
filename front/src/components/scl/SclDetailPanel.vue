<template>
  <div class="scl-detail-panel">
    <div v-if="!treeNode" class="empty-state">
      <el-empty :description="$t('scl.selectFileFirst')" :image-size="80" />
    </div>
    <div v-else class="detail-content">
      <h4 class="detail-title">
        📋 {{ $t("scl.nodeDetail") }}: {{ treeNode.label }}
      </h4>

      <!-- 节点属性 -->
      <el-descriptions :column="1" border size="small" class="attr-table">
        <el-descriptions-item :label="$t('scl.nodeName')">{{
          treeNode.label
        }}</el-descriptions-item>
        <el-descriptions-item :label="$t('scl.nodeType')">{{
          typeLabel
        }}</el-descriptions-item>
        <el-descriptions-item :label="$t('scl.belongsToFile')">{{
          fileName
        }}</el-descriptions-item>
        <el-descriptions-item v-if="treeNode.badge" :label="$t('scl.badge')">{{
          treeNode.badge
        }}</el-descriptions-item>
        <el-descriptions-item
          v-if="treeNode.meta?.dai_count !== undefined"
          :label="$t('scl.daCount')"
        >
          <el-tag size="small">{{ treeNode.meta.dai_count }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 子节点 (DO / DA / 其他) -->
      <div v-if="childrenList.length" class="sub-section">
        <h5 class="sub-title">
          📋 {{ childLabel }} ({{ childrenList.length }})
        </h5>
        <!-- DO 列表: 用设计图风格的 FC/CDC/帧类型表格 -->
        <el-table
          v-if="treeNode.type === 'LN'"
          :data="childrenList"
          size="small"
          stripe
          max-height="400"
        >
          <el-table-column
            prop="label"
            :label="$t('scl.name')"
            min-width="140"
            show-overflow-tooltip
          />
          <el-table-column prop="type" :label="$t('scl.type')" width="90">
            <template #default="{ row }">
              <el-tag size="small">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="badge"
            :label="$t('scl.badge')"
            min-width="100"
          />
        </el-table>
        <!-- 其他节点: 简单列表 -->
        <el-table
          v-else
          :data="childrenList"
          size="small"
          stripe
          max-height="300"
        >
          <el-table-column
            prop="label"
            :label="$t('scl.name')"
            min-width="140"
            show-overflow-tooltip
          />
          <el-table-column prop="type" :label="$t('scl.type')" width="90">
            <template #default="{ row }">
              <el-tag size="small">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="badge"
            :label="$t('scl.badge')"
            min-width="100"
          />
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { SclTreeNode } from "@/api/sclApi";

const { t } = useI18n();

const props = defineProps<{
  fileName: string;
  nodePath: string;
  treeNode: SclTreeNode | null;
}>();

const typeLabel = computed(() => {
  const map: Record<string, string> = {
    IED: t("scl.typeLabelIED"),
    AP: t("scl.typeLabelAP"),
    Server: t("scl.typeLabelServer"),
    LDevice: t("scl.typeLabelLDevice"),
    LN: t("scl.typeLabelLN"),
    DO: t("scl.typeLabelDO"),
    DA: t("scl.typeLabelDA"),
    DataSet: t("scl.typeLabelDataSet"),
    FCDA: t("scl.typeLabelFCDA"),
    GoCB: t("scl.typeLabelGoCB"),
    RCB: t("scl.typeLabelRCB"),
    DataType: t("scl.typeLabelDataType"),
    Communication: t("scl.typeLabelCommunication"),
  };
  return map[props.treeNode?.type || ""] || props.treeNode?.type || "";
});

const childrenList = computed(() => {
  return props.treeNode?.children || [];
});

const childLabel = computed(() => {
  const nodeType = props.treeNode?.type;
  if (nodeType === "LN") return t("scl.doList");
  if (nodeType === "DO") return t("scl.daList");
  if (nodeType === "LDevice") return t("scl.lnList");
  return t("scl.subNodes");
});
</script>

<style scoped>
.scl-detail-panel {
  height: 100%;
  overflow: auto;
}
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}
.detail-title {
  margin: 0 0 16px 0;
  font-size: 15px;
  color: var(--text-primary);
}
.attr-table {
  margin-bottom: 20px;
}
.sub-title {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 600;
}
.sub-section {
  margin-top: 16px;
}
</style>
