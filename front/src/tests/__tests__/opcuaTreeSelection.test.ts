/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer, nextTick, reactive } from "vue";
import {
  getOpcUaFeatures,
  getOpcUaNodeCapabilities,
  listOpcUaVariables,
  saveOpcUaFeature,
} from "@/api/opcuaApi";
import { DRAG_MIME, decodeUaDrag, type UaSelection } from "@/utils/opcuaPubSub";

jest.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
jest.mock("element-plus", () => ({
  ElMessage: { success: jest.fn(), warning: jest.fn() },
}));
jest.mock("@/api/http", () => ({ showError: jest.fn() }));
jest.mock("@/api/opcuaApi", () => ({
  getOpcUaFeatures: jest.fn(),
  getOpcUaNodeCapabilities: jest.fn(),
  listOpcUaVariables: jest.fn(),
  saveOpcUaFeature: jest.fn(),
}));

// Exercise the real SFC setup, events and reactive drafts without a browser DOM.
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
function mountPanel(
  name: string,
  props: Record<string, unknown>,
  emit = jest.fn(),
) {
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
      (id: string) => (id.endsWith(".vue") ? {} : require(id)),
      module,
      module.exports,
    );
    component = module.exports.default;
    components.set(name, component);
  }
  const panelProps = reactive(props);
  let state: any;
  const app = renderer.createApp({
    setup() {
      state = component.setup(panelProps, { expose() {}, emit });
      return () => null;
    },
  });
  app.mount({});
  cleanup.push(() => app.unmount());
  return { state, props: panelProps };
}
async function flush() {
  for (let i = 0; i < 8; i++) await Promise.resolve();
  await nextTick();
}
const variable = {
  node_id: "ns=2;s=power",
  browse_name: "Power",
  node_class: "Variable",
  key: "i=85/ns=2;s=power",
};
const source = {
  node_id: "i=2253",
  browse_name: "Server",
  node_class: "Object",
  event_notifier: true,
  key: "i=85/i=2253",
};
async function workspace(role: "client" | "server", running = false) {
  const props = { channelId: 3, role, running, active: false };
  const panel = mountPanel("OpcUaPubSub", props);
  await flush();
  const emit = jest.fn((event: string, nodes: UaSelection[]) => {
    if (event === "add") void panel.state.addNodes(nodes);
  });
  const tree = mountPanel("OpcUaNodeTree", props, emit);
  return { panel: panel.state, tree: tree.state, emit };
}

describe("OPC UA tree checkbox transfers", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(getOpcUaFeatures).mockResolvedValue({});
    jest.mocked(listOpcUaVariables).mockResolvedValue({ nodes: [] });
    jest.mocked(getOpcUaNodeCapabilities).mockImplementation(
      async (_, id) =>
        ({
          node_id: id,
          node_class: "Variable",
          history_read: true,
          event_notifier: true,
        }) as any,
    );
  });
  afterEach(() => cleanup.splice(0).forEach((dispose) => dispose()));

  it.each(["server", "client"] as const)(
    "adds a checked point to the %s draft without the add button",
    async (role) => {
      const { panel, tree, emit } = await workspace(role, role === "client");
      tree.onCheck(variable, { checkedNodes: [variable] });
      await flush();
      expect(emit).toHaveBeenCalledWith("add", [variable]);
      expect(panel.realtimeNodes.value).toEqual([
        expect.objectContaining({ node_id: variable.node_id }),
      ]);
      expect(panel.dirty.value).toBe(true);
      expect(saveOpcUaFeature).not.toHaveBeenCalled();
    },
  );

  it("does not add unchecked nodes or pagination placeholders", async () => {
    const { tree, emit } = await workspace("server");
    const more = { ...variable, key: "more", more: true };
    tree.onCheck(variable, { checkedNodes: [] });
    tree.onCheck(more, { checkedNodes: [more] });
    expect(tree.checked.value).toEqual([]);
    expect(emit).not.toHaveBeenCalled();
  });

  it("adds checked nodes to the active history and event drafts", async () => {
    const { panel, tree } = await workspace("server");
    panel.kind.value = "history";
    tree.onCheck(variable, { checkedNodes: [variable] });
    await flush();
    expect(panel.historyNodes.value[0].node_id).toBe(variable.node_id);
    panel.kind.value = "events";
    tree.onCheck(source, { checkedNodes: [variable, source] });
    await flush();
    expect(panel.eventNodes.value[0].node_id).toBe(source.node_id);
    expect(panel.realtimeNodes.value).toEqual([]);
  });

  it("keeps capability validation for checkbox additions", async () => {
    const { panel, tree } = await workspace("client", true);
    panel.kind.value = "history";
    jest.mocked(getOpcUaNodeCapabilities).mockResolvedValue({
      ...variable,
      history_read: false,
    } as any);
    tree.onCheck(variable, { checkedNodes: [variable] });
    await flush();
    expect(panel.historyNodes.value).toEqual([]);
    expect(panel.feedback.value).toContain("Power: opcua.requireHistory");
  });

  it("retains rapid checks during capability reads and deduplicates later drops", async () => {
    const { panel, tree } = await workspace("client", true);
    const second = { ...variable, node_id: "ns=2;s=voltage", key: "voltage" };
    let finishFirst!: (node: any) => void;
    let finishSecond!: (node: any) => void;
    jest
      .mocked(getOpcUaNodeCapabilities)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishFirst = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishSecond = resolve;
          }),
      );
    tree.onCheck(variable, { checkedNodes: [variable] });
    tree.onCheck(second, { checkedNodes: [variable, second] });
    expect(getOpcUaNodeCapabilities).toHaveBeenCalledTimes(2);
    finishFirst(variable);
    await flush();
    expect(panel.adding.value).toBe(true);
    finishSecond(second);
    await flush();
    expect(panel.adding.value).toBe(false);
    expect(
      panel.realtimeNodes.value.map((n: UaSelection) => n.node_id),
    ).toEqual([variable.node_id, second.node_id]);
    const setData = jest.fn();
    tree.drag({ dataTransfer: { setData } }, variable);
    expect(setData.mock.calls[0][0]).toBe(DRAG_MIME);
    expect(decodeUaDrag(setData.mock.calls[0][1], 3)).toHaveLength(2);
    panel.drop({
      preventDefault() {},
      dataTransfer: { getData: () => setData.mock.calls[0][1] },
    });
    await flush();
    expect(panel.currentSubscription.value.items).toHaveLength(2);
  });
});
