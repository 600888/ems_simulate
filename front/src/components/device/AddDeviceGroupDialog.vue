<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEditMode ? '编辑设备组' : '添加设备组'"
    width="520px"
    :close-on-click-modal="false"
    @close="handleClose"
    class="modern-dialog"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <el-form-item label="组编码" prop="code">
        <el-input 
          v-model="form.code" 
          placeholder="请输入设备组编码，如 GROUP1"
          :disabled="isEditMode"
        />
      </el-form-item>
      
      <el-form-item label="组名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入设备组名称" />
      </el-form-item>
      
      <el-form-item label="父级设备组" prop="parent_id">
        <el-tree-select
          v-model="form.parent_id"
          :data="parentOptions"
          :props="{ label: 'name', value: 'id', children: 'children' }"
          placeholder="选择父级设备组（可选）"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>
      
      <el-form-item label="描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="请输入设备组描述（可选）"
        />
      </el-form-item>
    </el-form>
    
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose" round>取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit" round :icon="Check">
          {{ isEditMode ? '保存修改' : '确认添加' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch } from 'vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { Check } from "@element-plus/icons-vue";
import {
  createDeviceGroup,
  updateDeviceGroup,
  getDeviceGroup,
  type DeviceGroupTreeNode,
  type DeviceGroupCreateRequest,
  type DeviceGroupUpdateRequest,
} from '@/api/deviceGroupApi';

const props = defineProps<{
  visible: boolean;
  groupId?: number | null;
  parentOptions?: DeviceGroupTreeNode[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'success'): void;
  (e: 'close'): void;
}>();

const formRef = ref<FormInstance>();
const loading = ref(false);
const isEditMode = computed(() => !!props.groupId);
const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const form = reactive<DeviceGroupCreateRequest>({
  code: '', name: '', parent_id: null, description: '',
});

const rules: FormRules = {
  code: [
    { required: true, message: '请输入编码', trigger: 'blur' },
    { min: 1, max: 32, message: '1-32字符', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '仅限字母/数字/下划线', trigger: 'blur' },
  ],
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { min: 1, max: 64, message: '1-64字符', trigger: 'blur' },
  ],
};

watch(() => [props.visible, props.groupId], async ([v, gid]) => {
  if (v && gid) {
    try {
      const g = await getDeviceGroup(gid as number);
      if (g) Object.assign(form, { code: g.code, name: g.name, parent_id: g.parent_id, description: g.description || '' });
    } catch (e) {}
  }
}, { immediate: true });

const handleClose = () => {
  dialogVisible.value = false;
  resetForm();
  emit('close');
};

const resetForm = () => {
  Object.assign(form, { code: '', name: '', parent_id: null, description: '' });
  formRef.value?.resetFields();
};

const handleSubmit = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (v) => {
    if (!v) return;
    loading.value = true;
    try {
      if (isEditMode.value && props.groupId) {
        await updateDeviceGroup(props.groupId, { name: form.name, parent_id: form.parent_id, description: form.description });
        ElMessage.success('更新成功');
      } else {
        await createDeviceGroup(form);
        ElMessage.success('创建成功');
      }
      emit('success');
      handleClose();
    } catch (e: any) {
      ElMessage.error(e.message || '操作失败');
    } finally { loading.value = false; }
  });
};
</script>

