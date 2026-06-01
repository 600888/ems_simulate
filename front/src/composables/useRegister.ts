/**
 * 寄存器组件公共逻辑 composable
 * 提取 SingleRegister / LongRegister / FloatRegister 共享的逻辑
 */

import { ref, watch, onMounted, type Ref } from 'vue';
import { ElMessage } from 'element-plus';
import { editPointData } from '@/api/pointApi';

export interface RegisterBase {
  real: number;
  mulCoe: number;
  addCoe: number;
}

/**
 * 公共寄存器编辑逻辑
 * @param props 组件 props
 * @param updateFromReal 从真实值更新寄存器的函数
 * @param defaultValue 默认值
 * @param emit emit 函数
 */
export function useRegisterEdit<T extends RegisterBase>(
  props: {
    rowIndex: number;
    deviceName: string;
    pointCode: string;
    realValue: number;
    mulCoe?: number;
    addCoe?: number;
    slaveId?: number;
  },
  updateFromReal: (value: number, register: Ref<T>) => void,
  defaultValue: T,
  emit: (event: 'editSuccess', rowIndex: number, realValue: number, hexStr?: string) => void,
) {
  const register = ref<T>({ ...defaultValue }) as Ref<T>;

  const reset = () => {
    register.value = { ...defaultValue };
  };

  const editRegisterValue = async (hexStr?: string) => {
    try {
      const isSuccess = await editPointData(
        props.deviceName,
        props.pointCode,
        parseFloat(register.value.real.toString()),
        props.slaveId,
      );
      if (isSuccess) {
        emit('editSuccess', props.rowIndex, parseFloat(register.value.real.toString()), hexStr);
        ElMessage({ message: '修改成功!', type: 'success' });
      }
    } catch (error) {
      console.error('Edit register failed:', error);
    }
  };

  watch(() => props.realValue, (newVal) => {
    updateFromReal(newVal, register);
  });

  watch(() => register.value.real, (newVal) => {
    updateFromReal(newVal, register);
  });

  onMounted(() => {
    register.value.mulCoe = props.mulCoe ?? 1;
    register.value.addCoe = props.addCoe ?? 0;
    updateFromReal(props.realValue, register);
  });

  return {
    register,
    reset,
    editRegisterValue,
  };
}
