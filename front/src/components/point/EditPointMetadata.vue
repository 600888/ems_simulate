<template>
  <div class="edit-metadata">
    <div class="simple-title">
      <span>{{ $t("editMetadata.title") }}</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="metadataForm">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item :label="$t('editMetadata.name')" class="form-item">
            <el-input v-model="metadataForm.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('editMetadata.code')" class="form-item">
            <el-input v-model="metadataForm.code" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item :label="$t('table.address')" class="form-item">
            <el-input v-model="metadataForm.reg_addr" />
          </el-form-item>
        </el-col>
        <el-col :span="12" v-if="!isIec104 && !isDnp3">
          <el-form-item
            :label="$t('editMetadata.decodeCode')"
            class="form-item"
          >
            <el-select
              v-model="metadataForm.decode_code"
              :placeholder="$t('editMetadata.selectDecodeCode')"
            >
              <el-option-group
                v-for="group in DECODE_GROUPS"
                :key="group.labelKey"
                :label="$t(group.labelKey)"
              >
                <el-option
                  v-for="code in group.codes"
                  :key="code"
                  :label="getDecodeOptionLabel(code, $t)"
                  :value="code"
                />
              </el-option-group>
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20">
        <el-col :span="12" v-if="!isIec104 && !isDnp3">
          <el-form-item :label="$t('table.funcCode')" class="form-item">
            <el-input v-model.number="metadataForm.func_code" type="number" />
          </el-form-item>
        </el-col>
        <el-col :span="12" v-if="isYxOrYk">
          <el-form-item :label="$t('editMetadata.bitOffset')" class="form-item">
            <el-input-number
              v-model="metadataForm.bit"
              :min="0"
              :max="31"
              :step="1"
              :placeholder="$t('editMetadata.bitPlaceholder')"
              style="width: 100%"
              controls-position="right"
              :value-on-clear="null"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20" v-if="isYcOrYt">
        <el-col :span="12">
          <el-form-item :label="$t('editMetadata.mulCoe')" class="form-item">
            <el-input v-model.number="metadataForm.mul_coe" type="number" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('editMetadata.addCoe')" class="form-item">
            <el-input v-model.number="metadataForm.add_coe" type="number" />
          </el-form-item>
        </el-col>
      </el-row>

      <div class="button-group">
        <el-button type="primary" @click="saveMetadata">{{
          $t("editMetadata.save")
        }}</el-button>
        <el-button @click="loadPointInfo">{{ $t("common.refresh") }}</el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { getPointInfo, editPointMetadata } from "@/api/pointApi";
import {
  DECODE_GROUPS,
  getDecodeOptionLabel,
  normalizeDecode,
} from "@/constants/decode";

interface Props {
  deviceName: string;
  pointCode: string;
  active?: boolean;
  protocolType?: string;
}

const { t } = useI18n();

const props = withDefaults(defineProps<Props>(), {
  active: true,
  protocolType: "",
});

// 判断是否为 IEC104 协议
const isIec104 = computed(() => {
  const pt = props.protocolType || "";
  return [
    "Iec104Client",
    "Iec104Server",
    "Iec101Client",
    "Iec101Server",
  ].includes(pt);
});
const isDnp3 = computed(() => {
  const pt = props.protocolType || "";
  return pt === "Dnp3Client" || pt === "Dnp3Server";
});
const emit = defineEmits(["update-success"]);

const metadataForm = reactive({
  name: "",
  code: "",
  reg_addr: "",
  func_code: 3,
  decode_code: "",
  mul_coe: 1.0,
  add_coe: 0.0,
  frame_type: 0,
  bit: null as number | null,
});

const isYcOrYt = computed(() => [0, 3].includes(metadataForm.frame_type));
const isYxOrYk = computed(() => [1, 2].includes(metadataForm.frame_type));

// 加载点信息
const loadPointInfo = async () => {
  try {
    const info = await getPointInfo(props.deviceName, props.pointCode);
    if (info) {
      metadataForm.name = info.name || "";
      metadataForm.code = info.code || "";
      metadataForm.reg_addr = info.reg_addr || "";
      metadataForm.func_code = info.func_code || 3;
      metadataForm.decode_code = info.decode_code
        ? normalizeDecode(info.decode_code)
        : "";
      metadataForm.mul_coe = info.mul_coe ?? 1.0;
      metadataForm.add_coe = info.add_coe ?? 0.0;
      metadataForm.frame_type = info.frame_type ?? 0;
      metadataForm.bit = info.bit ?? null;
    }
  } catch (error) {
    console.error("加载点信息失败:", error);
  }
};

// 保存元数据
const saveMetadata = async () => {
  try {
    const result = await editPointMetadata(
      props.deviceName,
      props.pointCode,
      metadataForm,
    );
    if (result) {
      ElMessage.success(t("editMetadata.saved"));
      emit("update-success", metadataForm.code); // 通知上层编码可能已变
    }
  } catch (error: any) {
    console.error("更新失败:", error);
  }
};

// 监听激活状态，激活时加载数据
watch(
  () => props.active,
  (newVal) => {
    if (newVal) {
      loadPointInfo();
    }
  },
  { immediate: true },
);

// 监听测点或设备变化，如果处于激活状态则重新加载数据
watch([() => props.deviceName, () => props.pointCode], (newVal) => {
  if (newVal[0] && newVal[1] && props.active) {
    loadPointInfo();
  }
});
</script>

<style scoped>
.edit-metadata {
  margin: 0;
  padding: 16px;
  width: 680px; /* Keep width */
  font-family: Arial, sans-serif;
  background-color: var(--panel-bg);
  border-radius: 8px; /* Match SingleRegister */
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); /* Match SingleRegister */
  border: 1px solid var(--border-color); /* Match SingleRegister */
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
  width: 100%; /* Rows will handle the width */
}

.button-group {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: 10px;
}
</style>
