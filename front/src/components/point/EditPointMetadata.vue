<template>
  <div class="edit-metadata">
    <div class="simple-title">
      <span>编辑测点属性</span>
      <el-divider></el-divider>
    </div>
    <el-form label-width="auto" :model="metadataForm">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="名称" class="form-item">
            <el-input v-model="metadataForm.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="编码" class="form-item">
            <el-input v-model="metadataForm.code" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="地址" class="form-item">
            <el-input v-model="metadataForm.reg_addr" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="解析码" class="form-item">
            <el-input v-model="metadataForm.decode_code" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="功能码" class="form-item">
            <el-input v-model.number="metadataForm.func_code" type="number" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="20" v-if="isYcOrYt">
        <el-col :span="12">
          <el-form-item label="乘系数" class="form-item">
            <el-input v-model.number="metadataForm.mul_coe" type="number" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="加系数" class="form-item">
            <el-input v-model.number="metadataForm.add_coe" type="number" />
          </el-form-item>
        </el-col>
      </el-row>
      <div class="button-group">
        <el-button type="primary" @click="saveMetadata">保存属性</el-button>
        <el-button @click="loadPointInfo">刷新</el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { getPointInfo, editPointMetadata } from '@/api/deviceApi';

interface Props {
  deviceName: string;
  pointCode: string;
}

const props = defineProps<Props>();
const emit = defineEmits(['update-success']);

const metadataForm = reactive({
  name: '',
  code: '',
  reg_addr: '',
  func_code: 3,
  decode_code: '',
  mul_coe: 1.0,
  add_coe: 0.0,
  frame_type: 0
});

const isYcOrYt = computed(() => [0, 3].includes(metadataForm.frame_type));

// 加载点信息
const loadPointInfo = async () => {
  try {
    const info = await getPointInfo(props.deviceName, props.pointCode);
    if (info) {
      metadataForm.name = info.name || '';
      metadataForm.code = info.code || '';
      metadataForm.reg_addr = info.reg_addr || '';
      metadataForm.func_code = info.func_code || 3;
      metadataForm.decode_code = info.decode_code || '';
      metadataForm.mul_coe = info.mul_coe ?? 1.0;
      metadataForm.add_coe = info.add_coe ?? 0.0;
      metadataForm.frame_type = info.frame_type ?? 0;
    }
  } catch (error) {
    console.error('加载点信息失败:', error);
  }
};

// 保存元数据
const saveMetadata = async () => {
  try {
    const result = await editPointMetadata(props.deviceName, props.pointCode, metadataForm);
    if (result) {
      ElMessage.success('测点属性已更新');
      emit('update-success', metadataForm.code); // 通知上层编码可能已变
    } else {
      ElMessage.error('更新失败');
    }
  } catch (error: any) {
    ElMessage.error('更新失败: ' + error.message);
  }
};

onMounted(() => {
  loadPointInfo();
});
</script>

<style scoped>
.edit-metadata {
  margin-top: 10px;
  margin-bottom: 20px;
  margin-left: 20px;
  padding: 20px;
  width: 500px; /* Keeping 500px for the row/col layout */
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
  width: 100%; /* Rows will handle the width */
}

.button-group {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: 10px;
}
</style>
