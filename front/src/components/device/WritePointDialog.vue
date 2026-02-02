<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="400px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <el-form :model="form" label-width="80px">
      <el-form-item label="测点编码" class="center-input">
        <el-input v-model="form.pointCode" disabled />
      </el-form-item>
      <el-form-item label="当前值" class="center-input">
        <el-input v-model="form.currentValue" disabled />
      </el-form-item>
      
      <!-- 遥控 (YK) -->
      <el-form-item v-if="pointType === 2" label="操作">
        <el-radio-group v-model="form.value">
          <el-radio :label="1">合 / 开 (1)</el-radio>
          <el-radio :label="0">分 / 关 (0)</el-radio>
        </el-radio-group>
      </el-form-item>
      
      <!-- 遥调 (YT) -->
      <el-form-item v-else-if="pointType === 3" label="设定值">
        <el-input-number 
          v-model="form.value" 
          :controls="false" 
          class="center-input"
          style="width: 100%" 
        />
      </el-form-item>
      
      <!-- 其他类型 fallback -->
      <el-form-item v-else label="设定值">
        <el-input v-model="form.value" />
      </el-form-item>
    </el-form>
    
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          确认写入
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { editPointData } from '@/api/deviceApi';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  deviceName: { type: String, required: true },
  pointCode: { type: String, required: true },
  currentValue: { type: [Number, String], default: '' },
  pointType: { type: Number, required: true } // 2=YK, 3=YT
});

const emit = defineEmits(['update:modelValue', 'success']);

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const loading = ref(false);
const form = reactive({
  pointCode: '',
  currentValue: '',
  value: 0 as number | string
});

const title = computed(() => {
  return props.pointType === 2 ? '遥控操作' : '遥调设置';
});

watch(() => props.modelValue, (val) => {
  if (val) {
    form.pointCode = props.pointCode;
    form.currentValue = String(props.currentValue);
    form.value = props.pointType === 2 ? 1 : Number(props.currentValue) || 0;
  }
});

const handleSubmit = async () => {
  loading.value = true;
  try {
    const val = Number(form.value);
    const success = await editPointData(props.deviceName, props.pointCode, val);
    if (success) {
      ElMessage.success('写入指令已发送');
      visible.value = false;
      emit('success');
    } else {
      ElMessage.error('写入失败');
    }
  } catch (e) {
    ElMessage.error('操作发生错误');
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
:deep(.center-input .el-input__inner) {
  text-align: center;
}
</style>
