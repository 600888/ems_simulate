<template>
  <div class="register">
    <div class="simple-title">
      <span>{{ $t("pointSimulator.title") }}</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="simulateForm">
      <el-row>
        <el-col :span="12">
          <el-form-item
            :label="$t('pointSimulator.method')"
            label-position="right"
            class="form-item"
          >
            <el-select
              v-model="simulateForm.simulateMethod"
              :placeholder="$t('pointSimulator.selectMethod')"
              style="width: 90%"
              @change="handleSimulateMethodChange"
            >
              <el-option
                v-for="item in simulateOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item
            :label="$t('pointSimulator.step')"
            label-position="right"
            class="form-item"
          >
            <el-input
              v-model.number="simulateForm.step"
              type="number"
              :placeholder="$t('pointSimulator.enterStep')"
              style="width: 90%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row>
        <el-col :span="12">
          <el-form-item
            :label="$t('pointSimulator.minValue')"
            label-position="right"
            class="form-item"
          >
            <el-input
              v-model.number="simulateForm.minValue"
              type="number"
              :placeholder="$t('pointSimulator.enterMin')"
              style="width: 90%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item
            :label="$t('pointSimulator.maxValue')"
            label-position="right"
            class="form-item"
          >
            <el-input
              v-model.number="simulateForm.maxValue"
              type="number"
              :placeholder="$t('pointSimulator.enterMax')"
              style="width: 90%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row>
        <el-col :span="24">
          <el-form-item
            :label="$t('pointSimulator.specialParams')"
            label-position="right"
            class="form-item"
          >
            <div class="special-params" v-if="showSpecialParams">
              <el-input
                v-if="simulateForm.simulateMethod === 'SineWave'"
                v-model.number="simulateForm.period"
                type="number"
                :placeholder="$t('pointSimulator.enterPeriod')"
                style="width: 90%"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'SineWave'"
                v-model.number="simulateForm.phase"
                type="number"
                :placeholder="$t('pointSimulator.enterPhase')"
                style="width: 90%"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'Ramp'"
                v-model.number="simulateForm.rampTime"
                type="number"
                :placeholder="$t('pointSimulator.enterRampTime')"
                style="width: 90%"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'Pulse'"
                v-model.number="simulateForm.pulseWidth"
                type="number"
                :placeholder="$t('pointSimulator.enterPulseWidth')"
                style="width: 200px"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'Pulse'"
                v-model.number="simulateForm.pulseInterval"
                type="number"
                :placeholder="$t('pointSimulator.enterPulseInterval')"
                style="width: 200px"
              />
            </div>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row class="custom-row">
        <el-form-item class="custom-form-item">
          <el-button type="primary" @click="saveSettings">{{
            $t("pointSimulator.saveSettings")
          }}</el-button>
        </el-form-item>
        <el-form-item class="custom-form-item">
          <el-button @click="loadPointInfo">{{
            $t("pointSimulator.loadPointInfo")
          }}</el-button>
        </el-form-item>
        <el-form-item class="custom-form-item">
          <el-button @click="resetSettings">{{
            $t("pointSimulator.reset")
          }}</el-button>
        </el-form-item>
      </el-row>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { showErrorOnce } from "@/api/http";
import {
  getPointInfo,
  setSinglePointSimulateMethod,
  setSinglePointStep,
  setPointSimulationRange,
} from "@/api/pointApi";

interface Props {
  deviceName: string;
  pointCode: string;
  active?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  active: true,
});
const emit = defineEmits(["update-success"]);

const { t } = useI18n();

const simulateOptions = computed(() => [
  { value: "Random", label: t("device.random") },
  { value: "AutoIncrement", label: t("device.autoIncrement") },
  { value: "AutoDecrement", label: t("device.autoDecrement") },
  { value: "SineWave", label: t("device.sineWave") },
  { value: "Ramp", label: t("device.ramp") },
  { value: "Pulse", label: t("device.pulse") },
]);

const simulateForm = reactive({
  simulateMethod: "Random",
  step: 1,
  minValue: 0,
  maxValue: 100,
  period: 10, // 正弦波周期(秒)
  phase: 0, // 正弦波相位(度)
  rampTime: 5, // 斜坡时间(秒)
  pulseWidth: 2, // 脉冲宽度(秒)
  pulseInterval: 5, // 脉冲间隔(秒)
});

const showSpecialParams = ref(false);

// 监听模拟方法变化，显示/隐藏特殊参数
watch(
  () => simulateForm.simulateMethod,
  (newMethod) => {
    showSpecialParams.value = ["SineWave", "Ramp", "Pulse"].includes(newMethod);
  },
);

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
watch([() => props.deviceName, () => props.pointCode], () => {
  if (props.active) {
    loadPointInfo();
  }
});

// 加载点信息
const loadPointInfo = async () => {
  try {
    const info = await getPointInfo(props.deviceName, props.pointCode);
    if (info) {
      simulateForm.step = info.step || 1;
      simulateForm.minValue = info.min_value || 0;
      simulateForm.maxValue = info.max_value || 100;
      simulateForm.simulateMethod = info.simulate_method || "Random";
      // 加载特殊参数
      if (info.period) simulateForm.period = info.period;
      if (info.phase) simulateForm.phase = info.phase;
      if (info.ramp_time) simulateForm.rampTime = info.ramp_time;
      if (info.pulse_width) simulateForm.pulseWidth = info.pulse_width;
      if (info.pulse_interval) simulateForm.pulseInterval = info.pulse_interval;

      ElMessage.success(t("pointSimulator.loaded"));
    }
  } catch (error) {
    console.error("加载点信息失败:", error);
    // error message is handled by global interceptor
  }
};

// 保存设置
const saveSettings = async () => {
  try {
    // 验证表单
    if (simulateForm.minValue >= simulateForm.maxValue) {
      ElMessage.warning(t("pointSimulator.minLtMax"));
      return;
    }

    // 保存模拟方法
    const methodResult = await setSinglePointSimulateMethod(
      props.deviceName,
      props.pointCode,
      simulateForm.simulateMethod,
    );

    // 保存步长
    const stepResult = await setSinglePointStep(
      props.deviceName,
      props.pointCode,
      simulateForm.step,
    );

    // 保存模拟范围
    const rangeResult = await setPointSimulationRange(
      props.deviceName,
      props.pointCode,
      simulateForm.minValue,
      simulateForm.maxValue,
    );

    if (methodResult && stepResult && rangeResult) {
      ElMessage.success(t("pointSimulator.saved"));
      emit("update-success");
    } else {
      showErrorOnce(t("pointSimulator.saveFailed"));
    }
  } catch (error) {
    console.error("保存设置失败:", error);
    // error message is handled by global interceptor
  }
};

// 重置设置
const resetSettings = () => {
  simulateForm.simulateMethod = "Random";
  simulateForm.step = 1;
  simulateForm.minValue = 0;
  simulateForm.maxValue = 100;
  simulateForm.period = 10;
  simulateForm.phase = 0;
  simulateForm.rampTime = 5;
  simulateForm.pulseWidth = 2;
  simulateForm.pulseInterval = 5;
  ElMessage.success(t("pointSimulator.resetDone"));
};

// 处理模拟方法变化
const handleSimulateMethodChange = () => {
  // 可以在这里添加特定模拟方法的处理逻辑
};
</script>

<style lang="scss">
.register {
  margin: 0;
  padding: 16px;
  width: 600px;
  height: auto;
  min-height: 350px;
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
  width: 300px;
}

.special-params {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.custom-row {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 10px;
}

.custom-form-item {
  margin: 0 10px;
}
</style>
