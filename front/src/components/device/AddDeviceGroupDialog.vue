<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEditMode ? $t('addGroup.titleEdit') : $t('addGroup.titleAdd')"
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
      <el-form-item :label="$t('addGroup.groupCode')" prop="code">
        <el-input
          v-model="form.code"
          :placeholder="$t('addGroup.codePlaceholder')"
          :disabled="isEditMode"
        />
      </el-form-item>

      <el-form-item :label="$t('addGroup.groupName')" prop="name">
        <el-input v-model="form.name" :placeholder="$t('addGroup.namePlaceholder')" />
      </el-form-item>

      <el-form-item :label="$t('addGroup.parentGroup')" prop="parent_id">
        <el-tree-select
          v-model="form.parent_id"
          :data="parentOptions"
          :props="{ label: 'name', value: 'id', children: 'children' }"
          :placeholder="$t('addGroup.parentPlaceholder')"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item :label="$t('addGroup.description')" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          :placeholder="$t('addGroup.descPlaceholder')"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose" round>{{ $t('common.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="loading"
          @click="handleSubmit"
          round
          :icon="Check"
        >
          {{ isEditMode ? $t('addGroup.saveChanges') : $t('addGroup.confirmAdd') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, reactive, watch } from 'vue';
import { useI18n } from 'vue-i18n'
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
  initialParentId?: number | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'success'): void;
  (e: 'close'): void;
}>();

const { t } = useI18n()

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
    { required: true, message: t('addGroup.codeRequired'), trigger: 'blur' },
    { min: 1, max: 32, message: '1-32 characters', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: 'Letters/Numbers/Underscores only', trigger: 'blur' },
  ],
  name: [
    { required: true, message: t('addGroup.nameRequired'), trigger: 'blur' },
    { min: 1, max: 64, message: '1-64 characters', trigger: 'blur' },
  ],
};

watch(() => [props.visible, props.groupId, props.initialParentId], async ([v, gid, initPid]) => {
  if (v) {
    if (gid) {
      try {
        const g = await getDeviceGroup(gid as number);
        if (g) Object.assign(form, { code: g.code, name: g.name, parent_id: g.parent_id, description: g.description || '' });
      } catch (e) {}
    } else {
      resetForm();
      if (initPid) {
        form.parent_id = initPid as number;
      }
    }
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
        ElMessage.success(t('addGroup.updateSuccess'));
      } else {
        await createDeviceGroup(form);
        ElMessage.success(t('addGroup.createSuccess'));
      }
      emit('success');
      handleClose();
    } catch (e: any) {
      console.error(e.message || '操作失败');
      // error message is handled by global interceptor
    } finally { loading.value = false; }
  });
};
</script>
