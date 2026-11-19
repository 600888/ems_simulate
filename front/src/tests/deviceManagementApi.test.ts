import { controlManagedDevice } from "@/api/deviceManagementApi";
import { requestApi } from "@/api/http";
import { reloadDeviceConfig } from "@/api/channelApi";
import { DEVICE_API } from "@/constants/api";
import type { ManagedDevice } from "@/utils/deviceManagement";

jest.mock("@/api/http", () => ({ requestApi: jest.fn() }));
jest.mock("@/api/channelApi", () => ({ reloadDeviceConfig: jest.fn() }));
jest.mock("@/api/deviceApi", () => ({
  startDevice: jest.fn(),
  stopDevice: jest.fn(),
  startSimulation: jest.fn(),
  stopSimulation: jest.fn(),
}));
jest.mock("@/api/opcuaApi", () => ({ pauseOpcUaSimulation: jest.fn() }));

it("clears an unloaded device by channel ID without initializing or starting it", async () => {
  jest.mocked(requestApi).mockResolvedValue({ deleted_count: 7 });
  await controlManagedDevice(
    { id: 71, device_id: 900, name: "Server" } as ManagedDevice,
    "clearConnectionHistory",
  );
  expect(requestApi).toHaveBeenCalledWith(
    DEVICE_API.CLEAR_CONNECTION_HISTORY,
    "post",
    { channel_id: 71 },
  );
  expect(reloadDeviceConfig).not.toHaveBeenCalled();
});
