<template>
  <div v-loading="initialLoading" class="workspace-page">
    <header class="workspace-toolbar">
      <div class="project-identity">
        <el-button
          class="back-button"
          text
          @click="router.push('/scl/modeling')"
          ><el-icon><ArrowLeft /></el-icon>返回</el-button
        >
        <span class="toolbar-divider"></span>
        <div>
          <div class="project-name">{{ project?.name || "模型工作台" }}</div>
          <div class="project-code">
            {{ project?.code }} · {{ project?.file_type }} ·
            {{ project?.standard_version }}
          </div>
        </div>
        <el-tag
          v-if="project"
          size="small"
          :type="
            project.status === 'PUBLISHED'
              ? 'success'
              : project.validation_errors
                ? 'danger'
                : 'info'
          "
        >
          {{ projectStatusLabel(project.status) }}
        </el-tag>
        <el-tag
          v-if="extensionStats.total"
          size="small"
          :type="extensionStats.lossy ? 'danger' : 'warning'"
          effect="plain"
        >
          {{
            extensionStats.lossy
              ? `有损扩展 ${extensionStats.lossy}`
              : `保真扩展 ${extensionStats.total}`
          }}
        </el-tag>
        <span class="save-state" :class="{ dirty }">
          <span class="save-dot"></span
          >{{
            dirty ? "有未应用修改" : `草稿已保存 · r${project?.revision || 1}`
          }}
        </span>
      </div>
      <div class="toolbar-actions">
        <el-button :disabled="!dirty" @click="resetForm">撤销修改</el-button>
        <el-button @click="openVersions"
          ><el-icon><Collection /></el-icon>版本</el-button
        >
        <el-button :loading="validating" @click="runValidation"
          ><el-icon><CircleCheck /></el-icon>校验</el-button
        >
        <el-button type="success" plain @click="openPublishDialog"
          ><el-icon><Promotion /></el-icon>发布</el-button
        >
        <el-dropdown trigger="click">
          <el-button
            ><el-icon><Download /></el-icon>导出<el-icon class="el-icon--right"
              ><ArrowDown /></el-icon
          ></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="openSclPreview"
                ><el-icon><View /></el-icon>预览 SCL</el-dropdown-item
              >
              <el-dropdown-item @click="downloadScl"
                ><el-icon><Download /></el-icon>下载
                {{ project?.file_type || "ICD" }}</el-dropdown-item
              >
              <el-dropdown-item divided @click="downloadArtifactBundle"
                ><el-icon><Files /></el-icon>下载 SCL / CFG / CSV
                产物包</el-dropdown-item
              >
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div class="workspace-grid">
      <aside class="tree-panel panel">
        <div class="panel-heading">
          <div>
            <strong>模型结构</strong
            ><small>{{ project?.node_count || 0 }} 个节点</small>
          </div>
          <el-tooltip content="刷新模型树"
            ><el-button text circle @click="loadTree"
              ><el-icon><Refresh /></el-icon></el-button
          ></el-tooltip>
        </div>
        <div class="tree-search">
          <el-input
            v-model="treeKeyword"
            clearable
            placeholder="搜索节点"
            size="small"
          >
            <template #prefix
              ><el-icon><Search /></el-icon
            ></template>
          </el-input>
          <el-select
            v-model="treeTypeFilter"
            size="small"
            placeholder="全部类型"
            aria-label="节点类型筛选"
          >
            <el-option label="全部类型" value="" />
            <el-option
              v-for="kind in treeKinds"
              :key="kind"
              :label="kindLabel(kind)"
              :value="kind"
            />
          </el-select>
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
              <div
                class="tree-node"
                :class="[
                  `kind-${data.kind.toLowerCase()}`,
                  `status-${childStatus(data).toLowerCase()}`,
                ]"
                :title="`${data.kind_label} · ${data.name}`"
              >
                <span class="tree-icon" aria-hidden="true">
                  <el-icon><component :is="treeNodeIcon(data.kind)" /></el-icon>
                </span>
                <span class="tree-label">{{ data.label }}</span>
                <span
                  v-if="childStatus(data) !== 'NORMAL'"
                  class="tree-problem-dot"
                ></span>
                <span v-if="nodeKindShort(data.kind)" class="kind-code">{{
                  nodeKindShort(data.kind)
                }}</span>
              </div>
            </template>
          </el-tree>
        </el-scrollbar>
        <div class="tree-footer">
          <el-button
            size="small"
            type="primary"
            :disabled="!canAdd"
            @click="openAddDialog('single')"
            ><el-icon><Plus /></el-icon>添加节点</el-button
          >
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="!selectedNode || selectedNode.protected"
            @click="openDeleteDialog"
          >
            <el-icon><Delete /></el-icon>删除
          </el-button>
        </div>
      </aside>

      <main class="context-panel panel">
        <template v-if="selectedNode">
          <div class="context-heading">
            <div>
              <strong>当前节点内容</strong>
              <div class="node-breadcrumb">
                <el-icon><Location /></el-icon
                >{{ displayPath(selectedNode.path) }}
              </div>
            </div>
            <el-tag size="small" effect="plain">{{
              selectedNode.kind_label
            }}</el-tag>
          </div>

          <el-alert
            v-if="isSelectedExtension"
            class="extension-notice"
            :type="selectedExtensionHasLossRisk ? 'error' : 'warning'"
            :closable="false"
            show-icon
          >
            <template #title>
              {{
                selectedExtensionHasLossRisk
                  ? "该扩展存在有损回写风险"
                  : "该节点是只读保真扩展"
              }}
            </template>
            <template #default>
              <p v-if="selectedExtensionHasLossRisk">
                当前 XML
                无法确认可以原位、原语义写回，修复保真策略前会阻止正式发布。
              </p>
              <p v-else>
                这是厂商 Private 或尚未结构化支持的原始
                XML。工具会在导出时按父节点保留，避免静默删除；由于无法完整理解其业务含义，默认不允许直接编辑。
              </p>
              <div class="extension-meta">
                <el-tag size="small" effect="plain"
                  >元素
                  {{ selectedNode.attributes.tag || selectedNode.name }}</el-tag
                >
                <el-tag
                  v-if="selectedNode.attributes.namespace"
                  size="small"
                  effect="plain"
                >
                  命名空间 {{ selectedNode.attributes.namespace }}
                </el-tag>
              </div>
            </template>
          </el-alert>

          <section v-if="selectedNode.kind === 'DO_TYPE'" class="cdc-assistant">
            <div class="cdc-assistant-heading">
              <div>
                <strong
                  ><el-icon><SetUp /></el-icon>CDC 数据属性助手</strong
                >
                <p>
                  当前 CDC：<code>{{
                    selectedNode.attributes.cdc || "未设置"
                  }}</code
                  >。模板作用于该
                  DOType，所有引用它的数据对象都会共享这些属性定义。
                </p>
              </div>
              <el-button
                type="primary"
                plain
                :loading="cdcAssistant.loading"
                :disabled="dirty"
                @click="applyCdcTemplate('common-quality-time-description')"
                >补齐 q / t / dU</el-button
              >
            </div>
            <div class="cdc-template-row">
              <el-select
                v-model="cdcAssistant.templateId"
                placeholder="选择完整 CDC 模板"
                style="min-width: 220px"
              >
                <el-option
                  v-for="template in fullCdcTemplates"
                  :key="template.id"
                  :label="template.name"
                  :value="template.id"
                  :disabled="
                    !!selectedNode.attributes.cdc &&
                    template.cdc !==
                      String(selectedNode.attributes.cdc).toUpperCase()
                  "
                />
              </el-select>
              <el-button
                :loading="cdcAssistant.loading"
                :disabled="dirty || !cdcAssistant.templateId"
                @click="applyCdcTemplate(cdcAssistant.templateId)"
                >应用完整模板</el-button
              >
              <span v-if="selectedCdcTemplate" class="cdc-template-description">
                {{ selectedCdcTemplate.description }}
              </span>
            </div>
            <div v-if="selectedCdcTemplate" class="cdc-attribute-preview">
              <el-tag
                v-for="attribute in selectedCdcTemplate.attributes"
                :key="attribute.name"
                size="small"
                effect="plain"
              >
                {{ attribute.name }} · {{ attribute.bType }} ·
                {{ attribute.fc }}
              </el-tag>
            </div>
            <el-alert
              v-if="cdcAssistant.conflicts.length"
              type="warning"
              :closable="false"
              show-icon
              :title="`${cdcAssistant.conflicts.length} 个已有属性与模板不一致，已保留原配置`"
              description="请在下方子节点中检查冲突属性；系统不会自动覆盖已有 bType、FC 或类型引用。"
            />
          </section>

          <el-tabs v-model="contentTab" class="content-tabs">
            <el-tab-pane
              :label="`子节点 ${selectedNode.children?.length || 0}`"
              name="children"
            >
              <el-table
                v-if="selectedNode.children?.length"
                :data="selectedNode.children"
                height="100%"
                row-key="id"
                highlight-current-row
                class="children-table"
                @row-click="focusChildRow"
              >
                <el-table-column label="名称" min-width="150">
                  <template #default="{ row }">
                    <div class="table-node-name">
                      <span class="node-mini">{{ nodeAbbr(row.kind) }}</span
                      ><strong>{{ row.name }}</strong>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="kind_label"
                  label="类型"
                  min-width="105"
                />
                <el-table-column label="CDC" width="72"
                  ><template #default="{ row }">{{
                    attributeValue(row, ["cdc"]) || "—"
                  }}</template></el-table-column
                >
                <el-table-column label="FC" width="64"
                  ><template #default="{ row }">{{
                    attributeValue(row, ["fc"]) || "—"
                  }}</template></el-table-column
                >
                <el-table-column
                  label="描述"
                  min-width="150"
                  show-overflow-tooltip
                  ><template #default="{ row }">{{
                    attributeValue(row, ["desc", "description"]) || "—"
                  }}</template></el-table-column
                >
                <el-table-column label="状态" width="86">
                  <template #default="{ row }"
                    ><span
                      class="node-status"
                      :class="childStatus(row).toLowerCase()"
                      ><span></span>{{ statusText(childStatus(row)) }}</span
                    ></template
                  >
                </el-table-column>
              </el-table>
              <el-empty
                v-else
                :image-size="72"
                description="当前节点还没有下级内容"
              >
                <el-button
                  v-if="canAdd"
                  type="primary"
                  @click="openAddDialog('single')"
                  ><el-icon><Plus /></el-icon>添加第一个子节点</el-button
                >
              </el-empty>
            </el-tab-pane>

            <el-tab-pane
              :label="`引用关系 ${referenceTotal}`"
              name="references"
            >
              <div class="reference-view">
                <section class="reference-card">
                  <div>
                    <span>被其他节点引用</span
                    ><strong>{{
                      nodeImpact?.inbound_references.length || 0
                    }}</strong>
                  </div>
                  <p>删除或重命名前需要优先处理这些引用。</p>
                </section>
                <section class="reference-card">
                  <div>
                    <span>引用其他节点</span
                    ><strong>{{
                      nodeImpact?.outbound_reference_count || 0
                    }}</strong>
                  </div>
                  <p>当前节点向下游模型建立的关系数量。</p>
                </section>
                <div
                  v-if="nodeImpact?.inbound_references.length"
                  class="reference-list"
                >
                  <div
                    v-for="reference in nodeImpact.inbound_references"
                    :key="reference.id"
                  >
                    <el-tag size="small" effect="plain">{{
                      reference.relation_type
                    }}</el-tag>
                    <code>{{ reference.source_node_id }}</code
                    ><span>→</span><code>{{ reference.target_node_id }}</code>
                  </div>
                </div>
                <el-empty
                  v-else
                  :image-size="64"
                  description="当前节点没有外部引用"
                />
              </div>
            </el-tab-pane>

            <el-tab-pane label="可视化摘要" name="summary">
              <div class="summary-view">
                <section class="summary-hero">
                  <div class="node-symbol">
                    {{ nodeAbbr(selectedNode.kind) }}
                  </div>
                  <div>
                    <span>{{ selectedNode.kind_label }}</span>
                    <h2>{{ selectedNode.name }}</h2>
                    <p>{{ nodeDescription(selectedNode.kind) }}</p>
                  </div>
                </section>
                <section class="metric-grid">
                  <div>
                    <span>节点类型</span
                    ><strong>{{ selectedNode.kind }}</strong>
                  </div>
                  <div>
                    <span>直接子节点</span
                    ><strong>{{ selectedNode.child_count }}</strong>
                  </div>
                  <div>
                    <span>节点修订</span
                    ><strong>r{{ selectedNode.revision }}</strong>
                  </div>
                  <div>
                    <span>结构保护</span
                    ><strong>{{ selectedNode.protected ? "是" : "否" }}</strong>
                  </div>
                </section>
                <section class="guide-card">
                  <div class="guide-heading">
                    <el-icon><Guide /></el-icon><strong>下一步建议</strong>
                  </div>
                  <p>{{ operationHint(selectedNode.kind) }}</p>
                  <div v-if="availableChildOptions.length" class="allowed-list">
                    <span>可添加：</span
                    ><el-tag
                      v-for="child in availableChildOptions"
                      :key="child.kind"
                      size="small"
                      effect="plain"
                      >{{ child.label }}</el-tag
                    >
                  </div>
                </section>
              </div>
            </el-tab-pane>
          </el-tabs>

          <div class="context-actions">
            <div>
              <el-button
                type="primary"
                :disabled="!canAdd"
                @click="openAddDialog('single')"
                ><el-icon><Plus /></el-icon>{{ addActionLabel }}</el-button
              >
              <el-button
                :disabled="!canBatchAdd"
                @click="openAddDialog('batch')"
                >批量添加</el-button
              >
              <el-tooltip content="模板库接口尚未接入当前版本"
                ><span
                  ><el-button disabled>从模板添加</el-button></span
                ></el-tooltip
              >
            </div>
            <span>{{ selectedNode.children?.length || 0 }} 个直接子节点</span>
          </div>
        </template>
        <el-empty v-else description="请从左侧选择一个模型节点" />
      </main>

      <aside class="property-panel panel">
        <div class="panel-heading property-heading">
          <div>
            <strong>属性编辑</strong
            ><small v-if="dirty" class="dirty-tip">有未应用修改</small>
          </div>
          <el-tag v-if="selectedNode" size="small" effect="plain">{{
            selectedNode.kind
          }}</el-tag>
        </div>
        <div v-if="selectedNode" class="property-tabs">
          <button
            :class="{ active: propertyTab === 'basic' }"
            @click="propertyTab = 'basic'"
          >
            基本信息
          </button>
          <button
            :class="{ active: propertyTab === 'advanced' }"
            @click="propertyTab = 'advanced'"
          >
            高级属性 <span>{{ advancedFields.length }}</span>
          </button>
        </div>
        <el-scrollbar class="property-scroll">
          <el-form
            v-if="selectedNode && selectedNode.schema"
            label-position="top"
            class="property-form"
          >
            <template v-for="field in visiblePropertyFields" :key="field.key">
              <el-form-item :required="field.required">
                <template #label
                  ><span>{{ field.label }}</span
                  ><code>{{ field.key }}</code></template
                >
                <el-switch
                  v-if="field.component === 'switch'"
                  v-model="propertyForm.attributes[field.key]"
                  :disabled="isSelectedExtension"
                />
                <el-input-number
                  v-else-if="field.component === 'number'"
                  v-model="propertyForm.attributes[field.key]"
                  :min="0"
                  :disabled="isSelectedExtension"
                  controls-position="right"
                  style="width: 100%"
                />
                <el-select
                  v-else-if="field.component === 'select'"
                  v-model="propertyForm.attributes[field.key]"
                  clearable
                  filterable
                  :disabled="isSelectedExtension"
                  style="width: 100%"
                >
                  <el-option
                    v-for="option in field.options || []"
                    :key="option"
                    :label="option || '无'"
                    :value="option"
                  />
                </el-select>
                <el-input
                  v-else-if="field.key === 'name'"
                  v-model="propertyForm.name"
                  :disabled="selectedNode.kind === 'LN0'"
                  :readonly="isSelectedExtension"
                />
                <el-input
                  v-else
                  v-model="propertyForm.attributes[field.key]"
                  :type="field.component === 'textarea' ? 'textarea' : 'text'"
                  :rows="3"
                  :clearable="!isSelectedExtension"
                  :readonly="isSelectedExtension"
                />
              </el-form-item>
            </template>
            <el-empty
              v-if="!visiblePropertyFields.length"
              :image-size="56"
              description="当前节点没有该分组属性"
            />
          </el-form>
          <el-empty v-else :image-size="64" description="选择节点后编辑属性" />
        </el-scrollbar>
        <div v-if="selectedNode" class="property-reference-summary">
          <span>引用 {{ nodeImpact?.outbound_reference_count || 0 }}</span
          ><span>被引用 {{ nodeImpact?.inbound_references.length || 0 }}</span>
        </div>
        <div class="property-footer">
          <el-button :disabled="!dirty" @click="resetForm">恢复</el-button>
          <el-button
            type="primary"
            :disabled="!dirty || isSelectedExtension"
            :loading="saving"
            @click="saveNode"
            ><el-icon><DocumentChecked /></el-icon>应用</el-button
          >
        </div>
      </aside>
    </div>

    <section class="validation-bar" :class="{ expanded: validationExpanded }">
      <button
        class="validation-summary"
        @click="validationExpanded = !validationExpanded"
      >
        <el-icon :class="{ rotate: validationExpanded }"><ArrowUp /></el-icon>
        <strong>问题</strong>
        <template v-if="validationResult">
          <span class="error-count"
            >{{ validationResult.error_count }} 错误</span
          >
          <span class="warning-count"
            >{{ validationResult.warning_count }} 警告</span
          >
          <span v-if="validationResult.passed" class="pass-text"
            ><el-icon><CircleCheckFilled /></el-icon>校验通过</span
          >
        </template>
        <span v-else class="muted">尚未执行校验</span>
        <span class="validation-spacer"></span>
        <small>{{
          validationExpanded ? "收起面板" : "展开问题、规则与路径"
        }}</small>
      </button>
      <el-scrollbar v-if="validationExpanded" class="issue-list">
        <div v-if="validationResult?.issues.length">
          <button
            v-for="issue in validationResult.issues"
            :key="`${issue.rule_code}-${issue.node_id}`"
            class="issue-row"
            @click="issue.node_id && focusNode(issue.node_id)"
          >
            <el-tag
              :type="issue.level === 'ERROR' ? 'danger' : 'warning'"
              size="small"
              >{{ issue.level }}</el-tag
            >
            <span class="issue-message">{{ issue.message }}</span
            ><code>{{ issue.path }}</code
            ><small>{{ issue.rule_code }}</small>
          </button>
        </div>
        <el-empty
          v-else
          :image-size="48"
          :description="
            validationResult ? '没有发现问题' : '点击右上角“校验模型”开始检查'
          "
        />
      </el-scrollbar>
    </section>

    <el-dialog
      v-model="addDialog.visible"
      :title="addDialog.batch ? '批量添加模型节点' : '添加模型节点'"
      width="500px"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item label="父节点"
          ><el-input :model-value="selectedNode?.path" disabled
        /></el-form-item>
        <el-form-item label="节点类型" required>
          <el-select
            v-model="addDialog.kind"
            style="width: 100%"
            @change="suggestNodeName"
          >
            <el-option
              v-for="item in addDialogChildOptions"
              :key="item.kind"
              :label="item.label"
              :value="item.kind"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="节点名称" required>
          <el-input
            v-model="addDialog.name"
            maxlength="128"
            @keyup.enter="createNode"
          />
        </el-form-item>
        <el-form-item v-if="addDialog.batch" label="创建数量" required>
          <el-input-number
            v-model="addDialog.quantity"
            :min="2"
            :max="20"
            controls-position="right"
          />
          <span class="batch-hint"
            >按名称尾部数字连续编号，最多一次创建 20 个。</span
          >
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="addDialog.loading"
          :disabled="!addDialog.kind || !addDialog.name.trim()"
          @click="createNode"
        >
          {{
            addDialog.batch ? `创建 ${addDialog.quantity} 个节点` : "确认添加"
          }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteDialog.visible"
      title="删除影响确认"
      width="560px"
    >
      <div v-loading="deleteDialog.loading" class="delete-impact">
        <el-alert
          v-if="deleteDialog.impact?.blocking_reason"
          type="error"
          :closable="false"
          show-icon
          :title="deleteDialog.impact.blocking_reason"
        />
        <div class="impact-target">
          <span class="node-symbol small">{{
            selectedNode ? nodeAbbr(selectedNode.kind) : ""
          }}</span>
          <div>
            <strong>{{ selectedNode?.name }}</strong
            ><small>{{ selectedNode?.path }}</small>
          </div>
        </div>
        <div class="impact-stats">
          <div>
            <strong>{{ deleteDialog.impact?.subtree_count ?? "--" }}</strong
            ><span>将删除节点</span>
          </div>
          <div>
            <strong>{{
              deleteDialog.impact?.inbound_references.length ?? "--"
            }}</strong
            ><span>外部引用</span>
          </div>
          <div>
            <strong>{{
              deleteDialog.impact?.outbound_reference_count ?? "--"
            }}</strong
            ><span>下游引用</span>
          </div>
        </div>
        <p>删除会同时移除该节点的全部下级结构，此操作不可撤销。</p>
      </div>
      <template #footer>
        <el-button @click="deleteDialog.visible = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="!deleteDialog.impact?.can_delete"
          :loading="deleteDialog.deleting"
          @click="deleteNode"
          >确认删除</el-button
        >
      </template>
    </el-dialog>

    <el-drawer
      v-model="versionsDrawer.visible"
      title="模型版本"
      size="480px"
      destroy-on-close
    >
      <div class="version-create-card">
        <div class="version-create-title">
          <strong>创建当前快照</strong
          ><small>保存 r{{ project?.revision }} 的完整模型结构</small>
        </div>
        <el-input
          v-model="versionsDrawer.label"
          maxlength="128"
          placeholder="版本名称，例如：保护配置初稿"
        />
        <el-input
          v-model="versionsDrawer.description"
          type="textarea"
          :rows="2"
          maxlength="512"
          placeholder="版本说明（可选）"
        />
        <el-button
          type="primary"
          :loading="versionsDrawer.creating"
          @click="createVersion"
          >创建快照</el-button
        >
      </div>
      <div class="version-list-heading">
        <strong>历史版本</strong><span>{{ versions.length }} 个版本</span>
      </div>
      <div v-loading="versionsDrawer.loading" class="version-list">
        <article
          v-for="version in versions"
          :key="version.id"
          class="version-item"
        >
          <div
            class="version-marker"
            :class="{ published: version.status === 'PUBLISHED' }"
          >
            V{{ version.version_number }}
          </div>
          <div class="version-content">
            <div class="version-title-row">
              <strong>{{ version.label }}</strong>
              <el-tag
                v-if="version.status === 'PUBLISHED'"
                type="success"
                size="small"
                >已发布</el-tag
              >
            </div>
            <p>{{ version.description || "无版本说明" }}</p>
            <small
              >源修订 r{{ version.source_revision }} ·
              {{ formatDateTime(version.created_at) }}</small
            >
          </div>
          <div class="version-actions">
            <el-button text type="primary" @click="restoreVersion(version)"
              >恢复</el-button
            >
            <el-button
              v-if="version.status !== 'PUBLISHED'"
              text
              type="danger"
              @click="deleteVersion(version)"
              >删除</el-button
            >
          </div>
        </article>
        <el-empty
          v-if="!versionsDrawer.loading && !versions.length"
          :image-size="64"
          description="还没有版本快照"
        />
      </div>
    </el-drawer>

    <el-dialog
      v-model="previewDialog.visible"
      title="SCL XML 预览"
      width="82%"
      top="5vh"
      destroy-on-close
    >
      <div class="preview-meta">
        <div>
          <strong>{{ previewDialog.artifact?.filename }}</strong
          ><span
            >{{ formatBytes(previewDialog.artifact?.size || 0) }} · r{{
              previewDialog.artifact?.revision
            }}</span
          >
        </div>
        <el-button :loading="downloading" @click="downloadScl"
          ><el-icon><Download /></el-icon>下载文件</el-button
        >
      </div>
      <el-scrollbar class="xml-preview">
        <pre>{{ previewDialog.artifact?.xml }}</pre>
      </el-scrollbar>
    </el-dialog>

    <el-dialog
      v-model="publishDialog.visible"
      title="发布模型"
      width="520px"
      destroy-on-close
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="发布前会重新执行结构校验与 SCL 完整性校验。"
      />
      <el-alert
        v-if="extensionStats.total"
        class="publish-extension-alert"
        :type="extensionStats.lossy ? 'error' : 'warning'"
        :closable="false"
        show-icon
        :title="
          extensionStats.lossy
            ? `存在 ${extensionStats.lossy} 个有损扩展，当前不能发布`
            : `模型包含 ${extensionStats.total} 个只读保真扩展`
        "
        :description="
          extensionStats.lossy
            ? '请先处理标记为有损风险的 XML 片段，再执行发布。'
            : '这些扩展会随 SCL 一并保留；发布校验会再次检查是否存在确认的有损风险。'
        "
      />
      <el-form label-position="top" class="publish-form">
        <el-form-item label="发布版本名称" required>
          <el-input
            v-model="publishDialog.label"
            maxlength="128"
            placeholder="例如：现场投运 V1.0"
          />
        </el-form-item>
        <el-form-item label="发布说明">
          <el-input
            v-model="publishDialog.description"
            type="textarea"
            :rows="3"
            maxlength="512"
            placeholder="记录本次发布的范围和变更"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="publishDialog.visible = false">取消</el-button>
        <el-button
          type="success"
          :loading="publishDialog.publishing"
          :disabled="!publishDialog.label.trim() || extensionStats.lossy > 0"
          @click="publishProject"
        >
          校验并发布
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import type { Component } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox, type ElTree } from "element-plus";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Bell,
  Box,
  CircleCheck,
  CircleCheckFilled,
  Coin,
  Connection,
  Cpu,
  DataLine,
  Delete,
  Document,
  DocumentChecked,
  Download,
  EditPen,
  Files,
  FolderOpened,
  Grid,
  Guide,
  Collection,
  CollectionTag,
  Link,
  Location,
  Menu,
  Monitor,
  Operation,
  Plus,
  Promotion,
  Refresh,
  Search,
  SetUp,
  Share,
  Tickets,
  View,
} from "@element-plus/icons-vue";
import { modelingApi, type CdcTemplate } from "@/api/modelingApi";
import type {
  DeleteImpact,
  ModelNode,
  ModelProject,
  ModelVersion,
  SclArtifact,
  ValidationResult,
} from "@/types/modeling";

