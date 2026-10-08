/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer, nextTick, reactive } from "vue";
import {
  browseOpcUaNodes,
  getOpcUaConfig,
  getOpcUaFeatures,
  listOpcUaPoints,
  readOpcUaHistory,
} from "@/api/opcuaApi";
import { showError } from "@/api/http";

jest.mock("vue-i18n", () => ({
  useI18n: () => ({ t: (key: string) => key, locale: { value: "en-US" } }),
}));
jest.mock("element-plus", () => ({
  ElMessage: { success: jest.fn(), warning: jest.fn() },
}));
jest.mock("@/api/http", () => ({ showError: jest.fn() }));
jest.mock("@/api/opcuaApi", () => ({
  browseOpcUaNodes: jest.fn(),
  getOpcUaConfig: jest.fn(),
  getOpcUaFeatures: jest.fn(),
  listOpcUaPoints: jest.fn(),
  readOpcUaHistory: jest.fn(),
}));

// Run the actual SFC setup and reactive navigation with mocked remote services.
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
const components = new Map<string, any>();
const cleanup: (() => void)[] = [];
function mount(name = "OpcUaPanel", extraProps: Record<string, unknown> = {}) {
  let component = components.get(name);
  if (!component) {
    const filename = resolve(__dirname, `../../components/device/${name}.vue`);
    const { descriptor } = parse(readFileSync(filename, "utf8"), { filename });
    const script = compileScript(descriptor, { id: name });
    const { outputText } = transpileModule(script.content, {
      compilerOptions: {
        module: ModuleKind.CommonJS,
        target: ScriptTarget.ES2020,
      },
    });
    const module = { exports: {} as any };
    new Function("require", "module", "exports", outputText)(
      (id: string) => (/\.(vue|scss)$/.test(id) ? {} : require(id)),
      module,
      module.exports,
    );
    component = module.exports.default;
    components.set(name, component);
  }
  const props = reactive({
    channelId: 3,
    role: "client",
    running: true,
    ...extraProps,
  });
  let state: any;
  const app = renderer.createApp({
    setup() {
      state = component.setup(props, { expose() {}, emit() {} });
      return () => null;
    },
  });
  app.mount({});
  cleanup.push(() => app.unmount());
  return { state, props };
}
async function flush() {
  for (let i = 0; i < 8; i++) await Promise.resolve();
  await nextTick();
}
const result = {
  nodes: [
    { node_id: "ns=2;s=folder", browse_name: "Folder", node_class: "Object" },
  ],
  total: 250,
  offset: 0,
  has_more: true,
};
beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(browseOpcUaNodes).mockResolvedValue(result);
  jest
    .mocked(listOpcUaPoints)
    .mockResolvedValue({ points: [], total: 0 } as any);
  jest.mocked(getOpcUaConfig).mockResolvedValue({
    endpoint_url: "opc.tcp://localhost:4840",
    endpoint_path: "/",
    namespace_uri: "urn:test",
  } as any);
  jest.mocked(getOpcUaFeatures).mockResolvedValue({});
  jest
    .mocked(readOpcUaHistory)
    .mockResolvedValue({ values: [], continuation: null } as any);
});
afterEach(() => cleanup.splice(0).forEach((dispose) => dispose()));

test("returning through multiple levels restores each parent and its page", async () => {
  const { state } = mount();
  await state.browse();
  state.changeRemotePage(2);
  await flush();
  state.openNode("ns=2;s=folder");
  await flush();
  state.openNode("ns=2;s=child");
  await flush();
  state.browseParent();
  await flush();
  expect(state.browseRoot.value).toBe("ns=2;s=folder");
  state.browseParent();
  await flush();
  expect(browseOpcUaNodes).toHaveBeenLastCalledWith(3, "i=85", 100);
  expect(state.remotePage.value).toBe(2);
  expect(state.browseParents.value).toEqual([]);
  const calls = jest.mocked(browseOpcUaNodes).mock.calls.length;
  state.browseParent();
  expect(browseOpcUaNodes).toHaveBeenCalledTimes(calls);
});

test("failed child and parent requests preserve the current directory and path", async () => {
  const { state } = mount();
  await state.browse();
  const error = new Error("Browse failed");
  jest.mocked(browseOpcUaNodes).mockRejectedValueOnce(error);
  state.openNode("ns=2;s=folder");
  await flush();
  expect(state.browseRoot.value).toBe("i=85");
  expect(state.browseParents.value).toEqual([]);
  state.openNode("ns=2;s=folder");
  await flush();
  jest.mocked(browseOpcUaNodes).mockRejectedValueOnce(error);
  state.browseParent();
  await flush();
  expect(state.browseRoot.value).toBe("ns=2;s=folder");
  expect(state.browseParents.value).toEqual([{ nodeId: "i=85", page: 1 }]);
  expect(state.remoteNodes.value).toEqual(result.nodes);
  expect(showError).toHaveBeenCalledWith(error);
});

test("manual root changes reset pagination and parent history", async () => {
  const { state } = mount();
  await state.browse();
  state.openNode("ns=2;s=folder");
  await flush();
  state.changeRemotePage(3);
  await flush();
  state.browseRoot.value = " ns=4;s=other ";
  await state.browse();
  expect(browseOpcUaNodes).toHaveBeenLastCalledWith(3, "ns=4;s=other", 0);
  expect(state.browseParents.value).toEqual([]);
  expect(state.remotePage.value).toBe(1);
});

test("switching devices clears navigation and ignores the old pending response", async () => {
  const { state, props } = mount();
  let complete!: (value: typeof result) => void;
  jest.mocked(browseOpcUaNodes).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const request = state.browse();
  props.channelId = 4;
  await flush();
  complete(result);
  await request;
  expect(state.remoteNodes.value).toEqual([]);
  expect(state.browseParents.value).toEqual([]);
  expect(state.browseRoot.value).toBe("i=85");
  expect(state.browsing.value).toBe(false);
});

test("history workspace sends Beijing picker input as UTC", async () => {
  const nodeId = "ns=2;s=power";
  const { state } = mount("OpcUaHistoryWorkspace", {
    nodes: [{ node_id: nodeId, browse_name: "Power", node_class: "Variable" }],
  });
  await flush();
  state.range.value = ["2026-10-08 00:00:00", "2026-10-08 01:00:00"];
  await state.query(false);
  expect(readOpcUaHistory).toHaveBeenCalledWith(
    3,
    nodeId,
    "2026-10-07T16:00:00.000Z",
    "2026-10-07T17:00:00.000Z",
    null,
    expect.any(Object),
  );
});

test.each(["en-US", "zh-CN"])(
  "trend axis and cursor labels use Beijing time in %s",
  (locale) => {
    const time = Date.parse("2026-10-07T16:30:45.123Z");
    const { state } = mount("OpcUaTrendPlot", {
      title: "Power",
      points: [{ timestamp: new Date(time).toISOString(), value: 12 }],
    });
    state.locale.value = locale;
    expect(state.timeLabel(time, true)).toBe("00:30:45.123");
    expect(state.timestampLabel(time)).toContain("00:30:45.123");
  },
);
