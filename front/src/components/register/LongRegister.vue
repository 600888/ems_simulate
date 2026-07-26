<template>
  <div class="register">
    <div class="simple-title">
      <span>{{ $t("register.registerParse") }}</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="longRegister" @submit.native.prevent="">
      <el-form-item label="Long AB CD:" class="form-item">
        <el-input v-model.number="longRegister.longABCD" disabled>
          <template #append>
            <span class="hex-value">{{
              getLongHex(longRegister.longABCD)
            }}</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Long CD AB:" class="form-item">
        <el-input v-model.number="longRegister.longCDAB" disabled>
          <template #append>
            <span class="hex-value">{{
              getLongHex(longRegister.longCDAB)
            }}</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Long BA DC:" class="form-item">
        <el-input v-model="longRegister.longBADC" disabled>
          <template #append>
            <span class="hex-value">{{
              getLongHex(longRegister.longBADC)
            }}</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Long DC BA:" class="form-item">
        <el-input v-model="longRegister.longDCBA" disabled>
          <template #append>
            <span class="hex-value">{{
              getLongHex(longRegister.longDCBA)
            }}</span>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item label="Real:" class="form-item">
        <el-input v-model="longRegister.real" v-decimal="2"></el-input>
      </el-form-item>
    </el-form>
    <el-row class="custom-row">
      <el-form-item class="custom-form-item">
        <el-button type="primary" @click="editRegisterValue">{{
          $t("register.set")
        }}</el-button>
      </el-form-item>
      <el-form-item class="custom-form-item">
        <el-button @click="reset">{{ $t("common.reset") }}</el-button>
      </el-form-item>
    </el-row>
  </div>
</template>

<script setup name="LongRegister" lang="ts">
import { onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { type LongPointRegister } from "@/types/register";
import { editPointData } from "@/api/pointApi";
import { ElMessage } from "element-plus";
import "element-plus/dist/index.css";

const { t } = useI18n();

const getLongHex = (value: number) => {
  const buffer = new ArrayBuffer(4);
  const view = new DataView(buffer);
  view.setUint32(0, value, false); // 大端序写入
  const hex = view
    .getUint32(0, false) // 保持大端序读取
    .toString(16)
    .toUpperCase()
    .padStart(8, "0");
  return "0x" + hex;
};

const props = defineProps({
  rowIndex: { type: Number, required: true },
  deviceName: { type: String, required: true },
  pointCode: { type: String, required: true },
  realValue: { type: Number, required: true },
  mulCoe: { type: Number, default: 1.0 },
  addCoe: { type: Number, default: 0.0 },
  slaveId: { type: Number, default: undefined },
});

const longRegister = ref<LongPointRegister>({
  longABCD: 0,
  longCDAB: 0,
  longBADC: 0,
  longDCBA: 0,
  real: 0,
  mulCoe: 1,
  addCoe: 0,
});

const reset = () => {
  longRegister.value = {
    longABCD: 0,
    longCDAB: 0,
    longBADC: 0,
    longDCBA: 0,
    real: 0,
    mulCoe: 1,
    addCoe: 0,
  };
};

const emit = defineEmits(["editSuccess"]);
const editRegisterValue = async () => {
  try {
    const isSuccess = await editPointData(
      props.deviceName,
      props.pointCode,
      parseFloat(longRegister.value.real.toString()),
      props.slaveId,
    );
    if (isSuccess) {
      emit(
        "editSuccess",
        props.rowIndex,
        parseFloat(longRegister.value.real.toString()),
        getLongHex(longRegister.value.longABCD),
      );
      ElMessage({
        message: t("register.editSuccess"),
        type: "success",
      });
    }
  } catch (error) {
    console.error("Edit long register failed:", error);
  }
};

function updateFromReal(value: number) {
  // 计算原始寄存器值（应用乘法和加法系数）
  const registerValue = parseInt(
    (
      (value - longRegister.value.addCoe) /
      longRegister.value.mulCoe
    ).toString(),
  );

  // 检查32位数值范围（兼容有符号和无符号）
  if (registerValue < -2147483648 || registerValue > 4294967295) {
    return;
  }

  // 转换为32位无符号表示
  const unsigned32 = registerValue | 0;

  // 生成四种排列组合（模拟不同字节序）
  longRegister.value = {
    longABCD: unsigned32,
    longCDAB:
      ((unsigned32 & 0xffff0000) >>> 16) | ((unsigned32 & 0x0000ffff) << 16),
    longBADC:
      ((unsigned32 & 0xff00ff00) >>> 8) | ((unsigned32 & 0x00ff00ff) << 8),
    longDCBA:
      ((unsigned32 & 0xff000000) >>> 24) |
      ((unsigned32 & 0x00ff0000) >>> 8) |
      ((unsigned32 & 0x0000ff00) << 8) |
      ((unsigned32 & 0x000000ff) << 24),
    real: value,
    mulCoe: props.mulCoe,
    addCoe: props.addCoe,
  };
}

watch(
  () => props.realValue,
  (newVal, oldVal) => {
    updateFromReal(newVal);
  },
);

// 监听所有字段的变化
watch(
  () => longRegister.value.real,
  (newVal, oldVal) => {
    updateFromReal(newVal);
  },
);

onMounted(() => {
  longRegister.value.mulCoe = props.mulCoe;
  longRegister.value.addCoe = props.addCoe;
  updateFromReal(props.realValue);
});
</script>

<style lang="scss" scoped>
.register {
  margin: 0;
  padding: 16px;
  width: 420px;
  font-family: Arial, sans-serif;
  background-color: var(--panel-bg);
  border-radius: 8px;
  box-shadow: var(--box-shadow-base);
  border: 1px solid var(--border-color);
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
  width: 380px;

  /* 优化输入框后缀样式，使其更融合 */
  :deep(.el-input-group__append) {
    background-color: var(--bg-subtle);
    border-left: 1px solid var(--border-color);
    padding: 0 14px;
  }

  .hex-value {
    color: #409eff;
    font-size: 13px;
    font-weight: 600;
    font-family: "Consolas", "Monaco", monospace;
    letter-spacing: 0.5px;
  }
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