const props = defineProps<{ projectId: string }>();
const router = useRouter();
const initialLoading = ref(true);
const saving = ref(false);
const validating = ref(false);
const project = ref<ModelProject>();
const treeData = ref<ModelNode[]>([]);
const selectedNode = ref<ModelNode>();
const nodeImpact = ref<DeleteImpact>();
const treeRef = ref<InstanceType<typeof ElTree>>();
const treeKeyword = ref("");
const treeTypeFilter = ref("");
const contentTab = ref("children");
const propertyTab = ref<"basic" | "advanced">("basic");
const propertyForm = reactive<{
  name: string;
  attributes: Record<string, any>;
  revision: number;
}>({ name: "", attributes: {}, revision: 1 });
const savedSnapshot = ref("");
const validationResult = ref<ValidationResult>();
const validationExpanded = ref(false);
const cdcTemplates = ref<CdcTemplate[]>([]);
const cdcAssistant = reactive<{
  loading: boolean;
  templateId: string;
  conflicts: Array<{ name: string }>;
}>({ loading: false, templateId: "", conflicts: [] });
const downloading = ref(false);
const versions = ref<ModelVersion[]>([]);
const versionsDrawer = reactive({
  visible: false,
  loading: false,
  creating: false,
  label: "",
  description: "",
});
const previewDialog = reactive<{
  visible: boolean;
  loading: boolean;
  artifact?: SclArtifact;
}>({ visible: false, loading: false });
const publishDialog = reactive({
  visible: false,
  publishing: false,
  label: "",
  description: "",
});
const addDialog = reactive({
  visible: false,
  loading: false,
  batch: false,
  quantity: 2,
  kind: "",
  name: "",
});
const deleteDialog = reactive<{
  visible: boolean;
  loading: boolean;
  deleting: boolean;
  impact?: DeleteImpact;
}>({ visible: false, loading: false, deleting: false });

