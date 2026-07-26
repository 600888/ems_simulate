<template>
  <div class="register">
    <div class="simple-title">
      <span>{{ $t("register.limitSettings") }}</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="pointLimit" @submit.native.prevent="">
      <el-form-item
        :label="$t('register.maxValueLimit')"
        label-position="right"
        class="form-item"
      >
        <el-input v-model.number="pointLimit.maxValueLimit"></el-input>
      </el-form-item>
      <el-form-item
        :label="$t('register.minValueLimit')"
        label-position="right"
        class="form-item"
      >
        <el-input v-model.number="pointLimit.minValueLimit"></el-input>
      </el-form-item>
    </el-form>
    <el-row class="custom-row">
      <el-form-item class="custom-form-item">
        <el-button type="primary" @click="editPointLimitValue">{{
          $t("register.set")
        }}</el-button>
      </el-form-item>
      <el-form-item class="custom-form-item">
        <el-button @click="reset">{{ $t("common.reset") }}</el-button>
      </el-form-item>
    </el-row>
  </div>
</template>

<script setup name="SingleRegister" lang="ts">
import { onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { editPointLimit, getPointLimit } from "@/api/pointApi";
import { ElMessage } from "element-plus";
import "element-plus/dist/index.css";
import type { PointLimit } from "@/types/point";

const { t } = useI18n();

const props = defineProps({
  deviceName: { type: String, required: true },
  pointCode: { type: String, required: true },
  active: { type: Boolean, default: true },
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
      message: t("register.minLtMax"),
      type: "error",
    });
    return;
  }

  try {
    const isSuccess = await editPointLimit(
      props.deviceName,
      props.pointCode,
      pointLimit.value.minValueLimit,
      pointLimit.value.maxValueLimit,
    );
    if (isSuccess) {
      ElMessage({
        message: t("register.editSuccess"),
        type: "success",
      });
    }
  } catch (error) {
    console.error("Edit point limit failed:", error);
  }
};

const loadLimits = async () => {
  const limit = await getPointLimit(props.deviceName, props.pointCode);
  pointLimit.value.maxValueLimit = limit.maxValueLimit;
  pointLimit.value.minValueLimit = limit.minValueLimit;
};

watch(
  () => props.active,
  (newVal) => {
    if (newVal) {
      loadLimits();
    }
  },
  { immediate: true },
);

// 监听测点或设备变化，重新加载数据
watch([() => props.deviceName, () => props.pointCode], () => {
  if (props.active) {
    loadLimits();
  }
});
</script>

<style lang="scss" scoped>
.register {
  margin: 0;
  padding: 16px;
  width: 340px;
  font-family: Arial, sans-serif;
  background-color: var(--panel-bg);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
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
