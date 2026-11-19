/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  clearConnectionHistory,
  getConnectionHistory,
  getConnectionSummary,
} from "@/api/connectionMonitorApi";

jest.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
jest.mock("element-plus", () => ({
  ElMessage: { success: jest.fn() },
  ElMessageBox: { confirm: jest.fn() },
}));
jest.mock("@element-plus/icons-vue", () => ({}));
jest.mock("@/api/connectionMonitorApi", () => ({
  clearConnectionHistory: jest.fn(),
  getConnectionHistory: jest.fn(),
  getConnectionSummary: jest.fn(),
  getConnectionDetail: jest.fn(),
  getCurrentConnections: jest.fn(),
}));

const filename = resolve(
  __dirname,
  "../../components/device/ConnectionMonitorDialog.vue",
);
const { descriptor } = parse(readFileSync(filename, "utf8"), { filename });
const script = compileScript(descriptor, { id: "ConnectionMonitorDialog" });
const { outputText } = transpileModule(script.content, {
  compilerOptions: { module: ModuleKind.CommonJS, target: ScriptTarget.ES2020 },
});
const componentModule = { exports: {} as any };
const confirmationResult = "confirm" as Awaited<
  ReturnType<typeof ElMessageBox.confirm>
>;
new Function("require", "module", "exports", outputText)(
  require,
  componentModule,
  componentModule.exports,
);
const renderer = createRenderer<any, any>({
  patchProp() {},
  insert() {},
  remove() {},
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  setText() {},
  setElementText() {},
  parentNode: () => null,
  nextSibling: () => null,
});
let unmount: () => void;

function mountMonitor() {
  let state: any;
  const app = renderer.createApp({
    setup() {
      state = componentModule.exports.default.setup(
        {
          modelValue: true,
          deviceName: "Server",
          serverName: "Server",
          endpoint: "127.0.0.1:2404",
        },
        { expose() {}, emit() {} },
      );
      return () => null;
    },
  });
  app.mount({});
  unmount = () => app.unmount();
  state.history.items = [{ session_id: "old" }];
  state.history.total = 1;
  state.historyPage.value = 3;
  return state;
}

beforeEach(() => {
  jest.resetAllMocks();
  jest.mocked(clearConnectionHistory).mockResolvedValue({ deleted_count: 1 });
  jest.mocked(getConnectionHistory).mockResolvedValue({
    supported: true,
    total: 0,
    retention_limit: 100,
    items: [],
  });
  jest.mocked(getConnectionSummary).mockResolvedValue({
    supported: true,
    server_running: true,
    current_count: 1,
    active_count: 1,
    idle_count: 0,
    history_count: 0,
    abnormal_disconnects_today: 0,
  });
});
afterEach(() => unmount?.());

it("waits for confirmation before deleting and refreshes history and summary", async () => {
  let confirm!: (
    value: Awaited<ReturnType<typeof ElMessageBox.confirm>>,
  ) => void;
  jest.mocked(ElMessageBox.confirm).mockReturnValue(
    new Promise((resolve) => {
      confirm = resolve;
    }),
  );
  const state = mountMonitor();
  const action = state.handleClearHistory();
  expect(clearConnectionHistory).not.toHaveBeenCalled();
  expect(state.history.total).toBe(1);
  expect(ElMessageBox.confirm).toHaveBeenCalled();

  confirm(confirmationResult);
  await action;

  expect(clearConnectionHistory).toHaveBeenCalledWith("Server");
  expect(state.history.items).toEqual([]);
  expect(state.historyPage.value).toBe(1);
  expect(state.summary.history_count).toBe(0);
  expect(state.summary.current_count).toBe(1);
  expect(state.clearingHistory.value).toBe(false);
  expect(ElMessage.success).toHaveBeenCalledWith(
    "connectionMonitor.historyCleared",
  );
});

it.each(["cancel", "close"])(
  "preserves records when confirmation returns %s",
  async (action) => {
    jest.mocked(ElMessageBox.confirm).mockRejectedValue(action);
    const state = mountMonitor();
    await state.handleClearHistory();
    expect(clearConnectionHistory).not.toHaveBeenCalled();
    expect(state.history.items).toEqual([{ session_id: "old" }]);
    expect(state.historyPage.value).toBe(3);
    expect(state.clearingHistory.value).toBe(false);
    expect(ElMessage.success).not.toHaveBeenCalled();
  },
);

it("preserves the displayed records if deletion fails", async () => {
  jest.mocked(ElMessageBox.confirm).mockResolvedValue(confirmationResult);
  jest
    .mocked(clearConnectionHistory)
    .mockRejectedValue(new Error("Database unavailable"));
  const errorLog = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    const state = mountMonitor();
    await state.handleClearHistory();
    expect(state.history.total).toBe(1);
    expect(state.clearingHistory.value).toBe(false);
    expect(ElMessage.success).not.toHaveBeenCalled();
  } finally {
    errorLog.mockRestore();
  }
});
