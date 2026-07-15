<template>
  <div v-loading="initialLoading" class="workspace-page">
    <header class="workspace-toolbar">
      <div class="project-identity">
        <el-button text circle @click="router.push('/scl/modeling')"><el-icon><ArrowLeft /></el-icon></el-button>
        <div>
          <div class="project-name">{{ project?.name || '模型工作台' }}</div>
          <div class="project-code">{{ project?.code }} · {{ project?.file_type }} · r{{ project?.revision }}</div>
        </div>
        <el-tag v-if="project" size="small" :type="project.validation_errors ? 'danger' : 'info'">
          {{ project.status === 'DRAFT' ? '草稿' : project.status }}
        </el-tag>
      </div>
      <div class="toolbar-actions">
        <el-button :loading="validating" @click="runValidation"><el-icon><CircleCheck /></el-icon>校验模型</el-button>
        <el-button type="primary" :disabled="!selectedNode || !dirty" :loading="saving" @click="saveNode">
          <el-icon><DocumentChecked /></el-icon>保存属性
        </el-button>
      </div>
    </header>

    <div class="workspace-grid">
      <aside class="tree-panel panel">
        <div class="panel-heading">
          <div><strong>模型结构</strong><small>{{ project?.node_count || 0 }} 个节点</small></div>
          <el-tooltip content="刷新模型树"><el-button text circle @click="loadTree"><el-icon><Refresh /></el-icon></el-button></el-tooltip>
        </div>
        <div class="tree-search">
          <el-input v-model="treeKeyword" clearable placeholder="搜索节点" size="small">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </div>
        <el-scrollbar class="tree-scroll">
          <el-tree
            ref="treeRef"
            :data="treeData"
            node-key="id"
            highlight-current
            default-expand-all
            :expand-on-click-node="false"
            :filter-node-method="filterTreeNode"
            @node-click="selectNode"
          >
            <template #default="{ data }">
              <div class="tree-node" :class="`kind-${data.kind.toLowerCase()}`">
                <span class="kind-dot"></span>
                <span class="tree-label">{{ data.label }}</span>
                <span v-if="['IED', 'LDEVICE', 'LN', 'LN0'].includes(data.kind)" class="kind-code">{{ data.kind }}</span>
              </div>
            </template>
          </el-tree>
        </el-scrollbar>
        <div class="tree-footer">
          <el-button size="small" :disabled="!canAdd" @click="openAddDialog"><el-icon><Plus /></el-icon>添加子节点</el-button>
          <el-button size="small" type="danger" plain :disabled="!selectedNode || selectedNode.protected" @click="openDeleteDialog">
            <el-icon><Delete /></el-icon>删除
          </el-button>
        </div>
      </aside>

      <main class="context-panel panel">
        <template v-if="selectedNode">
          <div class="node-breadcrumb"><el-icon><Location /></el-icon>{{ selectedNode.path }}</div>
          <section class="node-hero">
            <div class="node-symbol">{{ nodeAbbr(selectedNode.kind) }}</div>
            <div>
              <div class="kind-label">{{ selectedNode.kind_label }}</div>
              <h2>{{ selectedNode.name }}</h2>
              <p>{{ nodeDescription(selectedNode.kind) }}</p>
            </div>
          </section>

          <section class="metric-grid">
            <div><span>节点类型</span><strong>{{ selectedNode.kind }}</strong></div>
            <div><span>直接子节点</span><strong>{{ selectedNode.child_count }}</strong></div>
            <div><span>节点修订</span><strong>r{{ selectedNode.revision }}</strong></div>
            <div><span>结构保护</span><strong>{{ selectedNode.protected ? '是' : '否' }}</strong></div>
          </section>

          <section class="guide-card">
            <div class="guide-heading"><el-icon><Guide /></el-icon><strong>现场建模提示</strong></div>
            <p>{{ operationHint(selectedNode.kind) }}</p>
            <div v-if="selectedNode.schema?.allowed_children.length" class="allowed-list">
              <span>可添加：</span>
              <el-tag v-for="child in selectedNode.schema.allowed_children" :key="child.kind" size="small" effect="plain">
                {{ child.label }}
              </el-tag>
            </div>
            <el-empty v-else :image-size="48" description="该节点没有可添加的下级结构" />
          </section>

          <section v-if="selectedNode.children?.length" class="children-card">
            <div class="section-row"><strong>下级节点</strong><span>双击式操作被刻意避免，所有操作均有明确按钮。</span></div>
            <div class="child-chips">
              <button v-for="child in selectedNode.children" :key="child.id" @click="focusNode(child.id)">
                <span>{{ nodeAbbr(child.kind) }}</span>{{ child.name }}<small>{{ child.kind }}</small>
              </button>
            </div>
          </section>
        </template>
        <el-empty v-else description="请从左侧选择一个模型节点" />
      </main>

      <aside class="property-panel panel">
        <div class="panel-heading property-heading">
          <div><strong>节点属性</strong><small v-if="dirty" class="dirty-tip">有未保存修改</small></div>
          <el-tag v-if="selectedNode" size="small" effect="plain">{{ selectedNode.kind }}</el-tag>
        </div>
        <el-scrollbar class="property-scroll">
          <el-form v-if="selectedNode && selectedNode.schema" label-position="top" class="property-form">
            <template v-for="field in selectedNode.schema.fields" :key="field.key">
              <el-form-item :label="field.label" :required="field.required">
                <el-switch
                  v-if="field.component === 'switch'"
                  v-model="propertyForm.attributes[field.key]"
                />
                <el-input-number
                  v-else-if="field.component === 'number'"
                  v-model="propertyForm.attributes[field.key]"
                  :min="0"
                  controls-position="right"
                  style="width: 100%"
                />
                <el-input
                  v-else-if="field.key === 'name'"
                  v-model="propertyForm.name"
                  :disabled="selectedNode.kind === 'LN0'"
                />
                <el-input
                  v-else
                  v-model="propertyForm.attributes[field.key]"
                  :type="field.component === 'textarea' ? 'textarea' : 'text'"
                  :rows="3"
                  clearable
                />
              </el-form-item>
            </template>
          </el-form>
          <el-empty v-else :image-size="64" description="选择节点后编辑属性" />
        </el-scrollbar>
        <div class="property-footer">
          <el-button :disabled="!dirty" @click="resetForm">撤销修改</el-button>
          <el-button type="primary" :disabled="!dirty" :loading="saving" @click="saveNode">保存</el-button>
        </div>
      </aside>
    </div>

    <section class="validation-bar" :class="{ expanded: validationExpanded }">
      <button class="validation-summary" @click="validationExpanded = !validationExpanded">
        <el-icon :class="{ rotate: validationExpanded }"><ArrowUp /></el-icon>
        <strong>模型校验</strong>
        <template v-if="validationResult">
          <span class="error-count">{{ validationResult.error_count }} 错误</span>
          <span class="warning-count">{{ validationResult.warning_count }} 警告</span>
          <span v-if="validationResult.passed" class="pass-text"><el-icon><CircleCheckFilled /></el-icon>校验通过</span>
        </template>
        <span v-else class="muted">尚未执行校验</span>
      </button>
      <el-scrollbar v-if="validationExpanded" class="issue-list">
        <div v-if="validationResult?.issues.length">
          <button v-for="issue in validationResult.issues" :key="`${issue.rule_code}-${issue.node_id}`" class="issue-row" @click="issue.node_id && focusNode(issue.node_id)">
            <el-tag :type="issue.level === 'ERROR' ? 'danger' : 'warning'" size="small">{{ issue.level }}</el-tag>
            <span class="issue-message">{{ issue.message }}</span><code>{{ issue.path }}</code><small>{{ issue.rule_code }}</small>
          </button>
        </div>
        <el-empty v-else :image-size="48" :description="validationResult ? '没有发现问题' : '点击右上角“校验模型”开始检查'" />
      </el-scrollbar>
    </section>

    <el-dialog v-model="addDialog.visible" title="添加模型节点" width="480px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="父节点"><el-input :model-value="selectedNode?.path" disabled /></el-form-item>
        <el-form-item label="节点类型" required>
          <el-select v-model="addDialog.kind" style="width: 100%" @change="suggestNodeName">
            <el-option v-for="item in selectedNode?.schema?.allowed_children || []" :key="item.kind" :label="item.label" :value="item.kind" />
          </el-select>
        </el-form-item>
        <el-form-item label="节点名称" required>
          <el-input v-model="addDialog.name" maxlength="128" @keyup.enter="createNode" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="addDialog.loading" :disabled="!addDialog.kind || !addDialog.name.trim()" @click="createNode">确认添加</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="deleteDialog.visible" title="删除影响确认" width="560px">
      <div v-loading="deleteDialog.loading" class="delete-impact">
        <el-alert v-if="deleteDialog.impact?.blocking_reason" type="error" :closable="false" show-icon :title="deleteDialog.impact.blocking_reason" />
        <div class="impact-target"><span class="node-symbol small">{{ selectedNode ? nodeAbbr(selectedNode.kind) : '' }}</span><div><strong>{{ selectedNode?.name }}</strong><small>{{ selectedNode?.path }}</small></div></div>
        <div class="impact-stats">
          <div><strong>{{ deleteDialog.impact?.subtree_count ?? '--' }}</strong><span>将删除节点</span></div>
          <div><strong>{{ deleteDialog.impact?.inbound_references.length ?? '--' }}</strong><span>外部引用</span></div>
          <div><strong>{{ deleteDialog.impact?.outbound_reference_count ?? '--' }}</strong><span>下游引用</span></div>
        </div>
        <p>删除会同时移除该节点的全部下级结构，此操作不可撤销。</p>
      </div>
      <template #footer>
        <el-button @click="deleteDialog.visible = false">取消</el-button>
        <el-button type="danger" :disabled="!deleteDialog.impact?.can_delete" :loading="deleteDialog.deleting" @click="deleteNode">确认删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type ElTree } from 'element-plus'
