<template>
  <el-drawer
    v-model="visible"
    title="报文精确解析"
    size="min(760px, 100vw)"
    append-to-body
    destroy-on-close
    class="message-detail-drawer"
  >
    <div v-loading="loading" class="detail-body">
      <template v-if="detail">
        <el-alert :title="detail.summary" :type="detail.valid ? 'success' : 'error'" :closable="false" show-icon />

        <el-descriptions :column="3" border class="section">
          <el-descriptions-item label="协议">{{ detail.protocol }}</el-descriptions-item>
          <el-descriptions-item label="帧类型">{{ detail.frame_kind }}</el-descriptions-item>
          <el-descriptions-item label="方向">{{ detail.direction }} / {{ detail.msg_type }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ detail.formatted_time }}</el-descriptions-item>
          <el-descriptions-item label="长度">{{ detail.raw_length }} 字节</el-descriptions-item>
          <el-descriptions-item label="解析状态">
            <el-tag :type="detail.valid ? (detail.complete ? 'success' : 'warning') : 'danger'" size="small">
              {{ detail.valid ? (detail.complete ? '完整' : '部分') : '校验失败' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <section class="section">
          <h3>原始报文</h3>
          <div class="raw-frame">
            <span
              v-for="(byte, index) in rawBytes"
              :key="index"
              class="raw-byte"
              :class="{ selected: isSelectedByte(index) }"
              :title="`字节 ${index}`"
            >{{ byte }}</span>
          </div>
          <div class="raw-hint">点击下方字段可高亮其对应的原始字节</div>
        </section>

        <section class="section">
          <h3>字段解析</h3>
          <el-table
            :data="detail.fields"
            border
            size="small"
            max-height="360"
            highlight-current-row
            @row-click="selectField"
          >
            <el-table-column label="字节" width="82">
              <template #default="{ row }">{{ byteRange(row.offset, row.length) }}</template>
            </el-table-column>
            <el-table-column prop="raw_hex" label="原始字节" min-width="110" />
            <el-table-column prop="name" label="字段" width="130" />
            <el-table-column prop="display_value" label="解析值" min-width="150" />
            <el-table-column prop="description" label="说明" min-width="150" />
          </el-table>
        </section>

        <section v-if="detail.objects.length" class="section">
          <h3>数据对象</h3>
          <el-table
            :data="detail.objects"
            border
            size="small"
            max-height="280"
            highlight-current-row
            @row-click="handleObjectRowClick"
          >
            <el-table-column type="expand" width="42">
              <template #default="{ row }">
                <div class="object-detail">
                  <div v-if="row.name"><strong>数据项：</strong>{{ row.name }}</div>
                  <div v-if="row.point">
                    <strong>关联测点：</strong>{{ row.point.name }}（{{ row.point.code }}），
                    地址 {{ row.point.address }}，解析码 {{ row.point.decode_code }}，
                    系数 ×{{ row.point.multiplier }} + {{ row.point.addition }}
                  </div>
                  <div v-if="row.decoded_value !== undefined">
                    <strong>组合解析值：</strong>{{ displayValue(row.decoded_value) }}
                    <span v-if="row.combined_raw">（原始 {{ row.combined_raw }}）</span>
                  </div>
                  <div v-if="row.quality"><strong>品质/限定词：</strong>{{ displayValue(row.quality) }}</div>
                  <div v-if="row.timestamp_detail"><strong>时标字段：</strong>{{ displayValue(row.timestamp_detail) }}</div>
                  <el-table
                    v-if="row.fields?.length"
                    :data="row.fields"
                    size="small"
                    border
                    class="object-fields"
                    highlight-current-row
                    @row-click="selectField"
                  >
                    <el-table-column label="字节" width="82">
                      <template #default="scope">{{ byteRange(scope.row.offset, scope.row.length) }}</template>
                    </el-table-column>
                    <el-table-column prop="raw_hex" label="原始字节" min-width="110" />
                    <el-table-column prop="name" label="字段" width="130" />
                    <el-table-column prop="display_value" label="解析值" min-width="180" />
                  </el-table>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="index" label="#" width="55" />
            <el-table-column label="字节" width="82">
              <template #default="{ row }">{{ byteRange(row.offset, row.length) }}</template>
            </el-table-column>
            <el-table-column prop="name" label="数据项" min-width="120" />
            <el-table-column prop="address" label="地址 / IOA" width="120" />
            <el-table-column prop="raw_value" label="原始值" min-width="150" />
            <el-table-column label="解析值" min-width="160">
              <template #default="{ row }">{{ displayValue(row.value) }}</template>
            </el-table-column>
            <el-table-column label="工程值" min-width="130">
              <template #default="{ row }">{{ displayEngineeringValue(row) }}</template>
            </el-table-column>
            <el-table-column prop="timestamp" label="时标" min-width="150" />
          </el-table>
        </section>

        <section v-if="detail.correlation" class="section">
          <h3>请求响应关联</h3>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="关联请求序号">#{{ detail.correlation.request_sequence_id }}</el-descriptions-item>
            <el-descriptions-item label="匹配方式">{{ detail.correlation.match_method }}</el-descriptions-item>
            <el-descriptions-item label="地址范围">
              {{ detail.correlation.start_address }} - {{ detail.correlation.end_address }}
            </el-descriptions-item>
            <el-descriptions-item label="数量">{{ detail.correlation.quantity }}</el-descriptions-item>
          </el-descriptions>
        </section>

        <section v-if="detail.validation.length" class="section">
          <h3>完整性校验</h3>
          <div v-for="item in detail.validation" :key="item.name" class="validation-item">
            <el-tag :type="item.passed ? 'success' : 'danger'" size="small">{{ item.passed ? '通过' : '失败' }}</el-tag>
            <strong>{{ item.name }}</strong><span>{{ item.detail }}</span>
          </div>
        </section>

        <el-alert v-for="message in detail.warnings" :key="message" :title="message" type="warning" :closable="false" class="notice" />
        <el-alert v-for="message in detail.errors" :key="message" :title="message" type="error" :closable="false" class="notice" />
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMessageDetail, type MessageDetail } from '@/api/deviceApi'

const props = defineProps<{ deviceName: string }>()
const visible = ref(false)
const loading = ref(false)
const detail = ref<MessageDetail | null>(null)
const selectedField = ref<{ offset: number; length: number } | null>(null)
const rawBytes = computed(() => detail.value?.raw_hex.split(/\s+/).filter(Boolean) ?? [])

async function open(sequenceId: number) {
  visible.value = true
  loading.value = true
  detail.value = null
  selectedField.value = null
  try {
    detail.value = await getMessageDetail(props.deviceName, sequenceId)
  } catch (error) {
    ElMessage.error('获取报文详情失败，报文可能已被缓存淘汰')
    visible.value = false
  } finally {
    loading.value = false
  }
}

function byteRange(offset: number, length: number) {
  return length <= 1 ? `${offset}` : `${offset}-${offset + length - 1}`
}

function displayValue(value: unknown) {
  return typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')
}

function selectField(field: { offset: number; length: number }) {
  if (!field.length) return
  selectedField.value = { offset: field.offset, length: field.length }
}

function selectObject(object: { offset?: number; length?: number; fields?: Array<{ offset: number; length: number }> }) {
  if (typeof object.offset === 'number' && object.length) {
    selectField({ offset: object.offset, length: object.length })
    return
  }
  const mappedFields = object.fields?.filter((field) => field.length > 0) ?? []
  if (!mappedFields.length) return
  const start = Math.min(...mappedFields.map((field) => field.offset))
  const end = Math.max(...mappedFields.map((field) => field.offset + field.length))
  selectField({ offset: start, length: end - start })
}

function handleObjectRowClick(
  object: { offset?: number; length?: number; fields?: Array<{ offset: number; length: number }> },
  _column: unknown,
  event: MouseEvent,
) {
  if ((event.target as HTMLElement | null)?.closest('.object-fields')) return
  selectObject(object)
}

function isSelectedByte(index: number) {
  const selected = selectedField.value
  return !!selected && index >= selected.offset && index < selected.offset + selected.length
}

function displayEngineeringValue(row: Record<string, any>) {
  if (row.engineering_value === undefined) return row.point?.name ? '—' : ''
  const pointName = row.point?.name ? `${row.point.name}: ` : ''
  return `${pointName}${displayValue(row.engineering_value)}`
}

defineExpose({ open })
</script>

<style scoped>
.detail-body { min-height: 180px; }
.section { margin-top: 18px; }
.section h3 { margin: 0 0 10px; font-size: 15px; }
.raw-frame { padding: 14px; border-radius: 6px; background: #111827; color: #d1fae5; font: 13px/1.8 Consolas, Monaco, monospace; word-break: break-all; white-space: normal; }
.raw-byte { display: inline-block; margin-right: 7px; padding: 0 2px; border-radius: 3px; transition: background-color .15s, color .15s; }
.raw-byte.selected { background: #f59e0b; color: #111827; font-weight: 700; }
.raw-hint { margin-top: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
.validation-item { display: grid; grid-template-columns: 54px 110px 1fr; align-items: center; gap: 8px; margin: 7px 0; font-size: 13px; }
.notice { margin-top: 8px; }
.object-detail { padding: 8px 14px 14px; line-height: 1.8; }
.object-fields { margin-top: 8px; }
</style>
