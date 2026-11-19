/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer } from "vue";
import { ElMessageBox } from "element-plus";
import { controlManagedDevice } from "@/api/deviceManagementApi";

jest.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
jest.mock("element-plus", () => ({ ElMessageBox: { confirm: jest.fn() } }));
jest.mock("@element-plus/icons-vue", () => ({}));
jest.mock("@/api/channelApi", () => ({
  getChannelList: jest.fn(),
  getProtocolConfig: jest.fn(),
}));
jest.mock("@/api/deviceGroupApi", () => ({ getDeviceGroupTree: jest.fn() }));
jest.mock("@/api/deviceManagementApi", () => ({
  controlManagedDevice: jest.fn(),
  getDeviceManagementStatus: jest.fn(),
}));
jest.mock("@/api/http", () => ({
  getApiErrorMessage: (error: Error) => error.message,
}));

const filename = resolve(
  __dirname,
  "../../components/device/DeviceManagementDialog.vue",
);
const { descriptor } = parse(readFileSync(filename, "utf8"), { filename });
const script = compileScript(descriptor, { id: "DeviceManagementDialog" });
const { outputText } = transpileModule(script.content, {
  compilerOptions: { module: ModuleKind.CommonJS, target: ScriptTarget.ES2020 },
});
const componentModule = { exports: {} as any };
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
const confirmationResult = "confirm" as Awaited<
  ReturnType<typeof ElMessageBox.confirm>
>;
let unmount: () => void;

function mountManagement() {
  const component = componentModule.exports.default;
  let state: any;
  const app = renderer.createApp(
    {
      ...component,
      setup(props, context) {
        state = component.setup(props, context);
        return () => null;
      },
    },
    { visible: false },
  );
  app.mount({});
  unmount = () => app.unmount();
  state.channels.value = [1, 2, 3].map((id) => ({
    id,
    name: `Server ${id}`,
    code: `S${id}`,
    protocol_type: 2,
    conn_type: 2,
  }));
  state.selectDevice(1, true);
  state.selectDevice(3, true);
  return state;
}

beforeEach(() => {
  jest.resetAllMocks();
  jest.mocked(controlManagedDevice).mockResolvedValue(undefined);
});
afterEach(() => unmount?.());

it("waits for confirmation then clears only the checked devices, including unloaded devices", async () => {
  let confirm!: (result: typeof confirmationResult) => void;
  jest.mocked(ElMessageBox.confirm).mockReturnValue(
    new Promise((resolve) => {
      confirm = resolve;
    }),
  );
  const state = mountManagement();
  const action = state.executeOperation(
    "clearConnectionHistory",
    state.selected.value,
  );
  expect(controlManagedDevice).not.toHaveBeenCalled();
  expect(state.busy.value).toBe(true);
  expect(ElMessageBox.confirm).toHaveBeenCalledWith(
    "deviceManagement.clearConnectionHistoryConfirm",
    "deviceManagement.clearConnectionHistory",
    expect.objectContaining({ type: "warning" }),
  );
  confirm(confirmationResult);
  await action;
  expect(
    jest.mocked(controlManagedDevice).mock.calls.map(([row]) => row.id),
  ).toEqual([1, 3]);
  expect(
    jest
      .mocked(controlManagedDevice)
      .mock.calls.every(
        ([, operation]) => operation === "clearConnectionHistory",
      ),
  ).toBe(true);
  expect(state.completed.value).toBe(2);
  expect(state.operationFailed.value).toBe(false);
  expect(state.busy.value).toBe(false);
});

it.each(["cancel", "close"])(
  "keeps history when the confirmation returns %s",
  async (action) => {
    jest.mocked(ElMessageBox.confirm).mockRejectedValue(action);
    const state = mountManagement();
    await state.executeOperation(
      "clearConnectionHistory",
      state.selected.value,
    );
    expect(controlManagedDevice).not.toHaveBeenCalled();
    expect(state.busy.value).toBe(false);
  },
);

it("finishes other selected devices when one deletion fails and reports the failure", async () => {
  jest.mocked(ElMessageBox.confirm).mockResolvedValue(confirmationResult);
  jest
    .mocked(controlManagedDevice)
    .mockRejectedValueOnce(new Error("History unavailable"));
  const state = mountManagement();
  await state.executeOperation("clearConnectionHistory", state.selected.value);
  expect(controlManagedDevice).toHaveBeenCalledTimes(2);
  expect(state.completed.value).toBe(2);
  expect(state.operationFailed.value).toBe(true);
  expect(state.operationDetails.value).toEqual([
    "Server 1：History unavailable",
  ]);
  expect(state.busy.value).toBe(false);
});