const currentSnapshot = computed(() =>
  JSON.stringify({
    name: propertyForm.name,
    attributes: propertyForm.attributes,
  }),
);
const dirty = computed(
  () => !!selectedNode.value && currentSnapshot.value !== savedSnapshot.value,
);
const extensionNodes = computed(() =>
  flattenNodes(treeData.value).filter((node) => node.kind === "EXTENSION"),
);
const extensionStats = computed(() => ({
  total: extensionNodes.value.length,
  lossy: extensionNodes.value.filter((node) =>
    isTruthyFlag(node.attributes.lossRisk),
  ).length,
}));
const isSelectedExtension = computed(
  () => selectedNode.value?.kind === "EXTENSION",
);
const selectedExtensionHasLossRisk = computed(
  () =>
    isSelectedExtension.value &&
    isTruthyFlag(selectedNode.value?.attributes.lossRisk),
);
const fullCdcTemplates = computed(() =>
  cdcTemplates.value.filter((template) => template.mode === "CDC"),
);
const selectedCdcTemplate = computed(() =>
  fullCdcTemplates.value.find(
    (template) => template.id === cdcAssistant.templateId,
  ),
);
const singletonChildKinds = new Set([
  "HEADER",
  "COMMUNICATION",
  "DATA_TYPE_TEMPLATES",
  "LN0",
  "SERVER",
  "INPUTS",
  "ADDRESS",
  "SERVICES",
  "HISTORY",
  "TRG_OPS",
  "OPT_FIELDS",
  "RPT_ENABLED",
  "SETTING_CONTROL",
]);
const availableChildOptions = computed(() => {
  const children = selectedNode.value?.children || [];
  return (selectedNode.value?.schema?.allowed_children || []).filter(
    (option) =>
      !singletonChildKinds.has(option.kind) ||
      !children.some((child) => child.kind === option.kind),
  );
});
const canAdd = computed(() => availableChildOptions.value.length > 0);
const canBatchAdd = computed(() =>
  availableChildOptions.value.some(
    (option) => !singletonChildKinds.has(option.kind),
  ),
);
const addDialogChildOptions = computed(() =>
  addDialog.batch
    ? availableChildOptions.value.filter(
        (option) => !singletonChildKinds.has(option.kind),
      )
    : availableChildOptions.value,
);
const referenceTotal = computed(
  () =>
    (nodeImpact.value?.inbound_references.length || 0) +
    (nodeImpact.value?.outbound_reference_count || 0),
);
const basicFieldKeys = new Set([
  "name",
  "desc",
  "description",
  "manufacturer",
  "type",
  "inst",
  "lnClass",
  "prefix",
  "configVersion",
]);
const basicFields = computed(
  () =>
    selectedNode.value?.schema?.fields.filter((field) =>
      basicFieldKeys.has(field.key),
    ) || [],
);
const advancedFields = computed(
  () =>
    selectedNode.value?.schema?.fields.filter(
      (field) => !basicFieldKeys.has(field.key),
    ) || [],
);
const visiblePropertyFields = computed(() =>
  propertyTab.value === "basic" ? basicFields.value : advancedFields.value,
);
const treeKinds = computed(() =>
  Array.from(
    new Set(flattenNodes(treeData.value).map((node) => node.kind)),
  ).sort(),
);
const addActionLabel = computed(() => {
  const children = availableChildOptions.value;
  return children.length === 1 ? `添加${children[0].label}` : "添加子节点";
});

