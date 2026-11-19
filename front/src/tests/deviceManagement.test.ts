import {
  buildManagementTree,
  deviceAddress,
  deviceOperationReason,
  runDeviceOperations,
  type ManagedDevice,
} from "@/utils/deviceManagement";
import type { ChannelInfo } from "@/types/channel";
import type { DeviceGroupTreeResponse } from "@/api/deviceGroupApi";

const device = (id: number, deviceId: number): ChannelInfo => ({
  id,
  device_id: deviceId,
  name: `device-${id}`,
  code: `DEV_${id}`,
  protocol_type: 1,
  conn_type: 2,
  ip: "127.0.0.1",
  port: 502,
  rtu_addr: "1",
  timeout: 1000,
  enable: true,
});
const row = (overrides: Partial<ManagedDevice> = {}): ManagedDevice => ({
  ...device(10, 100),
  groupName: "test",
  runtime: {
    channel_id: 10,
    name: "device-10",
    status_available: true,
    running: true,
    simulating: false,
    simulation_supported: true,
  },
  ...overrides,
});

it("uses device IDs to join channels and includes descendants in group scope", () => {
  const groupDefaults = {
    code: "group",
    parent_id: null,
    description: null,
    status: 0,
    enable: true,
    created_at: null,
    updated_at: null,
  };
  const groupedDevice = (id: number) => ({
    id,
    code: `D${id}`,
    name: `D${id}`,
    device_type: 0,
    group_id: 1,
    enable: true,
  });
  const groups = {
    groups: [
      {
        id: 1,
        name: "parent",
        ...groupDefaults,
        devices: [groupedDevice(100)],
        children: [
          {
            ...groupDefaults,
            id: 2,
            name: "child",
            devices: [groupedDevice(200)],
            children: [],
          },
        ],
      },
    ],
    ungrouped: [],
  } satisfies DeviceGroupTreeResponse;
  const tree = buildManagementTree(
    groups,
    [device(10, 100), device(20, 200), device(30, 300)],
    "Ungrouped",
  );
  expect(tree[0].deviceIds.sort()).toEqual([10, 20]);
  expect(tree[0].children?.[0].deviceIds).toEqual([20]);
  expect(tree[1].deviceIds).toEqual([30]);
});

it("formats serial addresses for both serial roles", () => {
  expect(
    deviceAddress({
      ...device(1, 1),
      conn_type: 0,
      com_port: "COM7",
      baud_rate: 19200,
    }),
  ).toBe("COM7 · 19200 bps");
  expect(
    deviceAddress({ ...device(1, 1), conn_type: 3, com_port: "COM8" }),
  ).toBe("COM8 · 9600 bps");
});

it("guards simulation independently from power and honors runtime capabilities", () => {
  expect(deviceOperationReason(row(), "startSimulation")).toBe("");
  expect(deviceOperationReason(row(), "start")).toBe("alreadyOn");
  expect(
    deviceOperationReason(
      row({ runtime: { ...row().runtime!, running: false } }),
      "startSimulation",
    ),
  ).toBe("powerOnFirst");
  expect(
    deviceOperationReason(
      row({
        runtime: {
          ...row().runtime!,
          simulation_supported: false,
          simulation_reason: "clientNoSim",
        },
      }),
      "startSimulation",
    ),
  ).toBe("clientNoSim");
  expect(
    deviceOperationReason(row({ protocol_type: 4 }), "startSimulation"),
  ).toBe("modelNotLoaded");
  expect(deviceOperationReason(row({ runtime: undefined }), "start")).toBe("");
  expect(
    deviceOperationReason(
      row({ runtime: undefined, protocol_type: 4 }),
      "start",
    ),
  ).toBe("");
});

it("allows clearing saved history when a device is stopped, unloaded or has unknown runtime status", () => {
  expect(
    deviceOperationReason(
      row({ runtime: undefined }),
      "clearConnectionHistory",
    ),
  ).toBe("");
  expect(
    deviceOperationReason(
      row({ runtime: { ...row().runtime!, running: false } }),
      "clearConnectionHistory",
    ),
  ).toBe("");
  expect(
    deviceOperationReason(
      row({ runtime: { ...row().runtime!, status_available: false } }),
      "clearConnectionHistory",
    ),
  ).toBe("");
});

it("allows IEC61850 starts to restore models while retaining simulation guards", () => {
  const unloaded = row({
    protocol_type: 4,
    runtime: { ...row().runtime!, running: false, model_loaded: false },
  });
  expect(deviceOperationReason(unloaded, "start")).toBe("");
  expect(deviceOperationReason(unloaded, "startSimulation")).toBe(
    "powerOnFirst",
  );
  expect(
    deviceOperationReason(
      { ...unloaded, runtime: { ...unloaded.runtime!, running: true } },
      "startSimulation",
    ),
  ).toBe("modelNotLoaded");
});

it("allows stopping simulation even when power is off, and blocks unknown state", () => {
  expect(
    deviceOperationReason(
      row({ runtime: { ...row().runtime!, running: false, simulating: true } }),
      "stopSimulation",
    ),
  ).toBe("");
  expect(
    deviceOperationReason(
      row({ runtime: { ...row().runtime!, status_available: false } }),
      "start",
    ),
  ).toBe("statusUnavailable");
  expect(deviceOperationReason(row(), "stopSimulation")).toBe("simulationIdle");
});

it("starts all selected devices concurrently and waits for every operation", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const visited: number[] = [];
  const completed: number[] = [];
  const execution = runDeviceOperations([2, 4, 8, 10, 12], async (id) => {
    visited.push(id);
    await gate;
    completed.push(id);
  });
  try {
    expect(visited).toEqual([2, 4, 8, 10, 12]);
    expect(completed).toEqual([]);
  } finally {
    release();
    await execution;
  }
  expect(completed.sort((a, b) => a - b)).toEqual([2, 4, 8, 10, 12]);
});
