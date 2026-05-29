<template>
  <el-dialog
    :title="$t('editPoint.title')"
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
      <el-form-item :label="$t('editPoint.pointName')" label-position="right">
        <el-input v-model="editConfig.pointName" disabled></el-input>
      </el-form-item>
      <el-form-item :label="$t('editPoint.pointCode')" label-position="right">
        <el-input v-model="editConfig.pointCode" disabled></el-input>
      </el-form-item>
      <el-form-item :label="$t('editPoint.mulCoe')" label-position="right">
        <el-input v-model="editConfig.multiplicationFactor" disabled></el-input>
      </el-form-item>
      <el-form-item :label="$t('editPoint.addCoe')" label-position="right">
        <el-input v-model="editConfig.additionFactor" disabled></el-input>
      </el-form-item>
      <el-form-item :label="$t('editPoint.registerValue')" label-position="right">
        <el-input v-model="registerValue" disabled></el-input>
      </el-form-item>
      <el-form-item :label="$t('editPoint.realValue')" label-position="right">
        <el-input v-model="editConfig.realValue"></el-input>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-row class="custom-row">
        <el-form-item class="custom-form-item">
          <el-button type="primary" @click="editRegisterValue">{{ $t('common.confirm') }}</el-button>
        </el-form-item>
        <el-form-item class="custom-form-item">
          <el-button @click="cancel">{{ $t('common.cancel') }}</el-button>
        </el-form-item>
      </el-row>
    </template>
  </el-dialog>
</template>

<script setup name="EditPoint">
import { computed, ref } from "vue";
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { editPointData } from "@/api/deviceApi";
import { useRoute } from "vue-router";
const route = useRoute();
const deviceName = computed(() => route.name);
const { t } = useI18n();

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

const editRegisterValue = async () => {
  props.setEditDialogVisible(false);
  try {
    const isSuccess = await editPointData(
      deviceName.value,
      props.editConfig.pointCode,
      registerValue.value
    );
    if (isSuccess) {
      emit(
        "editSuccess",
        props.editConfig.pointCode,
        props.editConfig.realValue,
        registerValue.value
      );
      ElMessage.success(t('register.editSuccess'));
    }
  } catch (error) {
    console.error('Edit register failed:', error);
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
