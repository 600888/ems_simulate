<template>
  <div class="scl-detail-panel">
    <div v-if="!treeNode" class="empty-state">
      <el-empty :description="$t('scl.selectFileFirst')" :image-size="80" />
    </div>
    <div v-else class="detail-content">
      <h4 class="detail-title">📋 {{ $t('scl.nodeDetail') }}: {{ treeNode.label }}</h4>

      <!-- 节点属性 -->
      <el-descriptions :column="1" border size="small" class="attr-table">
        <el-descriptions-item label="节点名称">{{ treeNode.label }}</el-descriptions-item>
        <el-descriptions-item label="节点类型">{{ typeLabel }}</el-descriptions-item>
        <el-descriptions-item label="所属文件">{{ fileName }}</el-descriptions-item>
        <el-descriptions-item v-if="treeNode.badge" label="标识">{{ treeNode.badge }}</el-descriptions-item>
        <el-descriptions-item v-if="treeNode.meta?.dai_count !== undefined" label="DA 数量">
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
          <el-table-column prop="label" label="名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="type" label="类型" width="90">
            <template #default="{ row }">
              <el-tag size="small">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="badge" label="标识" min-width="100" />
        </el-table>
        <!-- 其他节点: 简单列表 -->
        <el-table v-else :data="childrenList" size="small" stripe max-height="300">
          <el-table-column prop="label" label="名称" min-width="140" show-overflow-tooltip />
          <el-table-column prop="type" label="类型" width="90">
            <template #default="{ row }">
              <el-tag size="small">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="badge" label="标识" min-width="100" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SclTreeNode } from '@/api/sclApi'

const props = defineProps<{
  fileName: string
  nodePath: string
  treeNode: SclTreeNode | null
}>()

const typeLabel = computed(() => {
  const map: Record<string, string> = {
    IED: 'IED 设备', AP: '访问点', Server: '服务器',
    LDevice: '逻辑设备', LN: '逻辑节点',
    DO: '数据对象', DA: '数据属性',
    DataSet: '数据集', FCDA: 'FCDA',
    GoCB: 'GOOSE 控制块', RCB: '报告控制块',
    DataType: '数据类型模板', Communication: '通信配置',
  }
  return map[props.treeNode?.type || ''] || props.treeNode?.type || ''
})

const childrenList = computed(() => {
  return props.treeNode?.children || []
})

const childLabel = computed(() => {
  const t = props.treeNode?.type
  if (t === 'LN') return 'DO 列表'
  if (t === 'DO') return 'DA 列表'
  if (t === 'LDevice') return 'LN 列表'
  return '子节点'
})
</script>

<style scoped>
.scl-detail-panel { height: 100%; overflow: auto; }
.empty-state { display: flex; align-items: center; justify-content: center; height: 200px; }
.detail-title { margin: 0 0 16px 0; font-size: 15px; color: var(--text-primary); }
.attr-table { margin-bottom: 20px; }
.sub-title { margin: 0 0 12px 0; font-size: 14px; color: var(--text-primary); font-weight: 600; }
.sub-section { margin-top: 16px; }
</style>
