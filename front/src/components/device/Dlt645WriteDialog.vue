<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('slave.dlt645ServerCmd.write_value')"
    width="440px"
    destroy-on-close
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="loading" class="dlt645-write-loading">
      {{ t("common.loading") }}
    </div>
    <el-form v-else :model="form" label-width="90px">
      <!-- 测点编码 -->
      <el-form-item :label="$t('table.pointCode')" class="center-input">
        <el-input :model-value="di" readonly />
      </el-form-item>
      <!-- 测点名称 -->
      <el-form-item :label="$t('table.pointName')" class="center-input">
        <el-input :model-value="diInfo?.name ?? ''" readonly />
      </el-form-item>
      <!-- 数据格式 -->
      <el-form-item :label="$t('slave.dlt645DataFormat')" class="center-input">
        <el-input
          :model-value="formatText"
          readonly
          :placeholder="formatText || '--'"
        />
      </el-form-item>

      <!-- 普通数据项：单个写入值 -->
      <el-form-item
        v-if="!isList"
        :label="$t('slave.dlt645WriteValue')"
        class="center-input"
      >
        <el-input
          v-model="form.value"
          :placeholder="$t('slave.dlt645WriteValuePlaceholder')"
        />
      </el-form-item>

      <!-- 列表数据项：每个子项一个输入框 -->
      <el-form-item
        v-for="(item, index) in listItems"
        :key="index"
        :label="t('slave.dlt645WriteItemN', { n: index + 1 })"
        class="center-input"
      >
        <el-input v-model="form.values[index]" :placeholder="item || ''" />
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="close">{{ $t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
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
import { sendDlt645Command, getDlt645DiInfo } from "@/api/deviceApi";
import { showError } from "@/api/http";

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
  /** 数据标识，如 "0x00000000" */
  di: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "success"): void;
}>();

const loading = ref(false);
const submitting = ref(false);
const diInfo = ref<any>(null);

const form = reactive<{ value: string; values: string[] }>({
  value: "",
  values: [],
});

const isList = computed(() => !!diInfo.value?.is_list);

/** 列表子项格式（仅列表项） */
const listItems = computed<string[]>(() =>
  isList.value ? (diInfo.value?.list_formats ?? []) : [],
);

/** 数据格式展示文本：普通项显示格式；列表项显示"列表（共 n 项）" */
const formatText = computed(() => {
  if (!diInfo.value) return "";
  if (isList.value) {
    return t("slave.dlt645ListFormat", { n: listItems.value.length });
  }
  return diInfo.value.data_format ?? "";
});

const close = () => emit("update:modelValue", false);

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) return;
    loading.value = true;
    diInfo.value = null;
    form.value = "";
    form.values = [];
    try {
      const info = await getDlt645DiInfo(props.deviceName, props.di);
      diInfo.value = info;
      if (info?.is_list) {
        form.values = (info.list_formats ?? []).map(() => "");
      }
    } catch (e) {
      showError(e, t("slave.dlt645CmdFailed"));
    } finally {
      loading.value = false;
    }
  },
);

const handleSubmit = async () => {
  submitting.value = true;
  try {
    const value = isList.value ? form.values.join(", ") : form.value.trim();
    if (!value) {
      ElMessage.warning(t("slave.dlt645WriteValueRequired"));
      return;
    }
    await sendDlt645Command(props.deviceName, "write_value", {
      di: props.di,
      value,
    });
    ElMessage.success(
      t("slave.dlt645WriteValueSuccess", { code: props.di, value }),
    );
    emit("success");
    close();
  } catch (e) {
    showError(e, t("slave.dlt645CmdFailed"));
  } finally {
    submitting.value = false;
  }
};
</script>

<style scoped>
.center-input :deep(.el-input__inner) {
  text-align: center;
}
.dlt645-write-loading {
  padding: 32px 0;
  text-align: center;
  color: var(--text-secondary, #94a3b8);
}
</style>
