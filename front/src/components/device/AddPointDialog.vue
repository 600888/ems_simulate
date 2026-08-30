<template>
  <el-dialog
    v-model="visible"
    :title="isBatch ? $t('point.batchAdd') : $t('point.add')"
    width="560px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <el-form-item :label="$t('point.addMode')">
        <el-radio-group v-model="isBatch">
          <el-radio :value="false">{{ $t("point.singleAdd") }}</el-radio>
          <el-radio :value="true">{{ $t("point.batchAdd") }}</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="$t('point.type')" prop="frame_type">
        <el-select
          v-model="formData.frame_type"
          :placeholder="$t('point.selectType')"
          style="width: 100%"
        >
          <el-option :label="`${$t('point.yc')} (YC)`" :value="0" />
          <el-option :label="`${$t('point.yx')} (YX)`" :value="1" />
          <el-option :label="`${$t('point.yk')} (YK)`" :value="2" />
          <el-option :label="`${$t('point.yt')} (YT)`" :value="3" />
        </el-select>
      </el-form-item>

      <template v-if="isBatch">
        <el-form-item :label="$t('point.batchCount')" prop="batchCount">
          <el-input-number
            v-model="batchCount"
            :min="1"
            :max="10000"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item
          :label="isDnp3 ? $t('point.startIndex') : $t('point.startAddress')"
          prop="reg_addr"
        >
          <el-input
            v-model="formData.reg_addr"
            :placeholder="$t('point.startAddrPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('point.codePrefix')">
          <el-input
            v-model="codePrefix"
            :placeholder="$t('point.codePrefixPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('point.namePrefix')">
          <el-input
            v-model="namePrefix"
            :placeholder="$t('point.namePrefixPlaceholder')"
          />
        </el-form-item>
      </template>

      <template v-else>
        <el-form-item :label="$t('point.code')" prop="code">
          <el-input
            v-model="formData.code"
            :placeholder="$t('point.codePlaceholder')"
          />
        </el-form-item>

        <el-form-item :label="$t('point.name')" prop="name">
          <el-input
            v-model="formData.name"
            :placeholder="$t('point.namePlaceholder')"
          />
        </el-form-item>

        <el-form-item
          :label="isDnp3 ? $t('point.index') : $t('point.regAddress')"
          prop="reg_addr"
        >
          <el-input
            v-model="formData.reg_addr"
            :placeholder="$t('point.regAddrPlaceholder')"
          />
        </el-form-item>
      </template>

      <el-form-item
        v-if="!isIec61850 && !isDlt645 && !isDnp3"
        :label="$t('point.slaveAddress')"
        prop="rtu_addr"
      >
        <el-select
          v-model="formData.rtu_addr"
          :placeholder="$t('point.selectSlaveAddress')"
          style="width: 100%"
        >
          <el-option
            v-for="slave in slaveIdList"
            :key="slave"
            :label="`${$t('point.slave')} ${slave}`"
            :value="slave"
          />
        </el-select>
      </el-form-item>

      <el-form-item
        v-if="!isIec104 && !isDnp3"
        :label="$t('point.funcCode')"
        prop="func_code"
      >
        <el-select
          v-model="formData.func_code"
          :placeholder="$t('point.selectFuncCode')"
          style="width: 100%"
        >
          <el-option
            v-for="fc in validFuncCodes"
            :key="fc.value"
            :label="fc.label"
            :value="fc.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item
        v-if="!isIec104 && !isDnp3"
        :label="$t('point.decodeCode')"
        prop="decode_code"
      >
        <el-select
          v-model="formData.decode_code"
          :placeholder="$t('point.selectDecodeCode')"
          style="width: 100%"
        >
          <el-option-group :label="$t('decode.bit8')">
            <el-option label="0x10 - Byte (unsigned)" value="0x10" />
            <el-option label="0x11 - Byte (signed)" value="0x11" />
          </el-option-group>
          <el-option-group :label="$t('decode.int16')">
            <el-option label="0x20 - Short AB (big endian)" value="0x20" />
            <el-option label="0x21 - Short AB (signed)" value="0x21" />
            <el-option label="0x22 - Short BA (byte swap)" value="0x22" />
            <el-option label="0xB0 - Short BA (unsigned)" value="0xB0" />
            <el-option label="0xB1 - Short BA (signed)" value="0xB1" />
            <el-option label="0xC0 - Short CD (little endian)" value="0xC0" />
            <el-option label="0xC1 - Short CD (signed)" value="0xC1" />
          </el-option-group>
          <el-option-group :label="$t('decode.int32')">
            <el-option label="0x40 - Long AB CD (big endian)" value="0x40" />
            <el-option label="0x41 - Long AB CD (signed)" value="0x41" />
            <el-option label="0x43 - Long BA DC (big word swap)" value="0x43" />
            <el-option label="0x44 - Long BA DC (signed)" value="0x44" />
            <el-option label="0xD0 - Long DC BA (little endian)" value="0xD0" />
            <el-option label="0xD1 - Long DC BA (signed)" value="0xD1" />
            <el-option
              label="0xD4 - Long CD AB (little word swap)"
              value="0xD4"
            />
            <el-option label="0xD5 - Long CD AB (signed)" value="0xD5" />
          </el-option-group>
          <el-option-group :label="$t('decode.float32')">
            <el-option label="0x42 - Float AB CD (big endian)" value="0x42" />
            <el-option
              label="0x45 - Float BA DC (big word swap)"
              value="0x45"
            />
            <el-option
              label="0xD2 - Float DC BA (little endian)"
              value="0xD2"
            />
            <el-option
              label="0xD3 - Float CD AB (little word swap)"
              value="0xD3"
            />
          </el-option-group>
          <el-option-group :label="$t('decode.int64')">
            <el-option
              label="0x60 - Int64 AB CD EF GH (big endian)"
              value="0x60"
            />
            <el-option label="0x61 - Int64 AB CD EF GH (signed)" value="0x61" />
            <el-option
              label="0x62 - Double AB CD EF GH (big endian)"
              value="0x62"
            />
            <el-option
              label="0xE0 - Int64 HG FE DC BA (little endian)"
              value="0xE0"
            />
            <el-option label="0xE1 - Int64 HG FE DC BA (signed)" value="0xE1" />
            <el-option
              label="0xE2 - Double HG FE DC BA (little endian)"
              value="0xE2"
            />
          </el-option-group>
        </el-select>
      </el-form-item>

      <template v-if="[1, 2].includes(formData.frame_type)">
        <el-form-item :label="$t('point.bitOffset')" prop="bit">
          <el-input-number
            v-model="formData.bit"
            :min="0"
            :max="31"
            :step="1"
            :placeholder="$t('point.bitOffsetPlaceholder')"
            style="width: 100%"
            controls-position="right"
            :value-on-clear="null"
          />
        </el-form-item>
      </template>

      <template v-if="isDnp3 && formData.dnp3_config">
        <el-divider content-position="left">DNP3</el-divider>
        <el-form-item :label="$t('point.dnp3StaticVariation')">
          <el-select
            v-model="formData.dnp3_config.static_variation"
            style="width: 100%"
          >
            <el-option
              v-for="v in dnp3StaticVariations"
              :key="v"
              :label="`V${v}`"
              :value="v"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('point.dnp3EventVariation')">
          <el-select
            v-model="formData.dnp3_config.event_variation"
            style="width: 100%"
          >
            <el-option
              v-for="v in dnp3EventVariations"
              :key="v"
              :label="`V${v}`"
              :value="v"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('point.dnp3EventClass')">
          <el-select
            v-model="formData.dnp3_config.event_class"
            style="width: 100%"
          >
            <el-option
              v-for="v in [1, 2, 3]"
              :key="v"
              :label="`Class ${v}`"
              :value="v"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="formData.frame_type === 0"
          :label="$t('point.dnp3Deadband')"
        >
          <el-input-number
            v-model="formData.dnp3_config.deadband"
            :min="0"
            :step="0.1"
            style="width: 100%"
          />
        </el-form-item>
        <template v-if="[2, 3].includes(formData.frame_type)">
          <el-form-item :label="$t('point.dnp3ControlMode')">
            <el-select
              v-model="formData.dnp3_config.control_mode"
              style="width: 100%"
            >
              <el-option label="Direct Operate" value="direct" />
              <el-option label="Select Before Operate" value="sbo" />
            </el-select>
          </el-form-item>
        </template>
        <template v-if="formData.frame_type === 2">
          <el-form-item :label="$t('point.dnp3CrobOperation')">
            <el-select
              v-model="formData.dnp3_config.crob_operation"
              style="width: 100%"
            >
              <el-option label="Latch" value="latch" />
              <el-option label="Pulse" value="pulse" />
            </el-select>
          </el-form-item>
          <template v-if="formData.dnp3_config.crob_operation === 'pulse'">
            <el-form-item :label="$t('point.dnp3PulseOn')"
              ><el-input-number
                v-model="formData.dnp3_config.pulse_on_ms"
                :min="0"
                style="width: 100%"
            /></el-form-item>
            <el-form-item :label="$t('point.dnp3PulseOff')"
              ><el-input-number
                v-model="formData.dnp3_config.pulse_off_ms"
                :min="0"
                style="width: 100%"
            /></el-form-item>
            <el-form-item :label="$t('point.dnp3PulseCount')"
              ><el-input-number
                v-model="formData.dnp3_config.pulse_count"
                :min="1"
                :max="255"
                style="width: 100%"
            /></el-form-item>
          </template>
        </template>
        <el-form-item :label="$t('point.dnp3InitialQuality')">
          <el-input-number
            v-model="formData.dnp3_config.initial_quality"
            :min="0"
            :max="255"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="$t('point.dnp3EventEnabled')"
          ><el-switch v-model="formData.dnp3_config.event_enabled"
        /></el-form-item>
        <el-form-item :label="$t('point.dnp3TimestampEnabled')"
          ><el-switch v-model="formData.dnp3_config.timestamp_enabled"
        /></el-form-item>
      </template>

      <el-form-item
        v-if="isIec104"
        :label="$t('point.iec104Type')"
        prop="iec_type_id"
      >
        <el-select
          v-model="formData.iec_type_id"
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
                : `${t(getIec104TypeLabelKey(item.type_id))} (${item.type_id})`
            "
            :value="item.type_id"
          />
        </el-select>
      </el-form-item>

      <el-form-item
        v-if="showQualityFlags"
        :label="$t('point.qualityDescriptor')"
      >
        <div class="quality-flags">
          <el-checkbox
            v-model="qualityFlags.ov"
            :disabled="!canOverflow"
            label="OV"
          />
          <el-checkbox v-model="qualityFlags.bl" label="BL" />
          <el-checkbox v-model="qualityFlags.sb" label="SB" />
          <el-checkbox v-model="qualityFlags.nt" label="NT" />
          <el-checkbox v-model="qualityFlags.iv" label="IV" />
        </div>
      </el-form-item>

      <template v-if="[0, 3].includes(formData.frame_type)">
        <el-form-item :label="$t('point.mulCoe')" prop="mul_coe">
          <el-input-number
            v-model="formData.mul_coe"
            :precision="6"
            :step="0.1"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="$t('point.addCoe')" prop="add_coe">
          <el-input-number
            v-model="formData.add_coe"
            :precision="6"
            :step="1"
            style="width: 100%"
          />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">{{ $t("common.cancel") }}</el-button>
      <el-button type="primary" :loading="loading" @click="handleSubmit">
        {{
          isBatch
            ? `${t("common.confirm")} (${batchCount})`
            : $t("common.confirm")
        }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage } from "element-plus";
