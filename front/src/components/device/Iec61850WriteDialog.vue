<template>
  <el-dialog
    v-model="visible"
    :title="$t('writeDialog.title')"
    width="400px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <el-form :model="form" label-width="80px">
      <el-form-item :label="$t('table.pointCode')">
        <el-input v-model="form.pointCode" disabled />
      </el-form-item>
      <el-form-item :label="$t('table.realValue')">
        <el-input :model-value="String(form.currentValue)" disabled />
      </el-form-item>
      <!-- 遥控 (YK): 合/分 -->
      <el-form-item v-if="pointType === 2" :label="$t('common.operation')">
        <el-radio-group v-model="form.writeValue">
          <el-radio :label="1">{{ $t('writeDialog.on') }}</el-radio>
          <el-radio :label="0">{{ $t('writeDialog.off') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <!-- 其他类型: 自由输入 (数值/字符串) -->
      <el-form-item v-else :label="$t('writeDialog.writeValue')">
        <el-input
          v-model="form.writeValue"
          :placeholder="$t('writeDialog.inputPlaceholder')"
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          {{ $t('writeDialog.confirmWrite') }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus';
import { iec61850WritePoint } from '@/api/channelApi';

const { t } = useI18n()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  channelId: { type: Number, required: true },
  pointCode: { type: String, default: '' },
  currentValue: { type: [Number, String], default: '' },
  pointType: { type: Number, default: 0 },
});

const emit = defineEmits(['update:modelValue', 'success']);

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
});

const loading = ref(false);
const form = reactive({
  pointCode: '',
  currentValue: '' as string | number,
  writeValue: '' as string | number,
});

watch(() => props.modelValue, (val) => {
  if (val) {
    form.pointCode = props.pointCode;
    form.currentValue = props.currentValue;
    form.writeValue = props.pointType === 2 ? 1 : String(props.currentValue ?? '');
  }
}, { immediate: true });

const handleSubmit = async () => {
  if (!form.pointCode) {
    ElMessage.warning(t('writeDialog.emptyCode'));
    return;
  }
  loading.value = true;
  try {
    // 智能判断值类型: 纯数字转为数字, 否则保留字符串
    let val: string | number = form.writeValue;
    if (typeof val === 'string' && val.trim() !== '' && !isNaN(Number(val))) {
      val = Number(val);
    }
    const result = await iec61850WritePoint(props.channelId, form.pointCode, val);
    if (result) {
      ElMessage.success(t('writeDialog.writeSent'));
      visible.value = false;
      emit('success');
    }
  } catch (e: any) {
    ElMessage.error(t('writeDialog.writeFailed', { msg: e?.message || e }));
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
::deep(.el-input__inner) {
  text-align: center;
}
</style>
