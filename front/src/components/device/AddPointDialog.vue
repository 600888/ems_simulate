<template>
  <el-dialog
    v-model="visible"
    :title="isBatch ? '批量添加测点' : '添加测点'"
    width="560px"
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
      <!-- 添加模式切换 -->
      <el-form-item label="添加模式">
        <el-radio-group v-model="isBatch">
          <el-radio :value="false">单个添加</el-radio>
          <el-radio :value="true">批量添加</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="测点类型" prop="frame_type">
        <el-select v-model="formData.frame_type" placeholder="选择测点类型" style="width: 100%">
          <el-option label="遥测 (YC)" :value="0" />
          <el-option label="遥信 (YX)" :value="1" />
          <el-option label="遥控 (YK)" :value="2" />
          <el-option label="遥调 (YT)" :value="3" />
        </el-select>
      </el-form-item>

      <!-- 批量模式：数量输入 -->
      <template v-if="isBatch">
        <el-form-item label="添加数量" prop="batchCount">
          <el-input-number v-model="batchCount" :min="1" :max="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="起始地址" prop="reg_addr">
          <el-input v-model="formData.reg_addr" placeholder="如: 0 或 0x0000" />
        </el-form-item>
        <el-form-item label="编码前缀">
          <el-input v-model="codePrefix" placeholder="如: POINT_" />
        </el-form-item>
        <el-form-item label="名称前缀">
          <el-input v-model="namePrefix" placeholder="如: 测点" />
        </el-form-item>
      </template>

      <!-- 单个模式：编码和名称输入 -->
      <template v-else>
        <el-form-item label="测点编码" prop="code">
          <el-input v-model="formData.code" placeholder="输入测点编码" />
        </el-form-item>

        <el-form-item label="测点名称" prop="name">
          <el-input v-model="formData.name" placeholder="输入测点名称" />
        </el-form-item>

        <el-form-item label="寄存器地址" prop="reg_addr">
          <el-input v-model="formData.reg_addr" placeholder="如: 0x0000 或 0" />
        </el-form-item>
      </template>

      <el-form-item label="从机地址" prop="rtu_addr">
        <el-select v-model="formData.rtu_addr" placeholder="选择从机地址" style="width: 100%">
          <el-option
            v-for="slave in slaveIdList"
            :key="slave"
            :label="`从机 ${slave}`"
            :value="slave"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="功能码" prop="func_code">
        <el-select v-model="formData.func_code" placeholder="选择功能码" style="width: 100%">
          <el-option label="01 - 读线圈" :value="1" />
          <el-option label="02 - 读离散输入" :value="2" />
          <el-option label="03 - 读保持寄存器" :value="3" />
          <el-option label="04 - 读输入寄存器" :value="4" />
          <el-option label="05 - 写单个线圈" :value="5" />
          <el-option label="06 - 写单个寄存器" :value="6" />
        </el-select>
      </el-form-item>

      <el-form-item label="解析码" prop="decode_code">
        <el-select v-model="formData.decode_code" placeholder="选择解析码" style="width: 100%">
          <el-option-group label="8位字符">
            <el-option label="0x10 - Byte 无符号" value="0x10" />
            <el-option label="0x11 - Byte 有符号" value="0x11" />
          </el-option-group>
          <el-option-group label="16位整数">
            <el-option label="0x20 - Short AB (大端)" value="0x20" />
            <el-option label="0x21 - Short AB 有符号" value="0x21" />
            <el-option label="0x22 - Short BA (字节交换)" value="0x22" />
            <el-option label="0xB0 - Short BA 无符号" value="0xB0" />
            <el-option label="0xB1 - Short BA 有符号" value="0xB1" />
            <el-option label="0xC0 - Short CD (小端)" value="0xC0" />
            <el-option label="0xC1 - Short CD 有符号" value="0xC1" />
          </el-option-group>
          <el-option-group label="32位整数">
            <el-option label="0x40 - Long AB CD (大端)" value="0x40" />
            <el-option label="0x41 - Long AB CD 有符号" value="0x41" />
            <el-option label="0x43 - Long CD AB (字交换)" value="0x43" />
            <el-option label="0x44 - Long CD AB 有符号" value="0x44" />
            <el-option label="0xD0 - Long DC BA (小端)" value="0xD0" />
            <el-option label="0xD1 - Long DC BA 有符号" value="0xD1" />
            <el-option label="0xD4 - Long BA DC (小端字交换)" value="0xD4" />
            <el-option label="0xD5 - Long BA DC 有符号" value="0xD5" />
          </el-option-group>
          <el-option-group label="32位浮点">
            <el-option label="0x42 - Float AB CD (大端)" value="0x42" />
            <el-option label="0x45 - Float CD AB (字交换)" value="0x45" />
            <el-option label="0xD2 - Float DC BA (小端)" value="0xD2" />
            <el-option label="0xD3 - Float BA DC (小端字交换)" value="0xD3" />
          </el-option-group>
          <el-option-group label="64位类型">
            <el-option label="0x60 - Int64 AB CD EF GH (大端)" value="0x60" />
            <el-option label="0x61 - Int64 有符号" value="0x61" />
            <el-option label="0x62 - Double AB CD EF GH" value="0x62" />
            <el-option label="0xE0 - Int64 HG FE DC BA (小端)" value="0xE0" />
            <el-option label="0xE1 - Int64 小端有符号" value="0xE1" />
            <el-option label="0xE2 - Double 小端" value="0xE2" />
          </el-option-group>
        </el-select>
      </el-form-item>

      <!-- 系数配置，仅遥测和遥调显示 -->
      <template v-if="[0, 3].includes(formData.frame_type)">
        <el-form-item label="乘法系数" prop="mul_coe">
          <el-input-number v-model="formData.mul_coe" :precision="6" :step="0.1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="加法系数" prop="add_coe">
          <el-input-number v-model="formData.add_coe" :precision="6" :step="1" style="width: 100%" />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleSubmit">
        {{ isBatch ? `批量添加 ${batchCount} 个` : '确定' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue';
import type { FormInstance, FormRules } from 'element-plus';
import { ElMessage } from 'element-plus';
import { addPoint, type PointCreateData } from '@/api/deviceApi';

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
  slaveIdList: number[];
  currentSlaveId?: number;
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
const isBatch = ref(false);
const batchCount = ref(10);

// 根据测点类型动态计算编码和名称前缀
const typeNameMap: Record<number, { code: string; name: string }> = {
  0: { code: 'YC_', name: '遥测' },
  1: { code: 'YX_', name: '遥信' },
  2: { code: 'YK_', name: '遥控' },
  3: { code: 'YT_', name: '遥调' },
};

const codePrefix = ref('YC_');
const namePrefix = ref('遥测');

const formData = reactive<PointCreateData>({
  frame_type: 0,
  code: '',
  name: '',
  rtu_addr: 1,
  reg_addr: '0',
  func_code: 3,
  decode_code: '0x41',
  mul_coe: 1.0,
  add_coe: 0.0,
});

// 监听测点类型变化，自动更新前缀
watch(() => formData.frame_type, (newType) => {
  const prefixes = typeNameMap[newType] || { code: 'POINT_', name: '测点' };
  codePrefix.value = prefixes.code;
  namePrefix.value = prefixes.name;
});

// 根据解析码计算寄存器跨度
const getRegisterSpan = (decodeCode: string): number => {
  // 64位解析码占4个寄存器
  if (['0x60', '0x61', '0x62', '0xE0', '0xE1', '0xE2'].includes(decodeCode)) {
    return 4;
  }
  // 32位解析码占2个寄存器
  if (['0x40', '0x41', '0x42', '0x43', '0x44', '0x45', '0xD0', '0xD1', '0xD2', '0xD3', '0xD4', '0xD5'].includes(decodeCode)) {
    return 2;
  }
  // 8位和16位占1个寄存器
  return 1;
};

const rules = computed<FormRules>(() => ({
  frame_type: [{ required: true, message: '请选择测点类型', trigger: 'change' }],
  code: isBatch.value ? [] : [{ required: true, message: '请输入测点编码', trigger: 'blur' }],
  name: isBatch.value ? [] : [{ required: true, message: '请输入测点名称', trigger: 'blur' }],
  rtu_addr: [{ required: true, message: '请选择从机地址', trigger: 'change' }],
  reg_addr: [{ required: true, message: '请输入寄存器地址', trigger: 'blur' }],
}));

watch(() => props.modelValue, (val) => {
  if (val && props.currentSlaveId) {
    formData.rtu_addr = props.currentSlaveId;
  }
});

const handleClose = () => {
  visible.value = false;
  formRef.value?.resetFields();
  isBatch.value = false;
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    loading.value = true;
    
    if (isBatch.value) {
      // 批量添加模式
      const startAddr = formData.reg_addr.startsWith('0x') 
        ? parseInt(formData.reg_addr, 16) 
        : parseInt(formData.reg_addr);
      const span = getRegisterSpan(formData.decode_code);
      let successCount = 0;
      
      for (let i = 0; i < batchCount.value; i++) {
        const pointData: PointCreateData = {
          ...formData,
          code: `${codePrefix.value}${String(i + 1).padStart(3, '0')}`,
          name: `${namePrefix.value}${i + 1}`,
          reg_addr: String(startAddr + i * span),
        };
        const success = await addPoint(props.deviceName, pointData);
        if (success) successCount++;
      }
      
      if (successCount === batchCount.value) {
        ElMessage.success(`成功添加 ${successCount} 个测点`);
      } else {
        ElMessage.warning(`成功添加 ${successCount}/${batchCount.value} 个测点`);
      }
      emit('success');
      handleClose();
    } else {
      // 单个添加模式
      const success = await addPoint(props.deviceName, formData);
      if (success) {
        ElMessage.success('添加测点成功');
        emit('success');
        handleClose();
      } else {
        ElMessage.error('添加测点失败');
      }
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