import {
  ArrowLeft, ArrowUp, CircleCheck, CircleCheckFilled, Delete, DocumentChecked, Guide,
  Location, Plus, Refresh, Search,
} from '@element-plus/icons-vue'
import { modelingApi } from '@/api/modelingApi'
import type { DeleteImpact, ModelNode, ModelProject, ValidationResult } from '@/types/modeling'

const props = defineProps<{ projectId: string }>()
const router = useRouter()
const initialLoading = ref(true)
const saving = ref(false)
const validating = ref(false)
const project = ref<ModelProject>()
const treeData = ref<ModelNode[]>([])
const selectedNode = ref<ModelNode>()
const treeRef = ref<InstanceType<typeof ElTree>>()
const treeKeyword = ref('')
const propertyForm = reactive<{ name: string; attributes: Record<string, any>; revision: number }>({ name: '', attributes: {}, revision: 1 })
const savedSnapshot = ref('')
const validationResult = ref<ValidationResult>()
const validationExpanded = ref(false)
const addDialog = reactive({ visible: false, loading: false, kind: '', name: '' })
const deleteDialog = reactive<{ visible: boolean; loading: boolean; deleting: boolean; impact?: DeleteImpact }>({ visible: false, loading: false, deleting: false })

const currentSnapshot = computed(() => JSON.stringify({ name: propertyForm.name, attributes: propertyForm.attributes }))
const dirty = computed(() => !!selectedNode.value && currentSnapshot.value !== savedSnapshot.value)
const canAdd = computed(() => Boolean(selectedNode.value?.schema?.allowed_children.length))