watch([treeKeyword, treeTypeFilter], ([keyword, kind]) =>
  treeRef.value?.filter({ keyword, kind }),
);

function filterTreeNode(
  value: { keyword: string; kind: string },
  data: ModelNode,
) {
  const keyword = value?.keyword?.trim().toLowerCase() || "";
  const matchesKeyword =
    !keyword ||
    data.name.toLowerCase().includes(keyword) ||
    data.kind.toLowerCase().includes(keyword);
  const matchesKind = !value?.kind || data.kind === value.kind;
  return matchesKeyword && matchesKind;
}

async function loadProject() {
  project.value = await modelingApi.getProject(props.projectId);
}

async function loadTree(selectId?: string) {
  treeData.value = await modelingApi.getTree(props.projectId);
  if (project.value) project.value.node_count = countNodes(treeData.value);
  const target = selectId || selectedNode.value?.id || treeData.value[0]?.id;
  if (target) await focusNode(target);
}

function countNodes(nodes: ModelNode[]): number {
  return nodes.reduce(
    (sum, node) => sum + 1 + countNodes(node.children || []),
    0,
  );
}

function flattenNodes(nodes: ModelNode[]): ModelNode[] {
  return nodes.flatMap((node) => [node, ...flattenNodes(node.children || [])]);
}

function isTruthyFlag(value: unknown) {
  return value === true || value === 1 || value === "1" || value === "true";
}

async function selectNode(data: ModelNode) {
  if (dirty.value && selectedNode.value?.id !== data.id) {
    ElMessage.warning("请先保存或撤销右侧未保存的属性修改");
    await nextTick();
    treeRef.value?.setCurrentKey(selectedNode.value?.id || "");
    return;
  }
  const [detail, impact] = await Promise.all([
    modelingApi.getNode(props.projectId, data.id),
    modelingApi
      .getDeleteImpact(props.projectId, data.id)
      .catch(() => undefined),
  ]);
  detail.children = data.children || [];
  selectedNode.value = detail;
  nodeImpact.value = impact;
  propertyTab.value = detail.kind === "EXTENSION" ? "advanced" : "basic";
  if (detail.kind === "DO_TYPE") {
    const cdc = String(detail.attributes.cdc || "").toUpperCase();
    cdcAssistant.templateId =
      fullCdcTemplates.value.find((template) => template.cdc === cdc)?.id ||
      fullCdcTemplates.value[0]?.id ||
      "";
  }
  cdcAssistant.conflicts = [];
  propertyForm.name = detail.name;
  propertyForm.attributes = structuredClone(detail.attributes || {});
  propertyForm.revision = detail.revision;
  savedSnapshot.value = currentSnapshot.value;
}

function findNode(nodes: ModelNode[], nodeId: string): ModelNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node;
    const nested = findNode(node.children || [], nodeId);
    if (nested) return nested;
  }
}

async function focusNode(nodeId: string) {
  const node = findNode(treeData.value, nodeId);
  if (!node) return;
  await selectNode(node);
  await nextTick();
  treeRef.value?.setCurrentKey(nodeId);
}

function focusChildRow(row: ModelNode) {
  void focusNode(row.id);
}

function resetForm() {
  if (!selectedNode.value) return;
  propertyForm.name = selectedNode.value.name;
  propertyForm.attributes = structuredClone(
    selectedNode.value.attributes || {},
  );
  savedSnapshot.value = currentSnapshot.value;
}

async function saveNode() {
  if (isSelectedExtension.value)
    return ElMessage.warning("保真扩展默认只读，不能直接修改原始 XML");
  if (!selectedNode.value || !propertyForm.name.trim())
    return ElMessage.warning("节点名称不能为空");
  saving.value = true;
  try {
    const updated = await modelingApi.updateNode(
      props.projectId,
      selectedNode.value.id,
      {
        name: propertyForm.name.trim(),
        attributes: propertyForm.attributes,
        expected_revision: propertyForm.revision,
      },
    );
    ElMessage.success("节点属性已保存");
    await Promise.all([loadProject(), loadTree(updated.id)]);
  } finally {
    saving.value = false;
  }
}

async function applyCdcTemplate(templateId: string) {
  if (!selectedNode.value || selectedNode.value.kind !== "DO_TYPE") return;
  if (dirty.value)
    return ElMessage.warning("请先保存或撤销当前 DOType 的属性修改");
  cdcAssistant.loading = true;
  try {
    const nodeId = selectedNode.value.id;
    const result = await modelingApi.applyCdcTemplate(
      props.projectId,
      nodeId,
      templateId,
    );
    await Promise.all([loadProject(), loadTree(nodeId)]);
    cdcAssistant.conflicts = result.conflicts;
    if (result.conflicts.length) {
      ElMessage.warning(
        `已新增 ${result.created.length} 项，${result.conflicts.length} 项冲突保持原值`,
      );
    } else if (result.changed) {
      ElMessage.success(`已补齐 ${result.created.length} 个数据属性/依赖类型`);
    } else {
      ElMessage.info("所需属性已经存在，无需重复创建");
    }
  } finally {
    cdcAssistant.loading = false;
  }
}

