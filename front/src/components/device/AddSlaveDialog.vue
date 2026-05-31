<template>
  <el-dialog
    v-model="visible"
    :title="$t('slave.addSlave')"
    width="520px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="120px"
      label-position="right"
    >
      <el-form-item :label="$t('slave.slaveAddress')" prop="slave_id">
        <el-input-number
          v-model="formData.slave_id"
          :min="0"
          :max="255"
          :placeholder="$t('slave.slaveAddressPlaceholder')"
          style="width: 100%"
        />
      </el-form-item>
      <el-alert
        v-if="existingSlaves.length > 0"
        :title="$t('slave.existingSlaves', { list: existingSlaves.join(', ') })"
        type="info"
        :closable="false"
        style="margin-bottom: 10px;"
      />
    </el-form>

    <template #footer>
      <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="loading" @click="handleSubmit">{{ $t('common.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { FormInstance, FormRules } from 'element-plus';
import { ElMessage } from 'element-plus';
import { addSlave } from '@/api/deviceApi';

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
  existingSlaves: number[];
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'success'): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const formRef = ref<FormInstance>();
const loading = ref(false);

const formData = reactive({
  slave_id: 1,
});

const validateSlaveId = (_rule: any, value: number, callback: any) => {
  if (props.existingSlaves.includes(value)) {
    callback(new Error(`从机 ${value} 已存在`));
  } else {
    callback();
  }
};

const rules: FormRules = {
  slave_id: [
    { required: true, message: '请输入从机地址', trigger: 'blur' },
    { type: 'number', min: 0, max: 255, message: '从机地址范围: 0-255', trigger: 'blur' },
    { validator: validateSlaveId, trigger: 'blur' }
  ],
};

const handleClose = () => {
  visible.value = false;
  formRef.value?.resetFields();
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    loading.value = true;
    
    const success = await addSlave(props.deviceName, formData.slave_id);
    if (success) {
      ElMessage.success('添加从机成功');
      emit('success');
      handleClose();
    }
  } catch (error) {
    console.error('添加从机失败:', error);
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