watch(treeKeyword, value => treeRef.value?.filter(value))

function filterTreeNode(value: string, data: ModelNode) {
  if (!value) return true
  const keyword = value.toLowerCase()
  return data.name.toLowerCase().includes(keyword) || data.kind.toLowerCase().includes(keyword)
}

async function loadProject() {
  project.value = await modelingApi.getProject(props.projectId)
}

async function loadTree(selectId?: string) {
  treeData.value = await modelingApi.getTree(props.projectId)
  if (project.value) project.value.node_count = countNodes(treeData.value)
  const target = selectId || selectedNode.value?.id || treeData.value[0]?.id
  if (target) await focusNode(target)
}

function countNodes(nodes: ModelNode[]): number {
  return nodes.reduce((sum, node) => sum + 1 + countNodes(node.children || []), 0)
}

async function selectNode(data: ModelNode) {
  if (dirty.value && selectedNode.value?.id !== data.id) {
    ElMessage.warning('请先保存或撤销右侧未保存的属性修改')
    await nextTick()
    treeRef.value?.setCurrentKey(selectedNode.value?.id || '')
    return
  }
  const detail = await modelingApi.getNode(props.projectId, data.id)
  detail.children = data.children || []
  selectedNode.value = detail
  propertyForm.name = detail.name
  propertyForm.attributes = structuredClone(detail.attributes || {})
  propertyForm.revision = detail.revision
  savedSnapshot.value = currentSnapshot.value
}

function findNode(nodes: ModelNode[], nodeId: string): ModelNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node
    const nested = findNode(node.children || [], nodeId)
    if (nested) return nested
  }
}

async function focusNode(nodeId: string) {
  const node = findNode(treeData.value, nodeId)
  if (!node) return
  await selectNode(node)
  await nextTick()
  treeRef.value?.setCurrentKey(nodeId)
}

