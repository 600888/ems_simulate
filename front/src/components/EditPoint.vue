<template>
  <el-dialog
    title="编辑测点值"
    width="350"
    v-model="visible"
    :show-close="false"
    :modal="true"
    :close-on-click-modal="false"
  >
    <el-form
      label-width="auto"
      :model="editConfig"
      @submit.native.prevent="editRegisterValue"
    >
      <el-form-item label="测点名称:" label-position="right">
        <el-input v-model="editConfig.pointName" disabled></el-input>
      </el-form-item>
      <el-form-item label="测点编码:" label-position="right">
        <el-input v-model="editConfig.pointCode" disabled></el-input>
      </el-form-item>
      <el-form-item label="乘法系数:" label-position="right">
        <el-input v-model="editConfig.multiplicationFactor" disabled></el-input>
      </el-form-item>
      <el-form-item label="加法系数:" label-position="right">
        <el-input v-model="editConfig.additionFactor" disabled></el-input>
      </el-form-item>
      <el-form-item label="寄存器值:" label-position="right">
        <el-input v-model="registerValue" disabled></el-input>
      </el-form-item>
      <el-form-item label="真实值:" label-position="right">
        <el-input v-model="editConfig.realValue"></el-input>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-row class="custom-row">
        <el-form-item class="custom-form-item">
          <el-button type="primary" @click="editRegisterValue">确定</el-button>
        </el-form-item>
        <el-form-item class="custom-form-item">
          <el-button @click="cancel">取消</el-button>
        </el-form-item>
      </el-row>
    </template>
  </el-dialog>
</template>

<script setup name="EditPoint">
import { computed, ref } from "vue";
import { editPointData } from "@/api/deviceApi";
import { useRoute } from "vue-router";
const route = useRoute();
const deviceName = computed(() => route.name);

let props = defineProps({
  editDialogVisible: {
    type: Boolean,
  },
  editConfig: {
    type: Object,
  },
  registerValue: {
    type: Number,
  },
  setEditDialogVisible: {
    type: Function,
  },
});
const visible = computed(() => props.editDialogVisible);
const registerValue = computed(() => props.registerValue);
const emit = defineEmits(["editSuccess"]);

const editRegisterValue = () => {
  props.setEditDialogVisible(false);
  const isSuccess = editPointData(
    deviceName.value,
    props.editConfig.pointCode,
    registerValue.value
  );
  if (!isSuccess) {
    alert("修改失败!");
  } else {
    emit(
      "editSuccess",
      props.editConfig.pointCode,
      props.editConfig.realValue,
      registerValue.value
    );
  }
};

const cancel = () => {
  props.setEditDialogVisible(false);
};
</script>

<style scoped>
.config-container {
  width: 400px;
  padding: 20px;
  text-align: left;

  /* border: 1px solid #ccc;
        border-radius: 5px;
        box-shadow: 0 0 10px rgba(0, 0, 0, 0.1); */
}

.el-form-item {
  margin-bottom: 15px;
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

/* 如果你不想给第一个和最后一个元素添加边距，可以使用伪类选择器 */
.custom-row .custom-form-item:first-child {
  margin-left: 0;
}

.custom-row .custom-form-item:last-child {
  margin-right: 0;
}
</style>
