<template>
  <div v-if="isDnp3" class="edit-dnp3">
    <div class="simple-title">
      <span>{{ $t("device.dnp3Properties") }}</span>
      <el-divider />
    </div>

    <el-form :model="form" label-width="auto" class="dnp3-form">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item :label="$t('point.dnp3StaticVariation')">
            <el-select v-model="form.static_variation" style="width: 100%">
              <el-option
                v-for="variation in staticVariations"
                :key="variation"
                :label="`V${variation}`"
                :value="variation"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('point.dnp3EventVariation')">
            <el-select v-model="form.event_variation" style="width: 100%">
              <el-option
                v-for="variation in eventVariations"
                :key="variation"
                :label="`V${variation}`"
                :value="variation"
              />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item :label="$t('point.dnp3EventClass')">
            <el-select v-model="form.event_class" style="width: 100%">
              <el-option
                v-for="eventClass in [1, 2, 3]"
                :key="eventClass"
                :label="`Class ${eventClass}`"
                :value="eventClass"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="frameType === 0" :span="12">
          <el-form-item :label="$t('point.dnp3Deadband')">
            <el-input-number
              v-model="form.deadband"
              :min="0"
              :step="0.1"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row v-if="isControlPoint" :gutter="20">
        <el-col :span="12">
          <el-form-item :label="$t('point.dnp3ControlMode')">
            <el-select v-model="form.control_mode" style="width: 100%">
              <el-option label="Direct Operate" value="direct" />
              <el-option label="Select Before Operate" value="sbo" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col v-if="frameType === 2" :span="12">
          <el-form-item :label="$t('point.dnp3CrobOperation')">
            <el-select v-model="form.crob_operation" style="width: 100%">
              <el-option label="Latch" value="latch" />
              <el-option label="Pulse" value="pulse" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row
        v-if="frameType === 2 && form.crob_operation === 'pulse'"
        :gutter="20"
      >
        <el-col :span="8">
          <el-form-item :label="$t('point.dnp3PulseOn')">
            <el-input-number
              v-model="form.pulse_on_ms"
              :min="0"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="$t('point.dnp3PulseOff')">
            <el-input-number
              v-model="form.pulse_off_ms"
              :min="0"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="$t('point.dnp3PulseCount')">
            <el-input-number
              v-model="form.pulse_count"
              :min="1"
              :max="255"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item
        :label="
          $t(
            isDnp3Server
              ? 'point.dnp3InitialQuality'
              : 'point.dnp3ReceivedQuality',
          )
        "
      >
        <div class="quality-flags">
          <el-checkbox
            v-for="flag in qualityFlagOptions"
            :key="flag.key"
            v-model="qualityFlags[flag.key]"
            :disabled="!isDnp3Server"
            :label="$t(flag.label)"
          />
          <span v-if="!isDnp3Server" class="readonly-hint">
            {{ receivedQualityDetail }}
            {{ $t("device.dnp3ClientReadonly") }}
          </span>
        </div>
      </el-form-item>

      <el-row v-if="!isDnp3Server">
        <el-col :span="24">
          <el-form-item :label="$t('point.dnp3ReceivedTimestamp')">
            <el-input :model-value="receivedTimestampText" readonly />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row v-if="isDnp3Server" :gutter="20">
        <el-col :span="12">
          <el-form-item :label="$t('point.dnp3EventEnabled')">
            <el-switch v-model="form.event_enabled" :disabled="!isDnp3Server" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="$t('point.dnp3TimestampEnabled')">
            <el-switch
              v-model="form.timestamp_enabled"
              :disabled="!isDnp3Server || !form.event_enabled"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <div class="button-group">
        <el-button type="primary" @click="saveDnp3Metadata">
          {{ $t("common.save") }}
        </el-button>
        <el-button @click="loadDnp3Info">
          {{ $t("common.refresh") }}
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { editPointMetadata, getPointInfo } from "@/api/pointApi";
import { iec61850ReadPointMetadata } from "@/api/channelApi";

interface Props {
  deviceName: string;
  pointCode: string;
  active?: boolean;
  protocolType?: string;
  channelId?: number | null;
}