function resetForm() {
  if (!selectedNode.value) return
  propertyForm.name = selectedNode.value.name
  propertyForm.attributes = structuredClone(selectedNode.value.attributes || {})
  savedSnapshot.value = currentSnapshot.value
}

async function saveNode() {
  if (!selectedNode.value || !propertyForm.name.trim()) return ElMessage.warning('节点名称不能为空')
  saving.value = true
  try {
    const updated = await modelingApi.updateNode(props.projectId, selectedNode.value.id, {
      name: propertyForm.name.trim(), attributes: propertyForm.attributes, expected_revision: propertyForm.revision,
    })
    ElMessage.success('节点属性已保存')
    if (project.value) project.value.revision += 1
    await loadTree(updated.id)
  } finally { saving.value = false }
}

function openAddDialog() {
  const first = selectedNode.value?.schema?.allowed_children[0]
  if (!first) return
  addDialog.kind = first.kind
  addDialog.name = defaultName(first.kind)
  addDialog.visible = true
}

function defaultName(kind: string) {
  const counts: Record<string, string> = {
    ACCESS_POINT: 'AP1', SERVER: 'Server', LDEVICE: 'LD1', LN0: 'LLN0', LN: 'PTOC1', DOI: 'Do1', DAI: 'stVal',
    DATASET: 'DataSet1', REPORT_CONTROL: 'Report1', GSE_CONTROL: 'Goose1', INPUTS: 'Inputs', FCDA: 'FCDA1', EXT_REF: 'ExtRef1',
    LNODE_TYPE: 'LNodeType1', DO_TYPE: 'DOType1', DA_TYPE: 'DAType1', ENUM_TYPE: 'EnumType1', ENUM_VALUE: 'value1',
  }
  return counts[kind] || `${kind}1`
}

function suggestNodeName(kind: string) { addDialog.name = defaultName(kind) }

async function createNode() {
  if (!selectedNode.value || !addDialog.kind || !addDialog.name.trim()) return
  addDialog.loading = true
  try {
    const attributes: Record<string, unknown> = {}
    if (addDialog.kind === 'LDEVICE') attributes.inst = addDialog.name.trim()
    if (addDialog.kind === 'LN') Object.assign(attributes, { lnClass: addDialog.name.slice(0, 4).toUpperCase(), inst: '1', lnType: '' })
    const node = await modelingApi.createNode(props.projectId, { parent_id: selectedNode.value.id, kind: addDialog.kind, name: addDialog.name.trim(), attributes })
    addDialog.visible = false
    ElMessage.success('节点已添加')
    if (project.value) project.value.revision += 1
    await loadTree(node.id)
  } finally { addDialog.loading = false }
}

async function openDeleteDialog() {
  if (!selectedNode.value) return
  deleteDialog.visible = true
  deleteDialog.loading = true
  deleteDialog.impact = undefined
  try { deleteDialog.impact = await modelingApi.getDeleteImpact(props.projectId, selectedNode.value.id) }
  finally { deleteDialog.loading = false }
}

async function deleteNode() {
  if (!selectedNode.value || !deleteDialog.impact?.can_delete) return
  const parentId = selectedNode.value.parent_id || undefined
  deleteDialog.deleting = true
  try {
    const result = await modelingApi.deleteNode(props.projectId, selectedNode.value.id)
    deleteDialog.visible = false
    selectedNode.value = undefined
    ElMessage.success(`已删除 ${result.deleted_count} 个节点`)
    if (project.value) project.value.revision += 1
    await loadTree(parentId)
  } finally { deleteDialog.deleting = false }
}

async function runValidation() {
  validating.value = true
  try {
    validationResult.value = await modelingApi.validate(props.projectId)
    validationExpanded.value = !validationResult.value.passed
    if (project.value) {
      project.value.validation_errors = validationResult.value.error_count
      project.value.validation_warnings = validationResult.value.warning_count
      project.value.status = validationResult.value.passed ? 'VALID' : 'DRAFT'
    }
    ElMessage[validationResult.value.passed ? 'success' : 'warning'](
      validationResult.value.passed ? '模型基础校验通过' : `发现 ${validationResult.value.error_count} 个错误`,
    )
  } finally { validating.value = false }
}

function nodeAbbr(kind: string) {
  return ({ DATA_TYPE_TEMPLATES: 'DT', ACCESS_POINT: 'AP', REPORT_CONTROL: 'RCB', GSE_CONTROL: 'GCB', LDEVICE: 'LD' } as Record<string, string>)[kind] || kind.slice(0, 3)
}