import { showErrorOnce } from "@/api/http";
import { addPoint, addPointsBatch, type PointCreateData } from "@/api/pointApi";
import {
  IEC104_TYPES_BY_FRAME_TYPE,
  getDefaultIec104Type,
  getIec104TypeLabelKey,
  encodeIec104Quality,
  supportsOverflow,
  supportsQuality as supportsQualityCheck,
} from "@/types/point";

const { t, locale } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
  slaveIdList: number[];
  currentSlaveId?: number;
  protocolType?: string;
}>();

// 判断是否为 IEC104 协议（IEC104 不需要功能码）
const isIec104 = computed(() => {
  const pt = props.protocolType || "";
  return [
    "Iec104Client",
    "Iec104Server",
    "Iec101Client",
    "Iec101Server",
  ].includes(pt);
});

// 判断是否为 IEC61850 协议（IEC61850 不需要从机地址）
const isIec61850 = computed(() => {
  const pt = props.protocolType || "";
  return pt === "Iec61850Client" || pt === "Iec61850Server";
});

const isDlt645 = computed(() => {
  const pt = props.protocolType || "";
  return pt === "Dlt645Client" || pt === "Dlt645Server";
});

// 判断是否为 DNP3 协议（DNP3 用 index 寻址，无功能码/解析码/从站地址）
const isDnp3 = computed(() => {
  const pt = props.protocolType || "";
  return pt === "Dnp3Client" || pt === "Dnp3Server";
});

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "success"): void;
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const formRef = ref<FormInstance>();
const loading = ref(false);
const isBatch = ref(false);
const batchCount = ref(10);

