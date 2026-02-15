<template>
  <div class="point-mapping-config">
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="3" animated />
    </div>
    <div v-else class="config-form">
      <!-- 如果没有映射，显示创建按钮 -->
      <div v-if="!hasMapping && !isEditing" class="empty-state">
        <p class="info-text">当前测点暂无映射规则</p>
        <!-- DEBUG INFO -->
        <p class="debug-text" style="font-size: 10px; color: #ccc;">
           Device: {{ deviceName }} | Point: {{ targetPointCode }}
        </p>
        <el-button type="primary" size="small" @click="startCreate">
          <el-icon><Plus /></el-icon> 创建映射
        </el-button>
      </div>

      <!-- 编辑/新建表单 -->
      <div v-else>
        <el-form :model="form" label-width="80px">
          <el-form-item label="目标测点">
             <el-tag>{{ targetPointCode }}</el-tag>
          </el-form-item>
          
          <el-form-item label="源测点">
            <div class="source-points-container">
              <div v-for="(item, index) in form.source_point_codes" :key="index" class="source-item">
                <el-tree-select
                  v-model="form.source_point_codes[index].point_code"
                  :lazy="true"
                  :load="loadNode"
                  check-strictly
                  placeholder="请选择源测点"
                  class="source-selector"
                  node-key="code"
                  :props="treeProps"
                >
                  <template #default="{ node, data }">
                    <div class="custom-tree-node">
                       <el-icon class="node-icon">
                         <Folder v-if="!data.type && data.children" />
                         <files v-else-if="!data.type" />
                         <Location v-else />
                       </el-icon>
                       <div class="node-content">
                         <span class="node-label">{{ node.label }}</span>
                         <span v-if="data.type" class="node-tag">{{ data.type }}</span>
                       </div>
                    </div>
                  </template>
                </el-tree-select>
                 <el-input 
                  v-model="form.source_point_codes[index].alias" 
                  placeholder="别名" 
                  class="alias-input"
                />
                <el-button type="danger" circle plain @click="removeSource(index)" v-if="form.source_point_codes.length > 1">
                  <el-icon><Minus /></el-icon>
                </el-button>
              </div>
              <el-button type="dashed" @click="addSource" class="add-btn">
                <el-icon><Plus /></el-icon> 添加源测点
              </el-button>
            </div>
          </el-form-item>

          <el-form-item label="计算公式">
            <el-input 
              v-model="form.formula" 
              type="textarea" 
              :rows="2"
              placeholder="公式 (例如: alias_a + alias_b * 0.5)" 
            />
          </el-form-item>

          <el-form-item label="启用">
            <el-switch v-model="form.enable" />
          </el-form-item>

          <div class="form-actions">
            <el-button @click="cancelEdit">取消</el-button>
            <el-button type="primary" @click="saveMapping" :loading="saving">保存</el-button>
            <el-popconfirm 
              v-if="hasMapping"
              title="确定删除由于此测点的映射吗？" 
              @confirm="handleDeleteMapping"
            >
              <template #reference>
                <el-button type="danger" link>删除映射</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, shallowRef } from 'vue';
import { ElMessage } from 'element-plus';
import { Plus, Minus, Folder, Files, Location } from '@element-plus/icons-vue';
import { 
  getMappings, 
  createMapping, 
  updateMapping, 
  deleteMapping,
  type PointMapping,
  type PointMappingCreate
} from '@/api/pointMappingApi';
import { getPointTree, type DeviceNode } from '@/api/pointTreeApi';

const props = defineProps({
  deviceName: { type: String, required: true },
  targetPointCode: { type: String, required: true }
});

const emit = defineEmits(['update-success']);

const loading = ref(false);
const saving = ref(false);
const hasMapping = ref(false);
const isEditing = ref(false);
const currentMappingId = ref(0);
// Use shallowRef for large tree data to improve performance
const treeData = shallowRef<DeviceNode[]>([]);

