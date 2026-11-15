import type { ChannelInfo } from "@/types/channel";
import type { DeviceGroupTreeResponse } from "@/api/deviceGroupApi";
import { isSerialConnectionType, PROTOCOL_TYPE } from "@/constants/protocol";

export type DeviceOperation =
  "start" | "stop" | "startSimulation" | "stopSimulation";
export interface DeviceRuntimeStatus {
  channel_id: number;
  name: string;
  status_available: boolean;
  running?: boolean;
  simulating?: boolean;
  simulation_supported?: boolean;
  simulation_reason?: string;
  model_loaded?: boolean;
  error?: string;
}
export interface ManagedDevice extends ChannelInfo {
  groupName: string;
  runtime?: DeviceRuntimeStatus;
}
export interface ManagementTreeNode {
  key: string;
  label: string;
  kind: "all" | "group" | "device";
  deviceIds: number[];
  children?: ManagementTreeNode[];
}

export function deviceAddress(device: ChannelInfo): string {
  if (isSerialConnectionType(device.conn_type)) {
    return `${device.com_port || "—"} · ${device.baud_rate || 9600} bps`;
  }
  return `${device.ip || "0.0.0.0"}:${device.port ?? "—"}`;
}

export function buildManagementTree(
  groups: DeviceGroupTreeResponse,
  channels: ChannelInfo[],
  ungroupedLabel: string,
): ManagementTreeNode[] {
  const assigned = new Set<number>();
  const deviceNodes = (deviceIds: Set<number>): ManagementTreeNode[] =>
    channels
      .filter((c) => c.device_id != null && deviceIds.has(c.device_id))
      .map((c) => {
        assigned.add(c.id);
        return {
          key: `device-${c.id}`,
          label: c.name,
          kind: "device",
          deviceIds: [c.id],
        };
      });
  const visit = (
    group: DeviceGroupTreeResponse["groups"][number],
  ): ManagementTreeNode => {
    const children = [
      ...(group.children || []).map(visit),
      ...deviceNodes(new Set((group.devices || []).map((d) => d.id))),
    ];
    return {
      key: `group-${group.id}`,
      label: group.name,
      kind: "group",
      children,
      deviceIds: children.flatMap((c) => c.deviceIds),
    };
  };
  const tree = groups.groups.map(visit);
  const ungrouped: ManagementTreeNode[] = channels
    .filter((c) => !assigned.has(c.id))
    .map((c) => ({
      key: `device-${c.id}`,
      label: c.name,
      kind: "device",
      deviceIds: [c.id],
    }));
  tree.push({
    key: "ungrouped",
    label: ungroupedLabel,
    kind: "group",
    children: ungrouped,
    deviceIds: ungrouped.map((d) => d.deviceIds[0]),
  });
  return tree;
}

/** A disabled action always has a user-facing reason; batches use the same rules. */
export function deviceOperationReason(
  device: ManagedDevice,
  operation: DeviceOperation,
): string {
  const state = device.runtime;
  if (state && !state.status_available) return "statusUnavailable";
  if (operation === "start") {
    if (state?.running) return "alreadyOn";
    // The backend restores cached IEC61850 models before starting the device.
    return "";
  }
  if (!state) return operation === "stop" ? "alreadyOff" : "notReady";
  if (operation === "stop")
    return state.running || state.simulating ? "" : "alreadyOff";
  if (operation === "stopSimulation")
    return state.simulating ? "" : "simulationIdle";
  if (state.simulating) return "simulationRunning";
  if (!state.running) return "powerOnFirst";
  if (device.protocol_type === PROTOCOL_TYPE.IEC61850 && !state.model_loaded)
    return "modelNotLoaded";
  if (!state.simulation_supported)
    return state.simulation_reason || "clientNoSim";
  return "";
}

/** Start every selected device operation concurrently and wait for all of them. */
export async function runDeviceOperations<T>(
  items: readonly T[],
  action: (item: T) => Promise<void>,
): Promise<void> {
  await Promise.all(items.map(action));
}