// 根据测点类型动态计算编码和名称前缀
const typeNameMap: Record<number, { code: string; nameKey: string }> = {
  0: { code: "YC_", nameKey: "point.yc" },
  1: { code: "YX_", nameKey: "point.yx" },
  2: { code: "YK_", nameKey: "point.yk" },
  3: { code: "YT_", nameKey: "point.yt" },
};

// IEC104 各测点类型的起始地址偏移（与后端 IEC104Strategy 一致）
const iec104AddressOffset: Record<number, number> = {
  0: 16385, // 遥测 YC
  1: 1, // 遥信 YX
  2: 24577, // 遥控 YK
  3: 25089, // 遥调 YT
};

const codePrefix = ref("YC_");
const namePrefix = ref(t("point.yc"));

const formData = reactive<PointCreateData>({
  frame_type: 0,
  code: "",
  name: "",
  rtu_addr: 1,
  reg_addr: "0",
  func_code: 3,
  decode_code: "0x20",
  bit: null,
  mul_coe: 1.0,
  add_coe: 0.0,
  iec_type_id: null,
  iec_quality: 0,
  dnp3_config: {
    static_variation: 5,
    event_variation: 7,
    event_class: 1,
    deadband: 0,
    control_mode: "direct",
    crob_operation: "latch",
    pulse_on_ms: 100,
    pulse_off_ms: 100,
    pulse_count: 1,
    initial_quality: 1,
    event_enabled: true,
    timestamp_enabled: true,
  },
});