// Tree Props (Reuse logic)
const treeProps = {
  label: 'label',
  children: 'children',
  value: 'code', // This MUST be the unique key
  isLeaf: 'leaf', // Explicitly map isLeaf
  disabled: (data: any) => !data.type // Disable selection of non-points (Devices/Groups) if desired. 
  // Wait, if disabled is true, user CANNOT select it. 
  // User said "Can't select". 
  // If "disabled" evaluates to true for Points, that explains why!
  // !data.type -> If data.type exists (Point), disabled is false. So Selectable.
  // If data.type missing (Device), disabled is true. Not selectable.
  // This seems correct for "Source Point".
}

interface SourcePointFormItem {
    point_code: string;
    alias: string;
}

const form = reactive({
  source_point_codes: [] as SourcePointFormItem[],
  formula: '',
  enable: true
});

// Fetch Tree
const fetchTree = async () => {
    // Cache: if data exists, don't fetch again
    if (treeData.value.length > 0) return;

    try {
        const data = await getPointTree();
        const processNode = (nodes: any[], parentDeviceName: string = '') => {
            return nodes.map(node => {
                let newNode = { ...node };
                let currentDeviceName = parentDeviceName;
                if (!node.type && node.children && node.children.some((c:any) => c.type)) {
                     // potential device node
                }
                if (node.children) {
                     if (!parentDeviceName && !node.type) {
                         currentDeviceName = node.label;
                    }
                    newNode.children = processNode(node.children, currentDeviceName);
                    // Generate stable key if possible, but random is okay if once
                    newNode.code = `group_${node.label}_${Math.random()}`;
                } else {
                    newNode.code = `${parentDeviceName}:${node.code}`;
                    newNode.label = `${node.name} (${node.code})`;
                }
                return newNode;
            });
        };
        treeData.value = processNode(data);
    } catch (e) {
        console.error(e);
    }
}


// 获取当前测点的映射
const fetchMapping = async () => {
    if (!props.targetPointCode) return;
    loading.value = true;
    await fetchTree(); 
    try {
        const allMappings = await getMappings();  
        const mapping = allMappings.find(m => 
            m.target_point_code === props.targetPointCode && 
            m.device_name === props.deviceName
        );
        
        if (mapping) {
            hasMapping.value = true;
            currentMappingId.value = mapping.id;
            loadFormData(mapping);
            isEditing.value = true; 
        } else {
            hasMapping.value = false;
            isEditing.value = false;
            resetForm();
        }
    } catch (error) {
        console.error(error);
        ElMessage.error('获取映射信息失败');
    } finally {
        loading.value = false;
    }
};

// Load Node for Lazy Loading
const loadNode = (node: any, resolve: any) => {
  // Top Level: Devices
  if (node.level === 0) {
     const nodes = treeData.value.map((d: any) => ({
        ...d,
        children: undefined, // Strip children to prevent eager recursion
        _children: d.children, // Store for next level
        // Device is leaf ONLY if strictly no children. But typically devices have children.
        leaf: (!d.children || d.children.length === 0) && !!d.type
     }));
     return resolve(nodes);
  }
  
  // Child Row (Points or Groups)
  if (node.data._children && node.data._children.length > 0) {
      const children = node.data._children.map((c: any) => ({
         ...c,
         children: undefined,
         _children: c.children,
         // Force leaf if it has a type (Point), OR if no children
         leaf: !!c.type || (!c.children || c.children.length === 0)
      }));
      resolve(children);
  } else {
      resolve([]);
  }
};

const loadFormData = (mapping: PointMapping) => {
    try {
        const parsed = JSON.parse(mapping.source_point_codes);
        if (Array.isArray(parsed) && parsed.length > 0) {
            if (typeof parsed[0] === 'string') {
                 form.source_point_codes = parsed.map((c: string) => ({ point_code: c, alias: c}));
            } else {
                 form.source_point_codes = parsed.map((item: any) => ({
                    point_code: `${item.device_name}:${item.point_code}`,
                    alias: item.alias
                }));
            }
        } else {
             form.source_point_codes = [{point_code: '', alias: ''}];
        }
    } catch (e) {
        form.source_point_codes = [{point_code: '', alias: ''}];
    }
    form.formula = mapping.formula;
    form.enable = mapping.enable;
};