function openAddDialog(mode: "single" | "batch" = "single") {
  addDialog.batch = mode === "batch";
  const first = addDialogChildOptions.value[0];
  if (!first) return;
  addDialog.quantity = 2;
  addDialog.kind = first.kind;
  addDialog.name = nextAvailableName(first.kind);
  addDialog.visible = true;
}

function defaultName(kind: string) {
  const counts: Record<string, string> = {
    ACCESS_POINT: "AP1",
    SERVER: "Server",
    LDEVICE: "LD1",
    LN0: "LLN0",
    LN: "PTOC1",
    DOI: "Do1",
    DAI: "stVal",
    DATASET: "DataSet1",
    REPORT_CONTROL: "Report1",
    TRG_OPS: "TrgOps",
    OPT_FIELDS: "OptFields",
    RPT_ENABLED: "RptEnabled",
    CLIENT_LN: "ClientLN1",
    GSE_CONTROL: "Goose1",
    SETTING_CONTROL: "SettingControl",
    INPUTS: "Inputs",
    FCDA: "FCDA1",
    EXT_REF: "ExtRef1",
    LNODE_TYPE: "LNodeType1",
    DO_TYPE: "DOType1",
    DA_TYPE: "DAType1",
    ENUM_TYPE: "EnumType1",
    ENUM_VALUE: "value1",
    COMMUNICATION: "Communication",
    SUBNETWORK: "StationBus",
    CONNECTED_AP: "ConnectedAP1",
    ADDRESS: "Address",
    P: "IP",
    GSE: "GSE1",
    SMV: "SMV1",
    DO_DEF: "Do1",
    DA_DEF: "stVal",
    SDO_DEF: "SubDo1",
    BDA_DEF: "value",
    SERVICES: "Services",
    SERVICE_CAPABILITY: "GetDirectory",
    HISTORY: "History",
    HITEM: "Hitem1",
    AUTHENTICATION: "Authentication",
    VAL: "Val",
  };
  return counts[kind] || `${kind}1`;
}

function nextAvailableName(kind: string) {
  const base = defaultName(kind);
  const siblings = (selectedNode.value?.children || [])
    .filter((node) => node.kind === kind)
    .map((node) => node.name);
  if (!siblings.includes(base)) return base;
  const match = base.match(/^(.*?)(\d+)$/);
  if (!match) return `${base}${siblings.length + 1}`;
  const maxSuffix = siblings.reduce((max, name) => {
    const siblingMatch = name.match(
      new RegExp(`^${match[1].replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\d+)$`),
    );
    return siblingMatch ? Math.max(max, Number(siblingMatch[1])) : max;
  }, Number(match[2]));
  return `${match[1]}${maxSuffix + 1}`;
}

function suggestNodeName(kind: string) {
  addDialog.name = nextAvailableName(kind);
}

async function createNode() {
  if (!selectedNode.value || !addDialog.kind || !addDialog.name.trim()) return;
  addDialog.loading = true;
  try {
    const quantity = addDialog.batch ? addDialog.quantity : 1;
    let node: ModelNode | undefined;
    for (let index = 0; index < quantity; index += 1) {
      const name =
        quantity === 1
          ? addDialog.name.trim()
          : incrementNodeName(addDialog.name.trim(), index);
      node = await modelingApi.createNode(props.projectId, {
        parent_id: selectedNode.value.id,
        kind: addDialog.kind,
        name,
        attributes: defaultAttributes(addDialog.kind, name),
      });
    }
    addDialog.visible = false;
    ElMessage.success(
      quantity === 1 ? "节点已添加" : `已连续创建 ${quantity} 个节点`,
    );
    await Promise.all([loadProject(), loadTree(node?.id)]);
  } finally {
    addDialog.loading = false;
  }
}

function incrementNodeName(base: string, offset: number) {
  const match = base.match(/^(.*?)(\d+)$/);
  if (!match) return offset === 0 ? base : `${base}${offset + 1}`;
  return `${match[1]}${Number(match[2]) + offset}`;
}

function defaultAttributes(
  kind: string,
  name: string,
): Record<string, unknown> {
  const lnClass = name.slice(0, 4).toUpperCase();
  if (kind === "LDEVICE") return { inst: name };
  if (kind === "LN") return { lnClass, inst: name.slice(4) || "1", lnType: "" };
  if (kind === "SUBNETWORK")
    return { type: "8-MMS", bitRate: 100, multiplier: "M" };
  if (kind === "P") return { type: name, value: "" };
  if (kind === "LNODE_TYPE") return { id: name, lnClass: "LLN0" };
  if (kind === "DO_TYPE") return { id: name, cdc: "SPS" };
  if (kind === "DA_TYPE" || kind === "ENUM_TYPE") return { id: name };
  if (kind === "DA_DEF") return { bType: "BOOLEAN", fc: "ST", dchg: true };
  if (kind === "BDA_DEF") return { bType: "BOOLEAN" };
  if (kind === "ENUM_VALUE") return { ord: 0, value: name };
  if (kind === "FCDA") return { fc: "ST" };
  if (kind === "REPORT_CONTROL")
    return { datSet: "", buffered: false, confRev: 1, bufTime: 0, intgPd: 0 };
  if (kind === "TRG_OPS")
    return { dchg: true, qchg: true, dupd: false, period: true, gi: true };
  if (kind === "OPT_FIELDS")
    return {
      seqNum: true,
      timeStamp: true,
      reasonCode: true,
      dataSet: true,
      dataRef: false,
      bufOvfl: true,
      entryID: true,
      configRef: true,
      segmentation: false,
    };
  if (kind === "RPT_ENABLED") return { max: 1 };
  if (kind === "GSE_CONTROL") return { datSet: "", appID: name, confRev: 1 };
  if (kind === "SETTING_CONTROL") return { actSG: 1, numOfSGs: 1 };
  if (kind === "SERVICE_CAPABILITY") return { tag: name };
  if (kind === "VAL") return { value: "" };
  return {};
}

async function openDeleteDialog() {
  if (!selectedNode.value) return;
  deleteDialog.visible = true;
  deleteDialog.loading = true;
  deleteDialog.impact = undefined;
  try {
    deleteDialog.impact = await modelingApi.getDeleteImpact(
      props.projectId,
      selectedNode.value.id,
    );
    nodeImpact.value = deleteDialog.impact;
  } finally {
    deleteDialog.loading = false;
  }
}

async function deleteNode() {
  if (!selectedNode.value || !deleteDialog.impact?.can_delete) return;
  const parentId = selectedNode.value.parent_id || undefined;
  deleteDialog.deleting = true;
  try {
    const result = await modelingApi.deleteNode(
      props.projectId,
      selectedNode.value.id,
    );
    deleteDialog.visible = false;
    selectedNode.value = undefined;
    nodeImpact.value = undefined;
    ElMessage.success(`已删除 ${result.deleted_count} 个节点`);
    await Promise.all([loadProject(), loadTree(parentId)]);
  } finally {
    deleteDialog.deleting = false;
  }
}

async function runValidation() {
  validating.value = true;
  try {
    validationResult.value = await modelingApi.validate(props.projectId);
    validationExpanded.value = !validationResult.value.passed;
    if (project.value) {
      project.value.validation_errors = validationResult.value.error_count;
      project.value.validation_warnings = validationResult.value.warning_count;
      project.value.status = validationResult.value.passed ? "VALID" : "DRAFT";
    }
    ElMessage[validationResult.value.passed ? "success" : "warning"](
      validationResult.value.passed
        ? "模型基础校验通过"
        : `发现 ${validationResult.value.error_count} 个错误`,
    );
  } finally {
    validating.value = false;
  }
}

function nodeAbbr(kind: string) {
  return (
    (
      {
        DATA_TYPE_TEMPLATES: "DT",
        ACCESS_POINT: "AP",
        REPORT_CONTROL: "RCB",
        GSE_CONTROL: "GCB",
        LDEVICE: "LD",
      } as Record<string, string>
    )[kind] || kind.slice(0, 3)
  );
}

const treeNodeIcons: Record<string, Component> = {
  ROOT: FolderOpened,
  HEADER: Document,
  COMMUNICATION: Connection,
  SUBNETWORK: Share,
  CONNECTED_AP: Link,
  ADDRESS: Location,
  P: EditPen,
  GSE: Promotion,
  SMV: DataLine,
  IED: Cpu,
  ACCESS_POINT: Connection,
  SERVER: Monitor,
  LDEVICE: Box,
  LN0: Grid,
  LN: Grid,
  DOI: DataLine,
  SDI: Operation,
  DAI: EditPen,
  DATASET: SetUp,
  REPORT_CONTROL: Bell,
  GSE_CONTROL: Promotion,
  INPUTS: Download,
  FCDA: Link,
  EXT_REF: Share,
  DATA_TYPE_TEMPLATES: Tickets,
  LNODE_TYPE: Files,
  DO_TYPE: CollectionTag,
  DA_TYPE: CollectionTag,
  ENUM_TYPE: Coin,
  DO_DEF: DataLine,
  DA_DEF: EditPen,
  SDO_DEF: Operation,
  BDA_DEF: EditPen,
  ENUM_VALUE: Menu,
};

