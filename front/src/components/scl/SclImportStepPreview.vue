<template>
  <div class="import-step-preview">
    <div v-if="loading" v-loading="loading" class="loading-area" />
    <template v-else-if="previewData">
      <div class="file-info">
        <span>{{ $t("addDevice.icdFile") }}: {{ previewData.file_name }}</span>
        <span>IED: {{ previewData.ied_name }}</span>
      </div>

      <div class="stat-cards">
        <div class="stat-card yc">
          <div class="stat-header">
            <span class="stat-title">{{ $t("scl.ycLabel") }}</span>
            <span class="stat-num">{{ previewData.counts.yc }}</span>
          </div>
          <div class="stat-points">
            {{
              previewData.points.yc
                .slice(0, 3)
                .map((p) => p.name)
                .join(", ")
            }}
          </div>
          <div class="stat-meta">
            {{
              $t("scl.fcTypePreview", {
                fc: "MX",
                types: "Float, Quality, Timestamp",
              })
            }}
          </div>
        </div>
        <div class="stat-card yx">
          <div class="stat-header">
            <span class="stat-title">{{ $t("scl.yxLabel") }}</span>
            <span class="stat-num">{{ previewData.counts.yx }}</span>
          </div>
          <div class="stat-points">
            {{
              previewData.points.yx
                .slice(0, 3)
                .map((p) => p.name)
                .join(", ")
            }}
          </div>
          <div class="stat-meta">
            {{
              $t("scl.fcTypePreview", { fc: "ST", types: "Boolean, Quality" })
            }}
          </div>
        </div>
        <div class="stat-card yk">
          <div class="stat-header">
            <span class="stat-title">{{ $t("scl.ykLabel") }}</span>
            <span class="stat-num">{{ previewData.counts.yk }}</span>
          </div>
          <div class="stat-points">
            {{
              previewData.points.yk
                .slice(0, 3)
                .map((p) => p.name)
                .join(", ")
            }}
          </div>
          <div class="stat-meta">
            {{
              $t("scl.fcTypePreview", { fc: "CO", types: "Boolean, Quality" })
            }}
          </div>
        </div>
        <div class="stat-card yt">
          <div class="stat-header">
            <span class="stat-title">{{ $t("scl.ytLabel") }}</span>
            <span class="stat-num">{{ previewData.counts.yt }}</span>
          </div>
          <div class="stat-points">
            {{
              previewData.points.yt
                .slice(0, 3)
                .map((p) => p.name)
                .join(", ")
            }}
          </div>
          <div class="stat-meta">
            {{ $t("scl.fcTypePreview", { fc: "SP", types: "Float, Quality" }) }}
          </div>
        </div>
      </div>

      <div class="point-table">
        <el-input
          v-model="searchText"
          :placeholder="$t('scl.searchPoint')"
          clearable
          class="search-input"
          :prefix-icon="Search"
        />
        <el-table :data="filteredPoints" size="small" stripe max-height="300">
          <el-table-column
            prop="code"
            :label="$t('scl.pointCode')"
            width="100"
          />
          <el-table-column
            prop="name"
            :label="$t('scl.pointName')"
            min-width="120"
          />
          <el-table-column
            prop="ref"
            :label="$t('scl.registerAddress')"
            min-width="200"
          />
          <el-table-column :label="$t('scl.pointCategory')" width="70">
            <template #default="{ row }">
              <el-tag :type="tagType(row.category)" size="small">{{
                row.category
              }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="fc" label="FC" width="60" />
          <el-table-column
            prop="type"
            :label="$t('scl.pointType')"
            width="100"
          />
        </el-table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { Search } from "@element-plus/icons-vue";
import type { SclPreviewData, SclPointInfo } from "@/api/sclApi";

const props = defineProps<{
  previewData: SclPreviewData | null;
  loading: boolean;
}>();

const searchText = ref("");

const filteredPoints = computed(() => {
  if (!searchText.value) return allPoints.value;
  const q = searchText.value.toLowerCase();
  return allPoints.value.filter(
    (p) => p.name.toLowerCase().includes(q) || p.code.toLowerCase().includes(q),
  );
});

const allPoints = computed<SclPointInfo[]>(() => {
  const data = props.previewData as SclPreviewData | null;
  if (!data) return [];
  return [
    ...(data.points?.yc || []),
    ...(data.points?.yx || []),
    ...(data.points?.yk || []),
    ...(data.points?.yt || []),
  ];
});

function tagType(cat: string): string {
  const map: Record<string, string> = {
    YC: "",
    YX: "success",
    YK: "warning",
    YT: "danger",
  };
  return map[cat] || "";
}
</script>

<style scoped>
.loading-area {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.file-info {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--bg-subtle);
  border-radius: var(--border-radius-base);
  font-size: 13px;
  color: var(--text-secondary);
}
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.stat-card {
  padding: 16px;
  border-radius: var(--border-radius-base);
  border: 1px solid;
}
.stat-card.yc {
  background: #e6f7ff;
  border-color: #91d5ff;
}
.stat-card.yx {
  background: #f6ffed;
  border-color: #b7eb8f;
}
.stat-card.yk {
  background: #fff7e6;
  border-color: #ffd591;
}
.stat-card.yt {
  background: #f9f0ff;
  border-color: #d3adf7;
}
.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.stat-title {
  font-weight: 600;
  font-size: 15px;
}
.stat-card.yc .stat-title {
  color: #1890ff;
}
.stat-card.yx .stat-title {
  color: #52c41a;
}
.stat-card.yk .stat-title {
  color: #fa8c16;
}
.stat-card.yt .stat-title {
  color: #722ed1;
}
.stat-num {
  font-size: 28px;
  font-weight: 700;
}
.stat-card.yc .stat-num {
  color: #1890ff;
}
.stat-card.yx .stat-num {
  color: #52c41a;
}
.stat-card.yk .stat-num {
  color: #fa8c16;
}
.stat-card.yt .stat-num {
  color: #722ed1;
}
.stat-points {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  line-height: 1.4;
}
.stat-meta {
  font-size: 11px;
  color: #999;
}
.point-table {
  flex: 1;
}
.search-input {
  width: 240px;
  margin-bottom: 12px;
}
</style>
