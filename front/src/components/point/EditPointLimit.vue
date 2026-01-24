<template>
  <div class="register">
    <div class="simple-title">
      <span>上下限值设置</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="pointLimit" @submit.native.prevent="">
      <el-form-item label="测点上限值(真实值):" label-position="right" class="form-item">
        <el-input v-model.number="pointLimit.maxValueLimit"></el-input>
      </el-form-item>
      <el-form-item label="测点下限值(真实值):" label-position="right" class="form-item">
        <el-input v-model.number="pointLimit.minValueLimit"></el-input>
      </el-form-item>
    </el-form>
    <el-row class="custom-row">
      <el-form-item class="custom-form-item">
        <el-button type="primary" @click="editPointLimitValue">设置</el-button>
      </el-form-item>
      <el-form-item class="custom-form-item">
        <el-button @click="reset">重置</el-button>
      </el-form-item>
    </el-row>
  </div>
</template>

<script setup name="SingleRegister" lang="ts">
import { onMounted, ref } from "vue";
import { editPointLimit, getPointLimit } from "@/api/deviceApi";
import { ElMessage } from "element-plus";
import "element-plus/dist/index.css";
import type { PointLimit } from "@/types/point";

const props = defineProps({
  deviceName: { type: String, required: true },
  pointCode: { type: String, required: true },
});

const pointLimit = ref<PointLimit>({
  minValueLimit: 0,
  maxValueLimit: 0,
});

const reset = () => {
  pointLimit.value = {
    minValueLimit: 0,
    maxValueLimit: 0,
  };
};
const editPointLimitValue = async () => {
  if (pointLimit.value.minValueLimit > pointLimit.value.maxValueLimit) {
    ElMessage({
      message: "最小值不能大于最大值!",
      type: "error",
    });
    return;
  }

  const isSuccess = await editPointLimit(
    props.deviceName,
    props.pointCode,
    pointLimit.value.minValueLimit,
    pointLimit.value.maxValueLimit
  );
  if (!isSuccess) {
    ElMessage({
      message: "修改失败!",
      type: "error",
    });
  } else {
    ElMessage({
      message: "修改成功!",
      type: "success",
    });
  }
};

onMounted(async () => {
  const limit = await getPointLimit(props.deviceName, props.pointCode);
  pointLimit.value.maxValueLimit = limit.maxValueLimit;
  pointLimit.value.minValueLimit = limit.minValueLimit;
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