function treeNodeIcon(kind: string) {
  return treeNodeIcons[kind] || Menu;
}

function nodeKindShort(kind: string) {
  return (
    (
      {
        ROOT: "SCL",
        HEADER: "HDR",
        COMMUNICATION: "COM",
        SUBNETWORK: "NET",
        CONNECTED_AP: "CAP",
        IED: "IED",
        ACCESS_POINT: "AP",
        SERVER: "SRV",
        LDEVICE: "LD",
        LN0: "LN0",
        LN: "LN",
        DOI: "DO",
        SDI: "SDO",
        DAI: "DA",
        DATASET: "DS",
        REPORT_CONTROL: "RCB",
        GSE_CONTROL: "GCB",
        INPUTS: "IN",
        FCDA: "FCDA",
        EXT_REF: "EXT",
        DATA_TYPE_TEMPLATES: "DTT",
        LNODE_TYPE: "LNT",
        DO_TYPE: "DOT",
        DA_TYPE: "DAT",
        ENUM_TYPE: "ENUM",
        DO_DEF: "DO",
        DA_DEF: "DA",
      } as Record<string, string>
    )[kind] || ""
  );
}

function kindLabel(kind: string) {
  return (
    flattenNodes(treeData.value).find((node) => node.kind === kind)
      ?.kind_label || kind
  );
}

function displayPath(path?: string) {
  return path?.split("/").join(" / ") || "—";
}

function attributeValue(node: ModelNode, keys: string[]) {
  for (const key of keys) {
    const value = node.attributes?.[key];
    if (value !== undefined && value !== null && value !== "")
      return String(value);
  }
  return "";
}

function childStatus(node: ModelNode): "ERROR" | "WARNING" | "NORMAL" {
  const issues =
    validationResult.value?.issues.filter(
      (issue) => issue.node_id === node.id,
    ) || [];
  if (issues.some((issue) => issue.level === "ERROR")) return "ERROR";
  if (issues.some((issue) => issue.level === "WARNING")) return "WARNING";
  return "NORMAL";
}

function statusText(status: "ERROR" | "WARNING" | "NORMAL") {
  return ({ ERROR: "错误", WARNING: "警告", NORMAL: "正常" } as const)[status];
}

function nodeDescription(kind: string) {
  return (
    (
      {
        ROOT: "当前工程的模型根节点，包含 SCL 头、IED 和数据类型模板。",
        IED: "智能电子设备，是访问点、服务与逻辑设备的容器。",
        LDEVICE: "逻辑设备由 LLN0 和若干业务逻辑节点组成。",
        LN0: "LLN0 管理数据集、报告和 GOOSE 控制配置。",
        LN: "逻辑节点承载设备功能及其实例化数据对象。",
        DATA_TYPE_TEMPLATES:
          "集中维护逻辑节点、数据对象、数据属性和枚举类型定义。",
      } as Record<string, string>
    )[kind] || "选择右侧属性表单可编辑该节点的 IEC 61850 配置。"
  );
}

function operationHint(kind: string) {
  return (
    (
      {
        ROOT: "通常先完善 IED 结构，再维护 DataTypeTemplates；通信配置可在需要生成 SCD 时补充。",
        IED: "一个 IED 可以包含多个 AccessPoint。现场常见装置可从一个 AP1 开始。",
        LDEVICE:
          "LLN0 已自动创建。请按装置功能添加 PTOC、XCBR、MMXU 等逻辑节点。",
        LN0: "报告与 GOOSE 控制块应先创建 DataSet，再填写 datSet 引用。",
        DATA_TYPE_TEMPLATES:
          "建议先创建 LNodeType，并通过 DOType、DAType、EnumType 补齐类型链。",
      } as Record<string, string>
    )[kind] ||
    "使用左下角“添加子节点”，右侧保存属性；删除前系统会先展示影响范围。"
  );
}

function projectStatusLabel(status: ModelProject["status"]) {
  return (
    (
      {
        DRAFT: "草稿",
        VALID: "校验通过",
        PUBLISHED: "已发布",
        ARCHIVED: "已归档",
      } as const
    )[status] || status
  );
}

function formatDateTime(value: string) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

async function loadVersions() {
  versionsDrawer.loading = true;
  try {
    versions.value = await modelingApi.listVersions(props.projectId);
  } finally {
    versionsDrawer.loading = false;
  }
}

async function openVersions() {
  if (dirty.value) return ElMessage.warning("请先保存或撤销节点属性修改");
  versionsDrawer.visible = true;
  await loadVersions();
}

async function createVersion() {
  if (dirty.value) return ElMessage.warning("请先保存当前节点修改");
  versionsDrawer.creating = true;
  try {
    await modelingApi.createVersion(props.projectId, {
      label: versionsDrawer.label,
      description: versionsDrawer.description,
    });
    versionsDrawer.label = "";
    versionsDrawer.description = "";
    ElMessage.success("当前模型已保存为版本快照");
    await loadVersions();
  } finally {
    versionsDrawer.creating = false;
  }
}

async function restoreVersion(version: ModelVersion) {
  if (dirty.value) return ElMessage.warning("请先保存或撤销节点属性修改");
  try {
    await ElMessageBox.confirm(
      `将当前模型恢复为“${version.label}”，恢复前建议先创建当前快照。`,
      "恢复模型版本",
      {
        type: "warning",
        confirmButtonText: "确认恢复",
        cancelButtonText: "取消",
      },
    );
    const result = await modelingApi.restoreVersion(
      props.projectId,
      version.id,
    );
    versionsDrawer.visible = false;
    validationResult.value = undefined;
    ElMessage.success(`已恢复 ${result.node_count} 个模型节点`);
    await Promise.all([loadProject(), loadTree()]);
  } catch (error) {
    if (error !== "cancel" && error !== "close") throw error;
  }
}

async function deleteVersion(version: ModelVersion) {
  try {
    await ElMessageBox.confirm(
      `确认删除版本快照“${version.label}”？`,
      "删除版本",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
      },
    );
    await modelingApi.deleteVersion(props.projectId, version.id);
    ElMessage.success("版本快照已删除");
    await loadVersions();
  } catch (error) {
    if (error !== "cancel" && error !== "close") throw error;
  }
}

async function openSclPreview() {
  if (dirty.value) return ElMessage.warning("请先保存或撤销节点属性修改");
  previewDialog.loading = true;
  try {
    previewDialog.artifact = await modelingApi.previewScl(props.projectId);
    previewDialog.visible = true;
  } finally {
    previewDialog.loading = false;
  }
}