const dnp3StaticVariations = computed(
  () =>
    ({ 0: [1, 2, 3, 4, 5, 6], 1: [1, 2], 2: [1, 2], 3: [1, 2, 3, 4] })[
      formData.frame_type
    ] || [1],
);
const dnp3EventVariations = computed(
  () =>
    ({
      0: [1, 2, 3, 4, 5, 6, 7, 8],
      1: [1, 2, 3],
      2: [1, 2],
      3: [1, 2, 3, 4, 5, 6, 7, 8],
    })[formData.frame_type] || [1],
);

// 品质描述符标志位
const qualityFlags = reactive({
  ov: false,
  bl: false,
  sb: false,
  nt: false,
  iv: false,
});

// 是否可以设置溢出标志（仅遥测和遥调）
const canOverflow = computed(() => supportsOverflow(formData.frame_type));
// 是否显示品质描述符（IEC104 协议且非遥控）
const showQualityFlags = computed(
  () => isIec104.value && supportsQualityCheck(formData.frame_type),
);

// 获取当前帧类型可用的 IEC104 类型列表
const availableIec104Types = computed(() => {
  return IEC104_TYPES_BY_FRAME_TYPE[formData.frame_type] || [];
});

// 监听测点类型变化，自动更新前缀和地址
watch(
  () => formData.frame_type,
  (newType) => {
    const prefixes = typeNameMap[newType] || {
      code: "POINT_",
      nameKey: "point.point",
    };
    codePrefix.value = prefixes.code;
    namePrefix.value = t(prefixes.nameKey);

    // 遥控 (2) 和 遥调 (3) 默认功能码为 6，遥测 (0) 和 遥信 (1) 默认功能码为 3
    if (newType === 2 || newType === 3) {
      formData.func_code = 6;
    } else {
      formData.func_code = 3;
    }

    // IEC104 协议下自动设置默认类型和起始地址
    if (isIec104.value) {
      formData.iec_type_id = getDefaultIec104Type(newType);
      formData.reg_addr = String(iec104AddressOffset[newType] ?? 0);
    }
    if (isDnp3.value && formData.dnp3_config) {
      const defaults = { 0: [5, 7], 1: [2, 2], 2: [2, 1], 3: [3, 3] }[
        newType
      ] || [1, 1];
      formData.dnp3_config.static_variation = defaults[0];
      formData.dnp3_config.event_variation = defaults[1];
      formData.dnp3_config.event_class = [2, 3].includes(newType) ? 2 : 1;
      formData.dnp3_config.event_enabled = [0, 1].includes(newType);
    }
  },
);

// 可用的功能码列表
const validFuncCodes = computed(() => {
  const allCodes = [
    { value: 1, label: t("table.funcCode01") },
    { value: 2, label: t("table.funcCode02") },
    { value: 3, label: t("table.funcCode03") },
    { value: 4, label: t("table.funcCode04") },
    { value: 5, label: t("table.funcCode05") },
    { value: 6, label: t("table.funcCode06") },
    { value: 15, label: t("table.funcCode15") },
    { value: 16, label: t("table.funcCode16") },
  ];

  const type = formData.frame_type;

  if (type === 0 || type === 1) {
    // 遥测 (0) 和 遥信 (1): 允许 1, 2, 3, 4
    return allCodes.filter((c) => [1, 2, 3, 4].includes(c.value));
  } else if (type === 2 || type === 3) {
    // 遥控 (2) 和 遥调 (3): 允许 5, 6, 15, 16
    return allCodes.filter((c) => [5, 6, 15, 16].includes(c.value));
  }

  return allCodes;
});

