<template>
  <div class="register">
    <div class="simple-title">
      <span>单点模拟设置</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="simulateForm">
      <el-row>
        <el-col :span="12">
          <el-form-item label="模拟方法" label-position="right" class="form-item">
            <el-select
              v-model="simulateForm.simulateMethod"
              placeholder="请选择模拟方法"
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
          <el-form-item label="步长" label-position="right" class="form-item">
            <el-input
              v-model.number="simulateForm.step"
              type="number"
              placeholder="请输入步长"
              style="width: 90%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row>
        <el-col :span="12">
          <el-form-item label="最小值" label-position="right" class="form-item">
            <el-input
              v-model.number="simulateForm.minValue"
              type="number"
              placeholder="请输入最小值"
              style="width: 90%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="最大值" label-position="right" class="form-item">
            <el-input
              v-model.number="simulateForm.maxValue"
              type="number"
              placeholder="请输入最大值"
              style="width: 90%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row>
        <el-col :span="24">
          <el-form-item label="特殊参数" label-position="right" class="form-item">
            <div class="special-params" v-if="showSpecialParams">
              <el-input
                v-if="simulateForm.simulateMethod === 'SineWave'"
                v-model.number="simulateForm.period"
                type="number"
                placeholder="请输入周期(秒)"
                style="width: 90%"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'SineWave'"
                v-model.number="simulateForm.phase"
                type="number"
                placeholder="请输入相位(度)"
                style="width: 90%"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'Ramp'"
                v-model.number="simulateForm.rampTime"
                type="number"
                placeholder="请输入斜坡时间(秒)"
                style="width: 90%"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'Pulse'"
                v-model.number="simulateForm.pulseWidth"
                type="number"
                placeholder="请输入脉冲宽度(秒)"
                style="width: 200px"
              />
              <el-input
                v-if="simulateForm.simulateMethod === 'Pulse'"
                v-model.number="simulateForm.pulseInterval"
                type="number"
                placeholder="请输入脉冲间隔(秒)"
                style="width: 200px"
              />
            </div>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row class="custom-row">
        <el-form-item class="custom-form-item">
          <el-button type="primary" @click="saveSettings">保存设置</el-button>
        </el-form-item>
        <el-form-item class="custom-form-item">
          <el-button @click="loadPointInfo">加载点信息</el-button>
        </el-form-item>
        <el-form-item class="custom-form-item">
          <el-button @click="resetSettings">重置</el-button>
        </el-form-item>
      </el-row>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { 
  getPointInfo, 
  setSinglePointSimulateMethod, 
  setSinglePointStep, 
  setPointSimulationRange 
} from '@/api/deviceApi';

interface Props {
  deviceName: string;
  pointCode: string;
}

const props = defineProps<Props>();
const emit = defineEmits(['update-success']);

const simulateOptions = ref([
  { value: 'Random', label: '随机模拟' },
  { value: 'AutoIncrement', label: '自增模拟' },
  { value: 'AutoDecrement', label: '自减模拟' },
  { value: 'SineWave', label: '正弦波模拟' },
  { value: 'Ramp', label: '斜坡模拟' },
  { value: 'Pulse', label: '脉冲模拟' }
]);

const simulateForm = reactive({
  simulateMethod: 'Random',
  step: 1,
  minValue: 0,
  maxValue: 100,
  period: 10, // 正弦波周期(秒)
  phase: 0,   // 正弦波相位(度)
  rampTime: 5, // 斜坡时间(秒)
  pulseWidth: 2, // 脉冲宽度(秒)
  pulseInterval: 5 // 脉冲间隔(秒)
});

const showSpecialParams = ref(false);

// 监听模拟方法变化，显示/隐藏特殊参数
watch(() => simulateForm.simulateMethod, (newMethod) => {
  showSpecialParams.value = ['SineWave', 'Ramp', 'Pulse'].includes(newMethod);
});

// 加载点信息
const loadPointInfo = async () => {
  try {
    const info = await getPointInfo(props.deviceName, props.pointCode);
    if (info) {
      simulateForm.step = info.step || 1;
      simulateForm.minValue = info.min_value || 0;
      simulateForm.maxValue = info.max_value || 100;
      simulateForm.simulateMethod = info.simulate_method || 'Random';
      // 加载特殊参数
      if (info.period) simulateForm.period = info.period;
      if (info.phase) simulateForm.phase = info.phase;
      if (info.ramp_time) simulateForm.rampTime = info.ramp_time;
      if (info.pulse_width) simulateForm.pulseWidth = info.pulse_width;
      if (info.pulse_interval) simulateForm.pulseInterval = info.pulse_interval;
      
      ElMessage.success('加载点信息成功');
    }
  } catch (error) {
    console.error('加载点信息失败:', error);
    ElMessage.error('加载点信息失败');
  }
};

// 保存设置
const saveSettings = async () => {
  try {
    // 验证表单
    if (simulateForm.minValue >= simulateForm.maxValue) {
      ElMessage.warning('最小值必须小于最大值');
      return;
    }
    
    // 保存模拟方法
    const methodResult = await setSinglePointSimulateMethod(
      props.deviceName,
      props.pointCode,
      simulateForm.simulateMethod
    );
    
    // 保存步长
    const stepResult = await setSinglePointStep(
      props.deviceName,
      props.pointCode,
      simulateForm.step
    );
    
    // 保存模拟范围
    const rangeResult = await setPointSimulationRange(
      props.deviceName,
      props.pointCode,
      simulateForm.minValue,
      simulateForm.maxValue
    );
    
    if (methodResult && stepResult && rangeResult) {
      ElMessage.success('设置保存成功');
      emit('update-success');
    } else {
      ElMessage.error('设置保存失败');
    }
  } catch (error) {
    console.error('保存设置失败:', error);
    ElMessage.error('保存设置失败');
  }
};

// 重置设置
const resetSettings = () => {
  simulateForm.simulateMethod = 'Random';
  simulateForm.step = 1;
  simulateForm.minValue = 0;
  simulateForm.maxValue = 100;
  simulateForm.period = 10;
  simulateForm.phase = 0;
  simulateForm.rampTime = 5;
  simulateForm.pulseWidth = 2;
  simulateForm.pulseInterval = 5;
  ElMessage.success('设置已重置');
};

// 处理模拟方法变化
const handleSimulateMethodChange = () => {
  // 可以在这里添加特定模拟方法的处理逻辑
};
</script>

<style lang="scss">
.register {
  margin-top: 10px;
  margin-bottom: 20px;
  margin-left: 20px;
  padding: 20px;
  width: 600px;
  height: auto;
  min-height: 350px;
  font-family: Arial, sans-serif;
  background-color: white;
  border-radius: 5px;
  box-shadow: 0 1px 3px rgba(0.2, 0.2, 0.2, 0.2);
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