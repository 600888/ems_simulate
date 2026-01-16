<template>
  <div class="register">
    <div class="simple-title">
      <span>寄存器解析</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="floatRegister" @submit.native.prevent="">
      <el-form-item label="Float AB CD:" class="form-item">
        <el-input v-model.number="floatRegister.floatABCD" disabled>
          <template #append>
            <span>({{ getFloatHex(floatRegister.floatABCD) }})</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Float CD AB:" class="form-item">
        <el-input v-model.number="floatRegister.floatCDAB" disabled>
          <template #append>
            <span>({{ getFloatHex(floatRegister.floatCDAB) }})</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Float BA DC:" class="form-item">
        <el-input v-model="floatRegister.floatBADC" disabled>
          <template #append>
            <span>({{ getFloatHex(floatRegister.floatBADC) }})</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Float DC BA:" class="form-item">
        <el-input v-model="floatRegister.floatDCBA" disabled>
          <template #append>
            <span>({{ getFloatHex(floatRegister.floatDCBA) }})</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Real:" class="form-item">
        <el-input v-model="floatRegister.real" v-decimal="2"></el-input>
      </el-form-item>
    </el-form>
    <el-row class="custom-row">
      <el-form-item class="custom-form-item">
        <el-button type="primary" @click="editRegisterValue">设置</el-button>
      </el-form-item>
      <el-form-item class="custom-form-item">
        <el-button @click="reset">重置</el-button>
      </el-form-item>
    </el-row>
  </div>
</template>

<script setup name="LongRegister" lang="ts">
import { onMounted, ref, watch } from "vue";
import {type FloatPointRegister } from "@/types/register";
import { editPointData } from "@/api/deviceApi";
import { ElMessage } from "element-plus";
import 'element-plus/dist/index.css'

const props = defineProps({
  rowIndex: { type: Number, required: true },
  deviceName: { type: String, required: true },
  pointCode: { type: String, required: true },
  realValue: { type: Number, required: true },
  mulCoe: { type: Number, default: 1.0 },
  addCoe: { type: Number, default: 0.0 }
});

const floatRegister = ref<FloatPointRegister>({
  floatABCD: 0,
  floatCDAB: 0,
  floatBADC: 0,
  floatDCBA: 0,
  real: 0,
  mulCoe: 1,
  addCoe: 0,
});

const reset = () => {
  floatRegister.value = {
    floatABCD: 0,
    floatCDAB: 0,
    floatBADC: 0,
    floatDCBA: 0,
    real: 0,
    mulCoe: 1,
    addCoe: 0,
  };
}

const emit = defineEmits(["editSuccess"]);
const editRegisterValue = async() => {
  const isSuccess = await editPointData(
    props.deviceName,
    props.pointCode,
    parseFloat(floatRegister.value.real.toString())
  );
  if (!isSuccess) {
    ElMessage({
      message: '修改失败!',
      type: 'error'
    })
  } else {
    emit("editSuccess",props.rowIndex, parseFloat(floatRegister.value.real.toString()), getFloatHex(floatRegister.value.floatABCD));
    ElMessage({
      message: '修改成功!',
      type: 'success'
    })
  }
}

// 浮点数转16进制（处理负数和小数）
const getFloatHex = (value:number) =>{
  const buffer = new ArrayBuffer(4);
  const view = new DataView(buffer);
  view.setFloat32(0, value, false); // 大端序写入
  const hex = view.getUint32(0, false) // 保持大端序读取
    .toString(16)
    .toUpperCase()
    .padStart(8, '0');
  return "0x" + hex;
}

function updateFromReal(value: number) {
  // 计算原始浮点数值
  const floatValue = (value - floatRegister.value.addCoe) / floatRegister.value.mulCoe;

  // 将浮点数转换为32位二进制表示（IEEE 754标准）
  const buffer = new ArrayBuffer(4);
  const view = new DataView(buffer);
  view.setFloat32(0, floatValue, false); // 大端序写入

  // 正确获取32位无符号整数表示（保持浮点结构）
  const unsigned32 = view.getUint32(0, false);

  // 生成四种字节序排列（仅操作二进制位，不改变浮点结构）
  floatRegister.value = {
    floatABCD: view.getFloat32(0, false),  // 原始大端序浮点值
    floatCDAB: new DataView(reorderBytes(buffer, 'CDAB')).getFloat32(0, false),
    floatBADC: new DataView(reorderBytes(buffer, 'BADC')).getFloat32(0, false),
    floatDCBA: new DataView(reorderBytes(buffer, 'DCBA')).getFloat32(0, false),
    real: value,
    mulCoe: props.mulCoe,
    addCoe: props.addCoe,
  };
}

// 字节序重排工具函数
function reorderBytes(buffer: ArrayBuffer, type: 'CDAB' | 'BADC' | 'DCBA') {
  const view = new DataView(buffer);
  const uint32 = view.getUint32(0, false);
  const newBuffer = new ArrayBuffer(4);
  const newView = new DataView(newBuffer);

  switch(type) {
    case 'CDAB':
      newView.setUint32(0,
        ((uint32 & 0xFFFF0000) >>> 16) |
        ((uint32 & 0x0000FFFF) << 16), false);
      break;
    case 'BADC':
      newView.setUint32(0,
        ((uint32 & 0xFF00FF00) >>> 8) |
        ((uint32 & 0x00FF00FF) << 8), false);
      break;
    case 'DCBA':
      newView.setUint32(0,
        ((uint32 & 0xFF000000) >>> 24) |
        ((uint32 & 0x00FF0000) >>> 8) |
        ((uint32 & 0x0000FF00) << 8) |
        ((uint32 & 0x000000FF) << 24), false);
  }
  return newBuffer;
}

watch(()=>props.realValue, (newVal, oldVal) => {
  updateFromReal(newVal);
})

// 监听所有字段的变化
watch(() => floatRegister.value.real, (newVal, oldVal) => {
  updateFromReal(newVal);
});

onMounted(() => {
  floatRegister.value.mulCoe = props.mulCoe;
  floatRegister.value.addCoe = props.addCoe;
  updateFromReal(props.realValue);
});
</script>

<style lang="scss" scoped>
.register {
  margin-top: 10px;
  margin-bottom: 20px;
  margin-left: 20px;
  padding: 20px;
  width: 500px;
  font-family: Arial, sans-serif;
  background-color: white;
  border-radius: 5px;
  box-shadow: 0 1px 3px rgba(0.2, 0.2, 0.2, 0.2);
}

.simple-title {
  margin-bottom: 15px;
}
.simple-title span {
  font-size: 16px;
  color: #409eff;
  font-weight: 500;
}
.simple-title .el-divider {
  margin: 12px 0;
  background-color: #409eff;
}

.form-item {
  width: 450px;
}

.custom-row {
  display: flex;
  justify-content: center;
  /* 居中对齐 */
  align-items: center;
  /* 垂直居中（如果需要的话） */
}

.custom-form-item {
  margin: 0 10px;
  /* 左右的间距，根据需要调整 */
}
</style>
