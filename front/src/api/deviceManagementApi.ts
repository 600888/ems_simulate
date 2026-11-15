import { requestApi } from "./http";
import { reloadDeviceConfig } from "./channelApi";
import {
  startDevice,
  stopDevice,
  startSimulation,
  stopSimulation,
} from "./deviceApi";
import { pauseOpcUaSimulation } from "./opcuaApi";
import { PROTOCOL_TYPE } from "@/constants/protocol";
import { DEVICE_API } from "@/constants/api";
import type {
  DeviceOperation,
  DeviceRuntimeStatus,
  ManagedDevice,
} from "@/utils/deviceManagement";

export const getDeviceManagementStatus = (): Promise<DeviceRuntimeStatus[]> =>
  requestApi(DEVICE_API.MANAGEMENT_STATUS, "post", null);

export async function controlManagedDevice(
  device: ManagedDevice,
  operation: DeviceOperation,
): Promise<void> {
  if (operation === "start" && !device.runtime) {
    await reloadDeviceConfig(device.id);
    if (!(await startDevice(device.name)))
      throw new Error("Device operation failed");
    return;
  }
  if (
    device.protocol_type === PROTOCOL_TYPE.OPCUA &&
    (operation === "startSimulation" || operation === "stopSimulation")
  ) {
    await pauseOpcUaSimulation(device.id, operation === "stopSimulation");
    return;
  }
  const actions = {
    start: startDevice,
    stop: stopDevice,
    startSimulation,
    stopSimulation,
  };
  if (!(await actions[operation](device.name)))
    throw new Error("Device operation failed");
}
