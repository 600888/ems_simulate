<template>
  <el-dialog
    v-model="visible"
    :title="$t('writeDialog.title')"
    width="560px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <el-form v-loading="preparing" :model="form" label-width="90px">
      <el-form-item :label="$t('writeDialog.attributeName')">
        <el-input v-model="form.attributeName" disabled />
      </el-form-item>
      <el-form-item :label="$t('writeDialog.currentValue')">
        <el-input :model-value="currentValueLabel" disabled />
      </el-form-item>
      <el-form-item
        v-if="target && target.point_code !== pointCode"
        :label="$t('writeDialog.targetAttribute')"
      >
        <el-input :model-value="target.address" disabled />
      </el-form-item>
      <el-form-item :label="$t('writeDialog.writeValue')">
        <Iec61850ValueEditor
          v-model="form.writeValue"
          :definition="target?.enum_definition"
          :disabled="preparing || Boolean(metadataError) || !target"
        />
      </el-form-item>
      <el-alert
        v-if="metadataError"
        :title="metadataError"
        type="error"
        :closable="false"
      />
      <el-alert
        v-else-if="target?.b_type === 'Enum' && !target.type_id"
        :title="$t('writeDialog.enumUnavailable')"
        type="info"
        :closable="false"
      />
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">{{
          $t("common.cancel")
        }}</el-button>
        <el-button
          type="primary"
          :loading="loading"
          :disabled="preparing || Boolean(metadataError) || !target"
          @click="handleSubmit"
        >
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
import { iec61850PrepareWrite, iec61850WritePoint } from "@/api/channelApi";
import type { IEC61850WriteTarget } from "@/api/channelApi";
import { formatEnumValue, isEnumSelection } from "@/utils/iec61850Enum";
import Iec61850ValueEditor from "./Iec61850ValueEditor.vue";

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
const preparing = ref(false);
const target = ref<IEC61850WriteTarget | null>(null);
const metadataError = ref("");
let requestSequence = 0;
const currentValueLabel = computed(() =>
  formatEnumValue(
    form.currentValue,
    target.value?.point_code === props.pointCode
      ? target.value.enum_definition
      : undefined,
    t("writeDialog.unknownEnum"),
  ),
);
const form = reactive({
  pointCode: "",
  attributeName: "",
  currentValue: "" as string | number,
  writeValue: "" as string | number,
});

watch(
  () => [props.modelValue, props.channelId, props.pointCode] as const,
  async ([isOpen]) => {
    const sequence = ++requestSequence;
    target.value = null;
    metadataError.value = "";
    preparing.value = false;
    if (isOpen) {
      form.pointCode = props.pointCode;
      form.attributeName = props.attributeName || props.pointCode;
      form.currentValue = props.currentValue;
      form.writeValue = "";
      preparing.value = true;
      try {
        const prepared = await iec61850PrepareWrite(
          props.channelId,
          props.pointCode,
        );
        if (sequence !== requestSequence) return;
        target.value = prepared;
        metadataError.value = prepared?.type_id
          ? prepared.enum_error || ""
          : "";
        if (!prepared) metadataError.value = t("writeDialog.prepareFailed");
      } catch (error) {
        if (sequence !== requestSequence) return;
        metadataError.value = t("writeDialog.prepareFailed");
        showError(error, metadataError.value);
      } finally {
        if (sequence === requestSequence) preparing.value = false;
      }
    }
  },
  { immediate: true },
);

const handleSubmit = async () => {
  if (preparing.value || metadataError.value || !target.value || loading.value)
    return;
  if (!form.pointCode) {
    ElMessage.warning(t("writeDialog.emptyCode"));
    return;
  }
  if (
    target.value.enum_definition &&
    !isEnumSelection(form.writeValue, target.value.enum_definition)
  ) {
    ElMessage.warning(t("writeDialog.selectEnum"));
    return;
  }
  if (form.writeValue === "") {
    ElMessage.warning(t("writeDialog.inputPlaceholder"));
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
      target.value.model_revision,
    );
    if (result) {
      ElMessage.success(t("writeDialog.writeSent"));
      visible.value = false;
      emit("success", result);
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