const resetForm = () => {
    form.source_point_codes = [{point_code: '', alias: ''}];
    form.formula = '';
    form.enable = true;
};

const startCreate = () => {
    isEditing.value = true;
    resetForm();
};

const cancelEdit = () => {
    if (hasMapping.value) {
        fetchMapping();
    } else {
        isEditing.value = false;
    }
};

const addSource = () => form.source_point_codes.push({point_code: '', alias: ''});
const removeSource = (index: number) => form.source_point_codes.splice(index, 1);

const saveMapping = async () => {
    saving.value = true;
    try {
         const apiSources = form.source_point_codes
            .filter(c => c.point_code)
            .map(c => {
                const [dev, code] = c.point_code.split(':');
                return {
                    device_name: dev,
                    point_code: code,
                    alias: c.alias || code
                };
            });

        const data: PointMappingCreate = {
            device_name: props.deviceName,
            target_point_code: props.targetPointCode,
            source_point_codes: apiSources,
            formula: form.formula,
            enable: form.enable
        };

        if (hasMapping.value) {
            await updateMapping(currentMappingId.value, data);
            ElMessage.success('更新成功');
        } else {
            await createMapping(data);
            ElMessage.success('创建成功');
            hasMapping.value = true;
        }
        emit('update-success');
        fetchMapping();
    } catch (error) {
        console.error(error);
        ElMessage.error('保存失败');
    } finally {
        saving.value = false;
    }
};

const handleDeleteMapping = async () => {
    if (!currentMappingId.value) return;
    try {
        await deleteMapping(currentMappingId.value);
        ElMessage.success('删除成功');
        hasMapping.value = false;
        isEditing.value = false;
        resetForm();
        emit('update-success');
    } catch (error) {
        console.error(error);
        ElMessage.error('删除失败');
    }
};

onMounted(() => {
    fetchMapping();
});

watch(() => props.targetPointCode, () => {
    fetchMapping();
});
</script>

<style scoped lang="scss">
/* Container: Match SingleRegister.vue style */
.point-mapping-config {
    margin: 0;
    padding: 16px;
    background-color: var(--panel-bg, #fff); /* Keep var for dark mode, default white */
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    border: 1px solid #e4e7ed;
}

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 32px 0;
    gap: 16px;
    background: #f8fafc;
    border-radius: 8px;
    border: 1px dashed #e2e8f0;
    
    .info-text {
        color: #64748b;
        font-size: 14px;
        margin: 0;
    }
}

.source-points-container {
    display: flex;
    flex-direction: column;
    gap: 8px; /* Reduced gap since items are cleaner */
}

/* Source Item: Remove border/background, make it clean */
.source-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 0; /* Minimal padding */
    background: transparent;
    border: none;
    
    .source-selector {
        flex: 1;
        min-width: 240px; /* Ensure sufficient width for text */
    }

    .alias-input {
        width: 140px;
    }
}

/* Custom Tree Node Styles */
.custom-tree-node {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    width: 100%;
    
    .node-icon {
        font-size: 16px; 
        display: flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        color: #64748b;
    }
    
    .node-content {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex: 1;
        overflow: hidden;
    }

    .node-label {
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: #334155;
    }

    .node-tag {
        font-size: 12px;
        padding: 2px 6px;
        border-radius: 4px;
        margin-left: 8px;
        background: #eff6ff;
        color: #3b82f6;
    }
}

.form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
    padding-top: 20px;
    border-top: 1px solid #f1f5f9;
}

.add-btn {
    width: 100%;
    border-style: dashed;
    height: 40px;
    color: #64748b;
    margin-top: 8px;
    &:hover {
        color: var(--el-color-primary);
        border-color: var(--el-color-primary);
    }
}

/* Dark mode overrides */
:global(.dark) {
    .point-mapping-config {
        background-color: #1e293b;
        border-color: #334155;
    }
    .empty-state {
        background: #0f172a;
        border-color: #334155;
    }
    .info-text { color: #94a3b8; }
    .form-actions { border-top-color: #334155; }
    .custom-tree-node .node-label { color: #e2e8f0; }
    .custom-tree-node .node-icon { color: #94a3b8; }
}
</style>
