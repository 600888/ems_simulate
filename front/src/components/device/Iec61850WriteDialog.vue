<template>
  <el-dialog
    v-model="visible"
    :title="$t('writeDialog.title')"
    width="400px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <el-form :model="form" label-width="80px">
      <el-form-item :label="$t('writeDialog.attributeName')">
        <el-input v-model="form.attributeName" disabled />
      </el-form-item>
      <el-form-item :label="$t('writeDialog.currentValue')">
        <el-input :model-value="String(form.currentValue)" disabled />
      </el-form-item>
      <el-form-item :label="$t('writeDialog.writeValue')">
        <el-input
          v-model="form.writeValue"
          :placeholder="$t('writeDialog.inputPlaceholder')"
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">{{
          $t("common.cancel")
        }}</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          {{ $t("writeDialog.confirmWrite") }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { showError } from "@/api/http";
import { iec61850WritePoint } from "@/api/channelApi";

const { t } = useI18n();

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  channelId: { type: Number, required: true },
  pointCode: { type: String, default: "" },
  attributeName: { type: String, default: "" },
  currentValue: { type: [Number, String], default: "" },
});

const emit = defineEmits(["update:modelValue", "success"]);

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const loading = ref(false);
const form = reactive({
  pointCode: "",
  attributeName: "",
  currentValue: "" as string | number,
  writeValue: "" as string | number,
});

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      form.pointCode = props.pointCode;
      form.attributeName = props.attributeName || props.pointCode;
      form.currentValue = props.currentValue;
      form.writeValue = "";
    }
  },
  { immediate: true },
);

const handleSubmit = async () => {
  if (!form.pointCode) {
    ElMessage.warning(t("writeDialog.emptyCode"));
    return;
  }
  loading.value = true;
  try {
    // 智能判断值类型: 纯数字转为数字, 否则保留字符串
    let val: string | number = form.writeValue;
    if (typeof val === "string" && val.trim() !== "" && !isNaN(Number(val))) {
      val = Number(val);
    }
    const result = await iec61850WritePoint(
      props.channelId,
      form.pointCode,
      val,
    );
    if (result) {
      ElMessage.success(t("writeDialog.writeSent"));
      visible.value = false;
      emit("success");
    }
  } catch (e: any) {
    showError(
      e,
      t("writeDialog.writeFailed", { msg: t("writeDialog.unknownError") }),
    );
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
