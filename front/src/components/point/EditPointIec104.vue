<template>
  <div class="edit-iec104" v-if="isIec104">
    <div class="simple-title">
      <span>{{ $t("device.iec104Properties") }}</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="iec104Form" class="iec104-form">
      <el-row :gutter="20">
        <el-col :span="24">
          <el-form-item :label="$t('point.iec104Type')" class="form-item">
            <el-select
              v-model="iec104Form.iec_type_id"
              :placeholder="$t('point.selectAsduType')"
              style="width: 100%"
              clearable
            >
              <el-option
                v-for="item in availableIec104Types"
                :key="item.type_id"
                :label="
                  locale === 'en-US'
                    ? item.type_id
                    : `${t(item.label)} (${item.type_id})`
                "
                :value="item.type_id"
              />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20" v-if="supportsQualityFlag(iec104Form.frame_type)">
        <el-col :span="24">
          <el-form-item
            :label="$t('device.iec104QualityDescriptor')"
            class="form-item"
          >
            <div class="quality-flags">
              <el-checkbox
                v-model="qualityFlags.ov"
                :disabled="!isIec104Server || !canOverflow"
                :label="$t('qualityLabels.overflow')"
              />
              <el-checkbox
                v-model="qualityFlags.bl"
                :disabled="!isIec104Server"
                :label="$t('qualityLabels.blocked')"
              />
              <el-checkbox
                v-model="qualityFlags.sb"
                :disabled="!isIec104Server"
                :label="$t('qualityLabels.substituted')"
              />
              <el-checkbox
                v-model="qualityFlags.nt"
                :disabled="!isIec104Server"
                :label="$t('qualityLabels.notTopical')"
              />
              <el-checkbox
                v-model="qualityFlags.iv"
                :disabled="!isIec104Server"
                :label="$t('qualityLabels.invalid')"
              />
              <span v-if="!isIec104Server" class="readonly-hint">{{
                $t("device.iec104ClientReadonly")
              }}</span>
            </div>
          </el-form-item>
        </el-col>
      </el-row>
      <div class="button-group">
        <el-button type="primary" @click="saveIec104Metadata">{{
          $t("device.iec104Save")
        }}</el-button>
        <el-button @click="loadIec104Info">{{
          $t("device.iec104Refresh")
        }}</el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { getPointInfo, editIec104Metadata } from "@/api/pointApi";
import {
  IEC104_TYPES_BY_FRAME_TYPE,
  decodeIec104Quality,
  encodeIec104Quality,
  supportsQuality as supportsQualityFlag,
  supportsOverflow,
} from "@/types/point";

const { t, locale } = useI18n();

interface Props {
  deviceName: string;
  pointCode: string;
  active?: boolean;
  protocolType?: string;
}

const props = withDefaults(defineProps<Props>(), {
  active: true,
});
const emit = defineEmits(["update-success"]);

const isIec104 = computed(() => {
  const pt = props.protocolType || "";
  return pt === "Iec104Client" || pt === "Iec104Server";
});

const isIec104Server = computed(() => {
  return props.protocolType === "Iec104Server";
});

const iec104Form = reactive({
  frame_type: 0,
  iec_type_id: null as string | null,
  iec_quality: 0,
});

const qualityFlags = reactive({
  ov: false,
  bl: false,
  sb: false,
  nt: false,
  iv: false,
});

const canOverflow = computed(() => supportsOverflow(iec104Form.frame_type));

const availableIec104Types = computed(() => {
  return IEC104_TYPES_BY_FRAME_TYPE[iec104Form.frame_type] || [];
});

const loadIec104Info = async () => {
  try {
    const info = await getPointInfo(props.deviceName, props.pointCode);
    if (info) {
      iec104Form.frame_type = info.frame_type ?? 0;
      iec104Form.iec_type_id = info.iec_type_id ?? null;
      iec104Form.iec_quality = info.iec_quality ?? 0;
      const qd = decodeIec104Quality(
        iec104Form.iec_quality,
        iec104Form.frame_type,
      );
      qualityFlags.ov = qd.ov;
      qualityFlags.bl = qd.bl;
      qualityFlags.sb = qd.sb;
      qualityFlags.nt = qd.nt;
      qualityFlags.iv = qd.iv;
    }
  } catch (error) {
    console.error("加载IEC104信息失败:", error);
  }
};

const saveIec104Metadata = async () => {
  try {
    // 客户端不允许修改品质描述符，使用原始值
    const iecQuality = isIec104Server.value
      ? encodeIec104Quality(qualityFlags, iec104Form.frame_type)
      : iec104Form.iec_quality;
    const result = await editIec104Metadata(props.deviceName, props.pointCode, {
      iec_type_id: iec104Form.iec_type_id,
      iec_quality: iecQuality,
    });
    if (result) {
      ElMessage.success(t("device.iec104Updated"));
      emit("update-success");
    }
  } catch (error: any) {
    console.error("更新IEC104属性失败:", error);
  }
};

let refreshTimer: ReturnType<typeof setInterval> | null = null;

const startRefresh = () => {
  stopRefresh();
  // 服务端模式：品质可被用户编辑，不自动刷新以免覆盖
  // 客户端模式：品质只读，每秒刷新以显示远端最新值
  if (!isIec104Server.value) {
    refreshTimer = setInterval(() => {
      loadIec104Quality();
    }, 1000);
  }
};

const stopRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
};

// 仅刷新品质描述符（不覆盖用户正在编辑的ASDU类型）
const loadIec104Quality = async () => {
  try {
    const info = await getPointInfo(props.deviceName, props.pointCode);
    if (info) {
      iec104Form.frame_type = info.frame_type ?? 0;
      iec104Form.iec_quality = info.iec_quality ?? 0;
      const qd = decodeIec104Quality(
        iec104Form.iec_quality,
        iec104Form.frame_type,
      );
      qualityFlags.ov = qd.ov;
      qualityFlags.bl = qd.bl;
      qualityFlags.sb = qd.sb;
      qualityFlags.nt = qd.nt;
      qualityFlags.iv = qd.iv;
    }
  } catch (error) {
    // 静默失败，避免每秒弹错误
  }
};

onBeforeUnmount(() => {
  stopRefresh();
});

watch(
  () => props.active,
  (newVal) => {
    if (newVal && isIec104.value) {
      loadIec104Info();
      startRefresh();
    } else {
      stopRefresh();
    }
  },
  { immediate: true },
);

watch([() => props.deviceName, () => props.pointCode], () => {
  if (props.deviceName && props.pointCode && props.active && isIec104.value) {
    loadIec104Info();
    stopRefresh();
    startRefresh();
  }
});
</script>

<style scoped>
.edit-iec104 {
  margin: 0;
  padding: 16px;
  width: 420px;
  font-family: Arial, sans-serif;
  background-color: var(--panel-bg);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.simple-title {
  margin-bottom: 15px;
}

.simple-title span {
  font-size: 16px;
  color: #e6a23c;
  font-weight: 500;
}

.simple-title .el-divider {
  margin: 12px 0;
  background-color: #e6a23c;
}

.form-item {
  width: 100%;
}

.iec104-form {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.button-group {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: auto;
  padding-top: 10px;
}

.quality-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.readonly-hint {
  font-size: 12px;
  color: #909399;
}
</style>
