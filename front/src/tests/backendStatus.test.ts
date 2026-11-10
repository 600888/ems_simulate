import { checkBackendStatus } from "@/utils/tauri";
import { invoke } from "@tauri-apps/api/core";

jest.mock("@/i18n", () => ({
  __esModule: true,
  default: { global: { t: (key: string) => key } },
}));
jest.mock("@tauri-apps/api/core", () => ({ invoke: jest.fn() }));

const fetchMock = jest.fn();
const invokeMock = invoke as jest.Mock;
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalFetch = globalThis.fetch;

function setPage(url: string, desktop = false) {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: new URL(url),
      setTimeout,
      clearTimeout,
      ...(desktop ? { __TAURI_INTERNALS__: {} } : {}),
    },
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  globalThis.fetch = fetchMock;
  fetchMock.mockResolvedValue({ ok: true });
  invokeMock.mockResolvedValue(false);
});

afterAll(() => {
  globalThis.fetch = originalFetch;
  if (originalWindow) {
    Object.defineProperty(globalThis, "window", originalWindow);
  } else {
    Reflect.deleteProperty(globalThis, "window");
  }
});

test.each([
  "http://192.168.1.20:8991",
  "http://ems-server:8080",
  "https://ems.example.com",
  "http://[2001:db8::1]:8991",
  "http://localhost:8080",
])("web health checks use the actual site origin: %s", async (origin) => {
  setPage(`${origin}/#/devices`);
  expect(await checkBackendStatus()).toBe(true);
  expect(fetchMock).toHaveBeenCalledWith(
    `${origin}/api/health`,
    expect.objectContaining({
      cache: "no-store",
      signal: expect.any(AbortSignal),
    }),
  );
  expect(invokeMock).not.toHaveBeenCalled();
});

test("an explicitly supplied backend URL takes precedence", async () => {
  setPage("https://ems.example.com");
  expect(await checkBackendStatus("https://backend.example.com:9443///")).toBe(
    true,
  );
  expect(fetchMock.mock.calls[0][0]).toBe(
    "https://backend.example.com:9443/api/health",
  );
});

test.each(["http://tauri.localhost", "tauri://localhost"])(
  "desktop app pages retain the local backend probe: %s",
  async (url) => {
    setPage(url, true);
    expect(await checkBackendStatus()).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8991/api/health");
    expect(invokeMock).toHaveBeenCalledWith("is_backend_ready", undefined);
  },
);

test("desktop backend pages retain their dynamically assigned port", async () => {
  setPage("http://127.0.0.1:9182", true);
  expect(await checkBackendStatus()).toBe(true);
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:9182/api/health");
});

test("web health checks still report an unavailable service", async () => {
  setPage("http://192.168.1.20:8991");
  fetchMock.mockResolvedValueOnce({ ok: false });
  expect(await checkBackendStatus()).toBe(false);
  fetchMock.mockRejectedValueOnce(new Error("Connection refused"));
  expect(await checkBackendStatus()).toBe(false);
});

test("desktop process readiness can confirm a failed HTTP probe", async () => {
  setPage("http://tauri.localhost", true);
  fetchMock.mockRejectedValueOnce(new Error("Connection refused"));
  invokeMock.mockResolvedValueOnce(true);
  expect(await checkBackendStatus()).toBe(true);
});