function nodeDescription(kind: string) {
  return ({
    ROOT: '当前工程的模型根节点，包含 SCL 头、IED 和数据类型模板。', IED: '智能电子设备，是访问点、服务与逻辑设备的容器。',
    LDEVICE: '逻辑设备由 LLN0 和若干业务逻辑节点组成。', LN0: 'LLN0 管理数据集、报告和 GOOSE 控制配置。', LN: '逻辑节点承载设备功能及其实例化数据对象。',
    DATA_TYPE_TEMPLATES: '集中维护逻辑节点、数据对象、数据属性和枚举类型定义。',
  } as Record<string, string>)[kind] || '选择右侧属性表单可编辑该节点的 IEC 61850 配置。'
}

function operationHint(kind: string) {
  return ({
    ROOT: '通常先完善 IED 结构，再维护 DataTypeTemplates；通信配置可在需要生成 SCD 时补充。',
    IED: '一个 IED 可以包含多个 AccessPoint。现场常见装置可从一个 AP1 开始。',
    LDEVICE: 'LLN0 已自动创建。请按装置功能添加 PTOC、XCBR、MMXU 等逻辑节点。',
    LN0: '报告与 GOOSE 控制块应先创建 DataSet，再填写 datSet 引用。',
    DATA_TYPE_TEMPLATES: '建议先创建 LNodeType，并通过 DOType、DAType、EnumType 补齐类型链。',
  } as Record<string, string>)[kind] || '使用左下角“添加子节点”，右侧保存属性；删除前系统会先展示影响范围。'
}

onMounted(async () => {
  try { await Promise.all([loadProject(), loadTree()]) }
  finally { initialLoading.value = false }
})
</script>