interface Dnp3PointConfig {
  static_variation: number;
  event_variation: number;
  event_class: number;
  deadband: number;
  control_mode: "direct" | "sbo";
  crob_operation: "latch" | "pulse";
  pulse_on_ms: number;
  pulse_off_ms: number;
  pulse_count: number;
  initial_quality: number;
  event_enabled: boolean;
  timestamp_enabled: boolean;
}

type QualityFlagKey =
  | "online"
  | "restart"
  | "commLost"
  | "remoteForced"
  | "localForced"
  | "overRange"
  | "referenceError";

const props = withDefaults(defineProps<Props>(), {
  active: true,
  protocolType: "",
  channelId: null,
});
const emit = defineEmits(["update-success"]);
const { t } = useI18n();

const isDnp3 = computed(() =>
  ["Dnp3Client", "Dnp3Server"].includes(props.protocolType),
);
const isDnp3Server = computed(() => props.protocolType === "Dnp3Server");
const frameType = ref(0);
const isControlPoint = computed(() => [2, 3].includes(frameType.value));

const staticVariationMap: Record<number, number[]> = {
  0: [1, 2, 3, 4, 5, 6],
  1: [1, 2],
  2: [1, 2],
  3: [1, 2, 3, 4],
};
const eventVariationMap: Record<number, number[]> = {
  0: [1, 2, 3, 4, 5, 6, 7, 8],
  1: [1, 2, 3],
  2: [1, 2],
  3: [1, 2, 3, 4, 5, 6, 7, 8],
};
const staticVariations = computed(
  () => staticVariationMap[frameType.value] || [1],
);
const eventVariations = computed(
  () => eventVariationMap[frameType.value] || [1],
);

const defaultsFor = (type: number): Dnp3PointConfig => {
  const variations: Record<number, [number, number]> = {
    0: [5, 7],
    1: [2, 2],
    2: [2, 1],
    3: [3, 3],
  };
  const [staticVariation, eventVariation] = variations[type] ?? [5, 7];
  return {
    static_variation: staticVariation,
    event_variation: eventVariation,
    event_class: [2, 3].includes(type) ? 2 : 1,
    deadband: 0,
    control_mode: "direct",
    crob_operation: "latch",
    pulse_on_ms: 100,
    pulse_off_ms: 100,
    pulse_count: 1,
    initial_quality: 1,
    event_enabled: [0, 1].includes(type),
    timestamp_enabled: true,
  };
};

const form = reactive<Dnp3PointConfig>(defaultsFor(0));
const receivedTimestampMs = ref<number | null>(null);
const receivedQualityDetail = ref("");
const receivedTimestampText = computed(() => {
  if (receivedTimestampMs.value === null) {
    return t("point.dnp3NoTimestamp");
  }
  const date = new Date(receivedTimestampMs.value);
  return `${date.toLocaleString()} (${receivedTimestampMs.value} ms)`;
});
const qualityFlags = reactive<Record<QualityFlagKey, boolean>>({
  online: true,
  restart: false,
  commLost: false,
  remoteForced: false,
  localForced: false,
  overRange: false,
  referenceError: false,
});
const qualityFlagOptions: Array<{
  key: QualityFlagKey;
  mask: number;
  label: string;
}> = [
  { key: "online", mask: 0x01, label: "point.dnp3Online" },
  { key: "restart", mask: 0x02, label: "point.dnp3Restart" },
  { key: "commLost", mask: 0x04, label: "point.dnp3CommLost" },
  { key: "remoteForced", mask: 0x08, label: "point.dnp3RemoteForced" },
  { key: "localForced", mask: 0x10, label: "point.dnp3LocalForced" },
  { key: "overRange", mask: 0x20, label: "point.dnp3OverRange" },
  { key: "referenceError", mask: 0x40, label: "point.dnp3ReferenceError" },
];
const knownQualityMask = qualityFlagOptions.reduce(
  (mask, flag) => mask | flag.mask,
  0,
);

const decodeQuality = (quality: number) => {
  qualityFlagOptions.forEach((flag) => {
    qualityFlags[flag.key] = (quality & flag.mask) !== 0;
  });
};

const encodeQuality = () => {
  const unknownFlags = form.initial_quality & ~knownQualityMask;
  return qualityFlagOptions.reduce(
    (quality, flag) => (qualityFlags[flag.key] ? quality | flag.mask : quality),
    unknownFlags,
  );
};