// 根据解析码计算寄存器跨度
const getRegisterSpan = (decodeCode: string): number => {
  // 64位解析码占4个寄存器
  if (["0x60", "0x61", "0x62", "0xE0", "0xE1", "0xE2"].includes(decodeCode)) {
    return 4;
  }
  // 32位解析码占2个寄存器
  if (
    [
      "0x40",
      "0x41",
      "0x42",
      "0x43",
      "0x44",
      "0x45",
      "0xD0",
      "0xD1",
      "0xD2",
      "0xD3",
      "0xD4",
      "0xD5",
    ].includes(decodeCode)
  ) {
    return 2;
  }
  // 8位和16位占1个寄存器
  return 1;
};

const rules = computed<FormRules>(() => ({
  frame_type: [
    { required: true, message: t("point.pleaseSelectType"), trigger: "change" },
  ],
  code: isBatch.value
    ? []
    : [
        {
          required: true,
          message: t("point.pleaseEnterCode"),
          trigger: "blur",
        },
      ],
  name: isBatch.value
    ? []
    : [
        {
          required: true,
          message: t("point.pleaseEnterName"),
          trigger: "blur",
        },
      ],
  rtu_addr:
    isIec61850.value || isDlt645.value
      ? []
      : [
          {
            required: true,
            message: t("point.pleaseSelectSlaveAddress"),
            trigger: "change",
          },
        ],
  reg_addr: [
    { required: true, message: t("point.pleaseEnterRegAddr"), trigger: "blur" },
  ],
}));

watch(
  () => props.modelValue,
  (val) => {
    if (val && props.currentSlaveId) {
      formData.rtu_addr = props.currentSlaveId;
    }
    // IEC104 协议下，打开时自动设置默认类型和起始地址
    if (val && isIec104.value) {
      if (!formData.iec_type_id) {
        formData.iec_type_id = getDefaultIec104Type(formData.frame_type);
      }
      formData.reg_addr = String(iec104AddressOffset[formData.frame_type] ?? 0);
    }
  },
);

const handleClose = () => {
  visible.value = false;
  formRef.value?.resetFields();
  formData.bit = null;
  formData.iec_quality = 0;
  qualityFlags.ov = false;
  qualityFlags.bl = false;
  qualityFlags.sb = false;
  qualityFlags.nt = false;
  qualityFlags.iv = false;
  isBatch.value = false;
};

const handleSubmit = async () => {
  try {
    await formRef.value?.validate();
    loading.value = true;

    if (isBatch.value) {
      // 批量添加模式
      const startAddr = formData.reg_addr.startsWith("0x")
        ? parseInt(formData.reg_addr, 16)
        : parseInt(formData.reg_addr);
      const span = getRegisterSpan(formData.decode_code);

      // 编码品质描述符
      const qualityValue = encodeIec104Quality(
        qualityFlags,
        formData.frame_type,
      );

      const points: PointCreateData[] = [];
      for (let i = 0; i < batchCount.value; i++) {
        points.push({
          ...formData,
          dnp3_config: isDnp3.value ? { ...formData.dnp3_config! } : undefined,
          code: `${codePrefix.value}${String(i + 1).padStart(3, "0")}`,
          name: `${namePrefix.value}${i + 1}`,
          reg_addr: String(startAddr + i * span),
          iec_quality: qualityValue,
        });
      }

      const success = await addPointsBatch(
        props.deviceName,
        formData.frame_type,
        points,
      );

      if (success) {
        ElMessage.success(
          t("point.batchAddSuccess", { count: batchCount.value }),
        );
        emit("success");
        handleClose();
      } else {
        showErrorOnce(t("point.batchAddFailed"));
      }
    } else {
      // 单个添加模式
      // 编码品质描述符
      formData.iec_quality = encodeIec104Quality(
        qualityFlags,
        formData.frame_type,
      );
      const success = await addPoint(props.deviceName, {
        ...formData,
        dnp3_config: isDnp3.value ? { ...formData.dnp3_config! } : undefined,
      });
      if (success) {
        ElMessage.success(t("point.addSuccess"));
        emit("success");
        handleClose();
      } else {
        showErrorOnce(t("point.addFailed"));
      }
    }
  } catch (error) {
    console.error(t("point.formValidationFailed"), error);
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped lang="scss">
:deep(.el-dialog__body) {
  padding-top: 20px;
}

.quality-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}
</style>