async function downloadScl() {
  if (dirty.value) return ElMessage.warning("请先保存或撤销节点属性修改");
  downloading.value = true;
  try {
    const artifact = await modelingApi.downloadScl(props.projectId);
    const blob = new Blob([artifact.content], {
      type: "application/xml;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = artifact.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    ElMessage.success(`已生成 ${artifact.filename}`);
  } finally {
    downloading.value = false;
  }
}

async function downloadArtifactBundle() {
  if (dirty.value) return ElMessage.warning("请先保存或撤销节点属性修改");
  downloading.value = true;
  try {
    const bundle = await modelingApi.downloadArtifacts(props.projectId);
    const url = URL.createObjectURL(bundle.content);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = bundle.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    ElMessage.success(`已生成可追溯产物包 ${bundle.filename}`);
  } finally {
    downloading.value = false;
  }
}

function openPublishDialog() {
  if (dirty.value) return ElMessage.warning("请先保存或撤销节点属性修改");
  publishDialog.label = `现场发布 r${project.value?.revision || 1}`;
  publishDialog.description = "";
  publishDialog.visible = true;
}

async function publishProject() {
  if (!publishDialog.label.trim()) return;
  publishDialog.publishing = true;
  try {
    const result = await modelingApi.publish(props.projectId, {
      label: publishDialog.label.trim(),
      description: publishDialog.description,
    });
    validationResult.value = result.validation;
    publishDialog.visible = false;
    ElMessage.success(`模型已发布：${result.artifact.filename}`);
    await Promise.all([loadProject(), loadVersions()]);
  } finally {
    publishDialog.publishing = false;
  }
}

onMounted(async () => {
  try {
    const [, , templates] = await Promise.all([
      loadProject(),
      loadTree(),
      modelingApi.listCdcTemplates(),
    ]);
    cdcTemplates.value = templates;
    if (selectedNode.value?.kind === "DO_TYPE")
      await selectNode(selectedNode.value);
  } finally {
    initialLoading.value = false;
  }
});
</script>

<style scoped lang="scss">
.workspace-page {
  height: 100%;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--text-primary);
  background: var(--bg-main);
}
.workspace-toolbar {
  height: 58px;
  flex: 0 0 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  box-sizing: border-box;
  background: var(--panel-bg);
  border-bottom: 1px solid var(--sidebar-border);
}
.project-identity,
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.back-button {
  padding-inline: 4px;
}
.toolbar-divider {
  width: 1px;
  height: 24px;
  background: var(--sidebar-border);
}
.project-name {
  color: var(--text-primary);
  font-weight: 700;
  font-size: 15px;
}
.project-code {
  color: var(--text-secondary);
  font-size: 10px;
  margin-top: 2px;
}
.save-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: 3px;
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}
.save-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
}
.save-state.dirty {
  color: var(--color-warning);
}
.save-state.dirty .save-dot {
  background: var(--color-warning);
}
.workspace-grid {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: 300px minmax(400px, 1fr) 370px;
  gap: 1px;
  background: var(--sidebar-border);
}
.panel {
  min-width: 0;
  min-height: 0;
  background: var(--panel-bg);
}
.tree-panel,
.property-panel,
.context-panel {
  display: flex;
  flex-direction: column;
}
.panel-heading {
  height: 54px;
  flex: 0 0 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid var(--sidebar-border);
  box-sizing: border-box;
}
.panel-heading strong {
  display: block;
  font-size: 14px;
}
.panel-heading small {
  color: var(--text-secondary);
  font-size: 11px;
}
.tree-search {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 96px;
  gap: 7px;
  padding: 11px 12px;
  border-bottom: 1px solid var(--sidebar-border);
  background: color-mix(in srgb, var(--panel-bg) 94%, #f8fafc);
}
.tree-search :deep(.el-input__wrapper),
.tree-search :deep(.el-select__wrapper) {
  border-radius: 7px;
  box-shadow: 0 0 0 1px var(--sidebar-border) inset;
}
.tree-scroll,
.property-scroll {
  min-height: 0;
  flex: 1;
}
:deep(.el-tree) {
  padding: 9px 9px 16px;
  background: transparent;
  color: var(--text-primary);
  --el-tree-node-hover-bg-color: transparent;
}
:deep(.el-tree-node__content) {
  position: relative;
  height: 38px;
  margin: 1px 0;
  padding-left: 3px !important;
  border: 1px solid transparent;
  border-radius: 8px;
  box-sizing: border-box;
  transition:
    color 0.16s ease,
    background 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}
:deep(.el-tree-node__content:hover) {
  background: color-mix(in srgb, var(--item-hover-bg) 76%, transparent);
}
:deep(.el-tree-node.is-current > .el-tree-node__content) {
  border-color: rgba(59, 130, 246, 0.2);
  background: linear-gradient(
    90deg,
    rgba(59, 130, 246, 0.13),
    rgba(99, 102, 241, 0.055)
  );
  box-shadow:
    0 2px 7px rgba(37, 99, 235, 0.08),
    inset 3px 0 0 var(--color-primary);
}
:deep(.el-tree-node__expand-icon) {
  width: 18px;
  height: 18px;
  margin-right: 2px;
  padding: 0;
  color: #94a3b8;
  font-size: 12px;
  border-radius: 5px;
  transition:
    transform 0.2s ease,
    color 0.16s ease,
    background 0.16s ease;
}
:deep(.el-tree-node__expand-icon:not(.is-leaf):hover) {
  color: var(--color-primary);
  background: rgba(59, 130, 246, 0.1);
}
:deep(.el-tree-node__expand-icon.is-leaf) {
  color: transparent;
}
:deep(.el-tree-node__children) {
  position: relative;
  margin-left: 18px;
}
:deep(.el-tree-node__children::before) {
  content: "";
  position: absolute;
  z-index: 0;
  top: -2px;
  bottom: 20px;
  left: -9px;
  width: 1px;
  background: #dbe3ee;
}
:deep(
  .el-tree-node__children > .el-tree-node > .el-tree-node__content::before
) {
  content: "";
  position: absolute;
  top: 18px;
  left: -9px;
  width: 10px;
  height: 1px;
  background: #dbe3ee;
}
.tree-node {
  --node-color: #64748b;
  --node-bg: #f1f5f9;
  position: relative;
  z-index: 1;
  min-width: 0;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 7px;
}
.tree-icon {
  display: grid;
  place-items: center;
  width: 25px;
  height: 25px;
  flex: 0 0 25px;
  border: 1px solid color-mix(in srgb, var(--node-color) 18%, transparent);
  border-radius: 7px;
  color: var(--node-color);
  background: var(--node-bg);
  box-sizing: border-box;
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
}
.tree-icon .el-icon {
  font-size: 14px;
}
:deep(.el-tree-node__content:hover) .tree-icon {
  transform: translateY(-1px);
  box-shadow: 0 3px 7px color-mix(in srgb, var(--node-color) 15%, transparent);
}
:deep(.el-tree-node.is-current > .el-tree-node__content) .tree-icon {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--node-color) 14%, transparent);
}
.tree-label {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  line-height: 1;
}
.kind-root .tree-label,
.kind-ied .tree-label,
.kind-ldevice .tree-label,
.kind-ln .tree-label,
.kind-ln0 .tree-label {
  font-weight: 600;
}
.kind-code {
  margin-left: auto;
  padding: 2px 5px;
  border: 1px solid color-mix(in srgb, var(--node-color) 18%, transparent);
  border-radius: 5px;
  color: var(--node-color);
  background: var(--node-bg);
  font-size: 8px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.2px;
}
.tree-problem-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  border: 2px solid var(--panel-bg);
  border-radius: 50%;
  box-sizing: content-box;
}
.status-warning .tree-problem-dot {
  background: var(--color-warning);
}
.status-error .tree-problem-dot {
  background: var(--color-danger);
}
.kind-root {
  --node-color: #2563eb;
  --node-bg: #eaf2ff;
}
.kind-header {
  --node-color: #64748b;
  --node-bg: #f1f5f9;
}
.kind-communication,
.kind-subnetwork,
.kind-connected_ap,
.kind-address {
  --node-color: #0891b2;
  --node-bg: #e7f9fc;
}
.kind-ied {
  --node-color: #4f46e5;
  --node-bg: #eef0ff;
}
.kind-access_point,
.kind-server {
  --node-color: #0284c7;
  --node-bg: #eaf7ff;
}
.kind-ldevice {
  --node-color: #059669;
  --node-bg: #e9fbf3;
}
.kind-ln,
.kind-ln0 {
  --node-color: #7c3aed;
  --node-bg: #f3edff;
}
.kind-doi,
.kind-sdi,
.kind-dai,
.kind-do_def,
.kind-da_def,
.kind-sdo_def,
.kind-bda_def {
  --node-color: #d97706;
  --node-bg: #fff7e6;
}
.kind-dataset,
.kind-fcda {
  --node-color: #0f766e;
  --node-bg: #e9f8f5;
}
.kind-report_control {
  --node-color: #db2777;
  --node-bg: #fff0f6;
}
.kind-gse_control,
.kind-gse,
.kind-smv {
  --node-color: #dc2626;
  --node-bg: #fff0f0;
}
.kind-data_type_templates,
.kind-lnode_type,
.kind-do_type,
.kind-da_type,
.kind-enum_type,
.kind-enum_value {
  --node-color: #9333ea;
  --node-bg: #f7efff;
}
.tree-footer,
.property-footer {
  display: flex;
  gap: 8px;
  padding: 11px 12px;
  border-top: 1px solid var(--sidebar-border);
}
.tree-footer .el-button {
  flex: 1;
  margin: 0;
}
.property-footer {
  justify-content: flex-end;
}
.context-heading {
  height: 66px;
  flex: 0 0 66px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 18px;
  border-bottom: 1px solid var(--sidebar-border);
  box-sizing: border-box;
}
.context-heading strong {
  font-size: 14px;
}
.extension-notice {
  flex: 0 0 auto;
  margin: 12px 14px 0;
}
.extension-notice p {
  margin: 4px 0 8px;
  line-height: 1.6;
}
.extension-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cdc-assistant {
  display: grid;
  gap: 10px;
  flex: 0 0 auto;
  margin: 12px 14px 0;
  padding: 12px 14px;
  border: 1px solid
    color-mix(in srgb, var(--color-primary) 24%, var(--sidebar-border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-primary) 5%, var(--panel-bg));
}
.cdc-assistant-heading,
.cdc-template-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cdc-assistant-heading {
  justify-content: space-between;
}
.cdc-assistant-heading strong {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cdc-assistant-heading p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.cdc-template-description {
  min-width: 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.cdc-attribute-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.node-breadcrumb {
  display: flex;
  align-items: center;
  gap: 5px;
  max-width: min(520px, 48vw);
  margin-top: 5px;
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.content-tabs {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.content-tabs :deep(.el-tabs__header) {
  flex: 0 0 auto;
  margin: 0;
  padding: 0 18px;
}
.content-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: var(--sidebar-border);
}
.content-tabs :deep(.el-tabs__item) {
  height: 45px;
  font-size: 12px;
}
.content-tabs :deep(.el-tabs__content) {
  min-height: 0;
  flex: 1;
}
.content-tabs :deep(.el-tab-pane) {
  height: 100%;
}
.children-table {
  --el-table-border-color: var(--sidebar-border);
  --el-table-header-bg-color: var(--bg-main);
  --el-table-row-hover-bg-color: var(--item-hover-bg);
  cursor: pointer;
}
.children-table :deep(th.el-table__cell) {
  height: 38px;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
}
.children-table :deep(td.el-table__cell) {
  height: 44px;
  font-size: 12px;
}
.table-node-name {
  display: flex;
  align-items: center;
  gap: 8px;
}
.node-mini {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  color: var(--color-primary);
  background: var(--item-active-bg);
  font-size: 9px;
  font-weight: 800;
}
.node-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
}
.node-status > span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.node-status.normal {
  color: var(--color-success);
}
.node-status.normal > span {
  background: var(--color-success);
}
.node-status.warning {
  color: var(--color-warning);
}
.node-status.warning > span {
  background: var(--color-warning);
}
.node-status.error {
  color: var(--color-danger);
}
.node-status.error > span {
  background: var(--color-danger);
}
.context-actions {
  height: 56px;
  flex: 0 0 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 14px;
  border-top: 1px solid var(--sidebar-border);
}
.context-actions > div {
  display: flex;
  gap: 8px;
}
.context-actions > span {
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}
.reference-view,
.summary-view {
  height: 100%;
  padding: 18px;
  overflow: auto;
  box-sizing: border-box;
}
.reference-view {
  display: grid;
  grid-template-columns: 1fr 1fr;
  align-content: start;
  gap: 12px;
}
.reference-card {
  padding: 16px;
  border: 1px solid var(--sidebar-border);
  border-radius: 10px;
  background: var(--bg-main);
}
.reference-card > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.reference-card span,
.reference-card p {
  color: var(--text-secondary);
  font-size: 12px;
}
.reference-card strong {
  color: var(--color-primary);
  font-size: 24px;
}
.reference-card p {
  margin: 10px 0 0;
  line-height: 19px;
}
.reference-list {
  grid-column: 1 / -1;
  border: 1px solid var(--sidebar-border);
  border-radius: 10px;
  overflow: hidden;
}
.reference-list > div {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr) 16px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--sidebar-border);
}
.reference-list > div:last-child {
  border-bottom: 0;
}
.reference-list code {
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
}
.summary-hero {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 18px;
}
.node-symbol {
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  flex: 0 0 58px;
  border-radius: 14px;
  color: var(--color-primary);
  background: var(--item-active-bg);
  font-size: 17px;
  font-weight: 800;
}
.node-symbol.small {
  width: 42px;
  height: 42px;
  flex-basis: 42px;
  border-radius: 11px;
  font-size: 13px;
}
.summary-hero span {
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 700;
}
.summary-hero h2 {
  margin: 2px 0;
  font-size: 21px;
}
.summary-hero p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.metric-grid > div {
  padding: 13px;
  border: 1px solid var(--sidebar-border);
  border-radius: 9px;
  background: var(--bg-main);
}
.metric-grid span,
.metric-grid strong {
  display: block;
}
.metric-grid span {
  color: var(--text-secondary);
  font-size: 11px;
}
.metric-grid strong {
  margin-top: 5px;
  font-size: 13px;
}
.guide-card {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--sidebar-border);
  border-radius: 10px;
}
.guide-heading {
  display: flex;
  align-items: center;
  gap: 7px;
}
.guide-heading .el-icon {
  color: var(--color-primary);
}
.guide-card > p {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 20px;
}
.allowed-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.allowed-list > span {
  color: var(--text-secondary);
  font-size: 12px;
}
.property-tabs {
  display: flex;
  flex: 0 0 44px;
  height: 44px;
  padding: 0 14px;
  border-bottom: 1px solid var(--sidebar-border);
  box-sizing: border-box;
}
.property-tabs button {
  position: relative;
  padding: 0 12px;
  border: 0;
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
}
.property-tabs button.active {
  color: var(--color-primary);
  font-weight: 600;
}
.property-tabs button.active::after {
  content: "";
  position: absolute;
  right: 8px;
  bottom: -1px;
  left: 8px;
  height: 2px;
  background: var(--color-primary);
}
.property-tabs button span {
  padding: 1px 5px;
  border-radius: 8px;
  background: var(--bg-main);
  font-size: 9px;
}
.property-heading .dirty-tip {
  color: var(--color-warning);
}
.property-form {
  padding: 15px;
}
.property-form :deep(.el-form-item) {
  margin-bottom: 15px;
}
.property-form :deep(.el-form-item__label) {
  display: flex;
  justify-content: space-between;
  width: 100%;
  color: var(--text-secondary);
  font-size: 12px;
}
.property-form :deep(.el-form-item__label code) {
  color: #94a3b8;
  font-size: 9px;
  font-weight: 400;
}
.property-reference-summary {
  display: flex;
  gap: 14px;
  padding: 10px 14px;
  border-top: 1px solid var(--sidebar-border);
  color: var(--text-secondary);
  font-size: 11px;
}
.validation-bar {
  flex: 0 0 40px;
  height: 40px;
  background: var(--panel-bg);
  border-top: 1px solid var(--sidebar-border);
  transition:
    flex-basis 0.2s,
    height 0.2s;
}
.validation-bar.expanded {
  flex-basis: 220px;
  height: 220px;
}
.validation-summary {
  width: 100%;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border: 0;
  color: var(--text-primary);
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.validation-summary .el-icon {
  transition: transform 0.2s;
}
.validation-summary .rotate {
  transform: rotate(180deg);
}
.validation-summary small {
  color: var(--text-secondary);
}
.validation-spacer {
  flex: 1;
}
.error-count {
  color: var(--color-danger);
}
.warning-count {
  color: var(--color-warning);
}
.pass-text {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--color-success);
}
.muted {
  color: var(--text-secondary);
}
.issue-list {
  height: 180px;
  border-top: 1px solid var(--sidebar-border);
}
.issue-row {
  width: 100%;
  display: grid;
  grid-template-columns: 70px minmax(200px, 1fr) minmax(180px, 1fr) 160px;
  align-items: center;
  gap: 8px;
  padding: 7px 16px;
  border: 0;
  border-bottom: 1px solid var(--sidebar-border);
  color: var(--text-primary);
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.issue-row:hover {
  background: var(--item-hover-bg);
}
.issue-row code,
.issue-row small {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.batch-hint {
  margin-left: 10px;
  color: var(--text-secondary);
  font-size: 11px;
}
.delete-impact .el-alert {
  margin-bottom: 14px;
}
.impact-target {
  display: flex;
  align-items: center;
  gap: 10px;
}
.impact-target small {
  display: block;
  margin-top: 3px;
  color: var(--text-secondary);
}
.impact-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 18px 0;
}
.impact-stats div {
  padding: 14px;
  border-radius: 10px;
  background: var(--bg-main);
  text-align: center;
}
.impact-stats strong,
.impact-stats span {
  display: block;
}
.impact-stats strong {
  font-size: 21px;
}
.impact-stats span,
.delete-impact p {
  color: var(--text-secondary);
  font-size: 12px;
}
.version-create-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 15px;
  border: 1px solid rgba(59, 130, 246, 0.24);
  border-radius: 12px;
  background: var(--item-hover-bg);
}
.version-create-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.version-create-title small {
  color: var(--text-secondary);
}
.version-create-card .el-button {
  align-self: flex-end;
}
.version-list-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 22px 0 10px;
}
.version-list-heading span {
  color: var(--text-secondary);
  font-size: 12px;
}
.version-list {
  min-height: 180px;
}
.version-item {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 11px;
  padding: 14px 4px;
  border-bottom: 1px solid var(--sidebar-border);
}
.version-marker {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  color: var(--color-primary);
  background: var(--item-active-bg);
  font-size: 11px;
  font-weight: 800;
}
.version-marker.published {
  color: var(--color-success);
  background: var(--status-normal-bg);
}
.version-title-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.version-content p {
  margin: 5px 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.version-content small {
  color: #94a3b8;
}
.version-actions {
  grid-column: 2;
  display: flex;
  justify-content: flex-end;
}
.preview-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.preview-meta strong,
.preview-meta span {
  display: block;
}
.preview-meta span {
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 11px;
}
.xml-preview {
  height: 68vh;
  border: 1px solid var(--sidebar-border);
  border-radius: 10px;
  background: #0f172a;
}
.xml-preview pre {
  margin: 0;
  padding: 18px;
  color: #dbeafe;
  font:
    12px/1.7 Consolas,
    "Courier New",
    monospace;
  white-space: pre;
}
.publish-form {
  margin-top: 16px;
}
.publish-extension-alert {
  margin-top: 10px;
}

@container (max-width: 1399px) {
  .workspace-grid {
    grid-template-columns: 260px minmax(360px, 1fr) 320px;
  }
  .toolbar-actions .el-button {
    padding-inline: 9px;
  }
  .toolbar-actions {
    gap: 4px;
  }
  .save-state {
    display: none;
  }
}
@container (max-width: 1200px) {
  .workspace-grid {
    grid-template-columns: 235px minmax(340px, 1fr) 290px;
  }
  .metric-grid {
    grid-template-columns: 1fr 1fr;
  }
  .toolbar-actions .el-button {
    font-size: 0;
    padding-inline: 10px;
  }
  .toolbar-actions .el-icon {
    margin: 0;
    font-size: 15px;
  }
  .project-code {
    display: none;
  }
  .context-actions .el-button:nth-child(n + 2) {
    display: none;
  }
}
</style>