const parseConfig = (value: unknown): Partial<Dnp3PointConfig> => {
  if (typeof value === "string" && value.trim()) {
    try {
      const parsed: unknown = JSON.parse(value);
      return parsed && typeof parsed === "object"
        ? (parsed as Partial<Dnp3PointConfig>)
        : {};
    } catch {
      return {};
    }
  }
  return value && typeof value === "object"
    ? (value as Partial<Dnp3PointConfig>)
    : {};
};

interface Dnp3RuntimeMetadata {
  quality?: {
    online?: boolean;
    restart?: boolean;
    communication_lost?: boolean;
    remote_forced?: boolean;
    local_forced?: boolean;
    over_range?: boolean;
    reference_error?: boolean;
    detailQuality?: string | number | null;
  };
  timestamp?: {
    unixTimestampMs?: number | null;
  };
}

const loadDnp3RuntimeMetadata = async () => {
  if (!props.channelId || !isDnp3.value || isDnp3Server.value) return;
  try {
    const metadata = (await iec61850ReadPointMetadata(
      props.channelId,
      props.pointCode,
    )) as Dnp3RuntimeMetadata | null;
    const quality = metadata?.quality;
    if (quality) {
      qualityFlags.online = Boolean(quality.online);
      qualityFlags.restart = Boolean(quality.restart);
      qualityFlags.commLost = Boolean(quality.communication_lost);
      qualityFlags.remoteForced = Boolean(quality.remote_forced);
      qualityFlags.localForced = Boolean(quality.local_forced);
      qualityFlags.overRange = Boolean(quality.over_range);
      qualityFlags.referenceError = Boolean(quality.reference_error);
      receivedQualityDetail.value = String(quality.detailQuality ?? "");
    }
    receivedTimestampMs.value = metadata?.timestamp?.unixTimestampMs ?? null;
  } catch (error) {
    console.error("刷新DNP3品质时标失败:", error);
  }
};

const loadDnp3Info = async () => {
  try {
    const info = await getPointInfo(props.deviceName, props.pointCode);
    if (!info) return;
    frameType.value = info.frame_type ?? 0;
    Object.assign(
      form,
      defaultsFor(frameType.value),
      parseConfig(info.dnp3_config),
    );
    decodeQuality(form.initial_quality);
    await loadDnp3RuntimeMetadata();
  } catch (error) {
    console.error("加载DNP3属性失败:", error);
  }
};

let refreshTimer: ReturnType<typeof setInterval> | null = null;

const stopRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
};

const startRefresh = () => {
  stopRefresh();
  if (!isDnp3Server.value && props.channelId) {
    refreshTimer = setInterval(loadDnp3RuntimeMetadata, 1000);
  }
};

const saveDnp3Metadata = async () => {
  try {
    if (isDnp3Server.value) {
      form.initial_quality = encodeQuality();
    }
    const result = await editPointMetadata(props.deviceName, props.pointCode, {
      dnp3_config: { ...form },
    });
    if (result) {
      ElMessage.success(t("device.dnp3Updated"));
      emit("update-success");
    }
  } catch (error) {
    console.error("更新DNP3属性失败:", error);
  }
};

watch(
  [
    () => props.active,
    () => props.deviceName,
    () => props.pointCode,
    () => props.protocolType,
    () => props.channelId,
  ],
  () => {
    if (props.active && isDnp3.value && props.deviceName && props.pointCode) {
      loadDnp3Info();
      startRefresh();
    } else {
      stopRefresh();
    }
  },
  { immediate: true },
);

onBeforeUnmount(stopRefresh);
</script>

<style scoped>
.edit-dnp3 {
  margin: 0;
  padding: 16px;
  width: 620px;
  font-family: Arial, sans-serif;
  background-color: var(--panel-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
}

.simple-title {
  margin-bottom: 15px;
}

.simple-title span {
  color: #e6a23c;
  font-size: 16px;
  font-weight: 500;
}

.simple-title .el-divider {
  margin: 12px 0;
  background-color: #e6a23c;
}

.dnp3-form {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.quality-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.readonly-hint {
  color: #909399;
  font-size: 12px;
}

.button-group {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: auto;
  padding-top: 10px;
}
</style>
