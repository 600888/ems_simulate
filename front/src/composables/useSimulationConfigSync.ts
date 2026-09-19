import { shallowRef } from "vue";

// 通知已展开的测点面板重新读取后端配置，不缓存另一份模拟参数。
export const simulationConfigChange = shallowRef<{ deviceName: string } | null>(
  null,
);

export function notifySimulationConfigChanged(deviceName: string): void {
  simulationConfigChange.value = { deviceName };
}
