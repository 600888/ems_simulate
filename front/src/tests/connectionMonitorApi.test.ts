import {
  getConnectionDetail,
  getConnectionHistory,
  getConnectionSummary,
  getCurrentConnections,
} from "@/api/connectionMonitorApi";
import { requestApi } from "@/api/http";
import { DEVICE_API } from "@/constants";

jest.mock("@/api/http", () => ({
  instance: {},
  requestApi: jest.fn(),
}));

const mockedRequest = requestApi as jest.MockedFunction<typeof requestApi>;

describe("connection monitoring API", () => {
  beforeEach(() => mockedRequest.mockReset());

  it("uses the device-scoped summary and current endpoints", async () => {
    mockedRequest
      .mockResolvedValueOnce({ current_count: 2 })
      .mockResolvedValueOnce({ items: [] });

    await getConnectionSummary("Modbus Server");
    await getCurrentConnections("Modbus Server");

    expect(mockedRequest).toHaveBeenNthCalledWith(
      1,
      DEVICE_API.CONNECTION_SUMMARY,
      "post",
      {
        device_name: "Modbus Server",
      },
    );
    expect(mockedRequest).toHaveBeenNthCalledWith(
      2,
      DEVICE_API.CURRENT_CONNECTIONS,
      "post",
      {
        device_name: "Modbus Server",
      },
    );
  });

  it("normalizes history pagination and filters", async () => {
    mockedRequest.mockResolvedValue({
      items: [],
      total: 0,
      retention_limit: 100,
    });

    await getConnectionHistory("IEC104 Server", {
      page: 2,
      page_size: 50,
      disconnect_reason: "network_reset",
      remote_ip: " 192.0.2.8 ",
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      DEVICE_API.CONNECTION_HISTORY,
      "post",
      {
        device_name: "IEC104 Server",
        page: 2,
        page_size: 50,
        disconnect_reason: "network_reset",
        remote_ip: "192.0.2.8",
      },
    );
  });

  it("requests details with both device and session identity", async () => {
    mockedRequest.mockResolvedValue({ session_id: "session-1" });

    await getConnectionDetail("DNP3 Server", "session-1");

    expect(mockedRequest).toHaveBeenCalledWith(
      DEVICE_API.CONNECTION_DETAIL,
      "post",
      {
        device_name: "DNP3 Server",
        session_id: "session-1",
      },
    );
  });
});
