<template>
  <div class="register">
    <div class="simple-title">
      <span>寄存器解析</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="pointRegister" @submit.native.prevent="">
      <el-form-item label="Signed:" label-position="right" class="form-item">
        <el-input v-model.number="pointRegister.signed" disabled></el-input>
      </el-form-item>
      <el-form-item label="Unsigned:" label-position="right" class="form-item">
        <el-input v-model.number="pointRegister.unsigned" disabled></el-input>
      </el-form-item>
      <el-form-item label="Hex:" label-position="right" class="form-item">
        <el-input v-model="pointRegister.hex" disabled></el-input>
      </el-form-item>
      <el-form-item label="Binary:" label-position="right" class="form-item">
        <el-input v-model="pointRegister.bin" disabled></el-input>
      </el-form-item>
      <el-form-item label="Real:" label-position="right" class="form-item">
        <el-input v-model="pointRegister.real" v-decimal="2"></el-input>
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

<script setup name="SingleRegister" lang="ts">
import { onMounted, ref, watch } from "vue";
import {type IntPointRegister } from "@/types/register";
import { editPointData } from "@/api/deviceApi";
import { ElMessage } from "element-plus";
import 'element-plus/dist/index.css'

const getIntHex = (value: number) => {
  // 参数校验（确保是16位整数）
  if (value < -32768 || value > 65535) {
    throw new Error("Value exceeds 16-bit integer range");
  }

  const buffer = new ArrayBuffer(2);
  const view = new DataView(buffer);

  // 处理有符号/无符号转换
  const uintValue = value < 0 ? 65536 + value : value;
  view.setUint16(0, uintValue, false); // 大端序写入

  // 修正补零长度（16位对应4字符十六进制）
  return "0x" + view.getUint16(0, false)
    .toString(16)
    .toUpperCase()
    .padStart(4, '0');
};

const props = defineProps({
  rowIndex: { type: Number, required: true },
  deviceName: { type: String, required: true },
  pointCode: { type: String, required: true },
  realValue: { type: Number, required: true },
  mulCoe: { type: Number, default: 1.0 },
  addCoe: { type: Number, default: 0.0 }
});

const pointRegister = ref<IntPointRegister>({
  signed: 0,
  unsigned: 0,
  hex: "",
  bin: "",
  real: 0,
  mulCoe: 1,
  addCoe: 0,
});

const reset = () => {
  pointRegister.value = {
    signed: 0,
    unsigned: 0,
    hex: "0000",
    bin: "0000000000000000",
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
    parseFloat(pointRegister.value.real.toString())
  );
  if (!isSuccess) {
    ElMessage({
      message: '修改失败!',
      type: 'error'
    })
  } else {
    emit("editSuccess",props.rowIndex, parseFloat(pointRegister.value.real.toString()), getIntHex(pointRegister.value.signed));
    ElMessage({
      message: '修改成功!',
      type: 'success'
    })
  }
}

function updateFromReal(value: number) {
  const registerValue = parseInt(((value - pointRegister.value.addCoe) / pointRegister.value.mulCoe).toString());

  // 检查16位有符号数范围
  if (registerValue < -32768 || registerValue > 65535) {
    return;
  }

  // 处理有符号数表示
  let signed = registerValue;
  if (registerValue > 32767) {
    signed = registerValue - 65535;
  }

  // 处理无符号数表示
  let unsigned = registerValue;
  if (registerValue < 0) {
    unsigned = 65536 + registerValue;
  }

  // 确保数值在有效范围内
  unsigned = Math.max(0, Math.min(65535, unsigned));
  signed = Math.max(-32768, Math.min(32767, signed));

  // 格式化输出
  pointRegister.value = {
    signed: signed,
    unsigned: unsigned,
    hex: unsigned.toString(16).toUpperCase().padStart(4, '0'),
    bin: unsigned.toString(2).padStart(16, '0'),
    real: value,
    mulCoe: pointRegister.value.mulCoe,
    addCoe: pointRegister.value.addCoe,
  };
}

watch(()=>props.realValue, (newVal, oldVal) => {
  updateFromReal(newVal);
})

// 监听所有字段的变化
watch(() => pointRegister.value.real, (newVal, oldVal) => {
  updateFromReal(newVal);
});

onMounted(() => {
  pointRegister.value.mulCoe = props.mulCoe;
  pointRegister.value.addCoe = props.addCoe;
  updateFromReal(props.realValue);
});
</script>

<style lang="scss" scoped>
.register {
  margin: 0;
  padding: 16px;
  width: 340px;
  font-family: Arial, sans-serif;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid #e4e7ed;
}

.simple-title {
  margin-bottom: 12px;
}
.simple-title span {
  font-size: 14px;
  color: #409eff;
  font-weight: 600;
}
.simple-title .el-divider {
  margin: 8px 0;
  background-color: #409eff;
}

.form-item {
  margin-bottom: 10px;
  width: 280px;
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
