<template>
  <el-dialog
    v-model="visible"
    title="编辑从机"
    width="400px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <el-form-item label="原从机地址">
        <el-input :value="currentSlaveId" disabled />
      </el-form-item>
      <el-form-item label="新从机地址" prop="new_slave_id">
        <el-input-number
          v-model="formData.new_slave_id"
          :min="0"
          :max="255"
          placeholder="输入新从机地址 (0-255)"
          style="width: 100%"
        />
      </el-form-item>
      <el-alert
        v-if="existingSlaves.length > 0"
        :title="`已存在的从机: ${existingSlaves.join(', ')}`"
        type="info"
        :closable="false"
        style="margin-bottom: 10px;"
      />
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import type { FormInstance, FormRules } from 'element-plus';
import { ElMessage } from 'element-plus';
import { editSlave } from '@/api/deviceApi';

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
  existingSlaves: number[];
  currentSlaveId: number;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'success', newSlaveId: number): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const formRef = ref<FormInstance>();
const loading = ref(false);

const formData = reactive({
  new_slave_id: 1,
});

watch(() => props.currentSlaveId, (val) => {
    formData.new_slave_id = val;
}, { immediate: true });

const validateSlaveId = (_rule: any, value: number, callback: any) => {
  if (value !== props.currentSlaveId && props.existingSlaves.includes(value)) {
    callback(new Error(`从机 ${value} 已存在`));
  } else {
    callback();
  }
};

const rules: FormRules = {
  new_slave_id: [
    { required: true, message: '请输入从机地址', trigger: 'blur' },
    { type: 'number', min: 0, max: 255, message: '从机地址范围: 0-255', trigger: 'blur' },
    { validator: validateSlaveId, trigger: 'blur' }
  ],
};

const handleClose = () => {
  visible.value = false;
  formRef.value?.resetFields();
  // Reset to original on close just in case
  formData.new_slave_id = props.currentSlaveId;
};

const handleSubmit = async () => {
    if (!formRef.value) return;
    
    try {
        await formRef.value.validate();
        
        if (formData.new_slave_id === props.currentSlaveId) {
             handleClose();
             return;
        }

        loading.value = true;
        
        const success = await editSlave(props.deviceName, props.currentSlaveId, formData.new_slave_id);
        if (success) {
            ElMessage.success('编辑从机成功');
            emit('success', formData.new_slave_id);
            handleClose();
        } else {
             ElMessage.error('编辑失败：请检查后台日志或稍后重试');
        }
    } catch (error) {
        console.error('表单验证失败:', error);
    } finally {
        loading.value = false;
    }
};
</script>

<style scoped lang="scss">
:deep(.el-dialog__body) {
  padding-top: 20px;
}
</style>