<style scoped lang="scss">
.workspace-page { height: calc(100vh - var(--header-height) - var(--tags-height) - var(--footer-height)); display: flex; flex-direction: column; overflow: hidden; background: var(--bg-main); }
.workspace-toolbar { height: 58px; flex: 0 0 58px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; box-sizing: border-box; background: var(--panel-bg); border-bottom: 1px solid var(--sidebar-border); }
.project-identity, .toolbar-actions { display: flex; align-items: center; gap: 9px; }
.project-name { color: var(--text-primary); font-weight: 700; font-size: 15px; }.project-code { color: var(--text-secondary); font-size: 11px; margin-top: 2px; }
.workspace-grid { min-height: 0; flex: 1; display: grid; grid-template-columns: 290px minmax(360px, 1fr) 340px; gap: 1px; background: var(--sidebar-border); }
.panel { min-width: 0; min-height: 0; background: var(--panel-bg); }
.tree-panel, .property-panel { display: flex; flex-direction: column; }
.panel-heading { height: 54px; flex: 0 0 54px; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; border-bottom: 1px solid var(--sidebar-border); box-sizing: border-box; }
.panel-heading strong { display: block; font-size: 14px; }.panel-heading small { color: var(--text-secondary); font-size: 11px; }
.tree-search { padding: 10px 12px; }.tree-scroll, .property-scroll { min-height: 0; flex: 1; }
:deep(.el-tree) { padding: 0 8px 12px; background: transparent; color: var(--text-primary); --el-tree-node-hover-bg-color: var(--item-hover-bg); }
:deep(.el-tree-node__content) { height: 32px; border-radius: 6px; }.tree-node { min-width: 0; width: 100%; display: flex; align-items: center; gap: 7px; padding-right: 5px; }
.kind-dot { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 2px; background: #94a3b8; }.kind-ied .kind-dot, .kind-root .kind-dot { background: var(--color-primary); }.kind-ldevice .kind-dot { background: var(--color-success); }.kind-ln .kind-dot, .kind-ln0 .kind-dot { background: #8b5cf6; }.kind-data_type_templates .kind-dot { background: var(--color-warning); }
.tree-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }.kind-code { margin-left: auto; color: #94a3b8; font-size: 9px; }
.tree-footer, .property-footer { display: flex; gap: 8px; padding: 11px 12px; border-top: 1px solid var(--sidebar-border); }.tree-footer .el-button { flex: 1; margin: 0; }.property-footer { justify-content: flex-end; }
.context-panel { overflow: auto; padding: 18px 22px; box-sizing: border-box; }
.node-breadcrumb { display: flex; align-items: center; gap: 6px; color: var(--text-secondary); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.node-hero { display: flex; align-items: center; gap: 16px; margin: 22px 0; }.node-symbol { display: grid; place-items: center; width: 62px; height: 62px; flex: 0 0 62px; border-radius: 16px; color: var(--color-primary); background: var(--item-active-bg); font-size: 18px; font-weight: 800; }.node-symbol.small { width: 42px; height: 42px; flex-basis: 42px; border-radius: 11px; font-size: 13px; }
.kind-label { color: var(--color-primary); font-size: 11px; font-weight: 700; }.node-hero h2 { margin: 3px 0; color: var(--text-primary); font-size: 23px; }.node-hero p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }.metric-grid > div { padding: 13px; border: 1px solid var(--sidebar-border); border-radius: 10px; background: var(--bg-main); }.metric-grid span, .metric-grid strong { display: block; }.metric-grid span { color: var(--text-secondary); font-size: 11px; }.metric-grid strong { margin-top: 5px; font-size: 13px; }
.guide-card, .children-card { margin-top: 18px; padding: 16px; border: 1px solid var(--sidebar-border); border-radius: 12px; }.guide-heading { display: flex; align-items: center; gap: 7px; }.guide-heading .el-icon { color: var(--color-primary); }.guide-card > p { color: var(--text-secondary); font-size: 13px; line-height: 21px; }.allowed-list { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }.allowed-list > span { color: var(--text-secondary); font-size: 12px; }
.section-row { display: flex; justify-content: space-between; align-items: center; }.section-row span { color: var(--text-secondary); font-size: 11px; }.child-chips { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-top: 12px; }.child-chips button { display: grid; grid-template-columns: 30px 1fr; align-items: center; gap: 8px; padding: 8px; border: 1px solid var(--sidebar-border); border-radius: 9px; color: var(--text-primary); background: var(--panel-bg); text-align: left; cursor: pointer; }.child-chips button:hover { border-color: var(--color-primary); }.child-chips button > span { grid-row: 1 / 3; display: grid; place-items: center; width: 28px; height: 28px; border-radius: 7px; color: var(--color-primary); background: var(--item-active-bg); font-size: 10px; font-weight: 700; }.child-chips small { color: var(--text-secondary); font-size: 9px; }
.property-heading .dirty-tip { color: var(--color-warning); }.property-form { padding: 15px; }.property-form :deep(.el-form-item) { margin-bottom: 15px; }.property-form :deep(.el-form-item__label) { color: var(--text-secondary); font-size: 12px; }
.validation-bar { flex: 0 0 40px; height: 40px; background: var(--panel-bg); border-top: 1px solid var(--sidebar-border); transition: flex-basis .2s, height .2s; }.validation-bar.expanded { flex-basis: 190px; height: 190px; }.validation-summary { width: 100%; height: 40px; display: flex; align-items: center; gap: 10px; padding: 0 16px; border: 0; color: var(--text-primary); background: transparent; cursor: pointer; text-align: left; }.validation-summary .el-icon { transition: transform .2s; }.validation-summary .rotate { transform: rotate(180deg); }.error-count { color: var(--color-danger); }.warning-count { color: var(--color-warning); }.pass-text { display: flex; align-items: center; gap: 4px; color: var(--color-success); }.muted { color: var(--text-secondary); }.issue-list { height: 150px; border-top: 1px solid var(--sidebar-border); }.issue-row { width: 100%; display: grid; grid-template-columns: 70px minmax(200px, 1fr) minmax(180px, 1fr) 160px; align-items: center; gap: 8px; padding: 7px 16px; border: 0; border-bottom: 1px solid var(--sidebar-border); color: var(--text-primary); background: transparent; text-align: left; cursor: pointer; }.issue-row:hover { background: var(--item-hover-bg); }.issue-row code, .issue-row small { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.delete-impact .el-alert { margin-bottom: 14px; }.impact-target { display: flex; align-items: center; gap: 10px; }.impact-target small { display: block; margin-top: 3px; color: var(--text-secondary); }.impact-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 18px 0; }.impact-stats div { padding: 14px; border-radius: 10px; background: var(--bg-main); text-align: center; }.impact-stats strong, .impact-stats span { display: block; }.impact-stats strong { font-size: 21px; }.impact-stats span, .delete-impact p { color: var(--text-secondary); font-size: 12px; }

@media (max-width: 1200px) { .workspace-grid { grid-template-columns: 250px minmax(320px, 1fr) 300px; }.metric-grid { grid-template-columns: 1fr 1fr; } }
</style>
