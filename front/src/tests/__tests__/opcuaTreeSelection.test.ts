/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer, nextTick, reactive, watchEffect } from "vue";
import {
  getOpcUaFeatures,
  browseOpcUaNodes,
  browseOpcUaServer,
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
  browseOpcUaNodes: jest.fn(),
  browseOpcUaServer: jest.fn(),
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
  data_type: "Double" as const,
  initial_value: 0,
  writable: true,
  key: "i=85/ns=2;s=power",
};
const source = {
  node_id: "i=2253",
  browse_name: "Server",
  node_class: "Object",
  event_notifier: true,
  key: "i=85/i=2253",
};
const second = {
  ...variable,
  node_id: "ns=2;s=voltage",
  key: "i=85/ns=2;s=voltage",
};
async function workspace(role: "client" | "server", running = false) {
  const props = { channelId: 3, role, running, active: false };
  const panel = mountPanel("OpcUaPubSub", props);
  await flush();
  const emit = jest.fn((event: string, nodes: any, checked?: boolean) => {
    if (event === "add") void panel.state.addNodes(nodes);
    else if (event === "selection-change")
      void panel.state.onTreeSelectionChange(nodes, checked);
  });
  const tree = mountPanel(
    "OpcUaNodeTree",
    {
      ...props,
      selectedNodes: panel.state.selectedNodes.value,
      selectionRevision: 0,
    },
    emit,
  );
  cleanup.push(
    watchEffect(() => {
      tree.props.selectedNodes = panel.state.selectedNodes.value;
      tree.props.selectionRevision = panel.state.selectionRevision.value;
    }),
  );
  const treeApi = {
    setCheckedKeys: jest.fn(),
    filter: jest.fn(),
    remove: jest.fn(),
    append: jest.fn(),
  };
  tree.state.tree.value = treeApi;
  await tree.state.loadChildren(
    { level: 1, data: { node_id: "i=85", key: "i=85" } },
    jest.fn(),
  );
  return {
    panel: panel.state,
    tree: tree.state,
    emit,
    treeApi,
    panelProps: panel.props,
  };
}

describe("OPC UA tree checkbox transfers", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(getOpcUaFeatures).mockResolvedValue({});
    jest
      .mocked(listOpcUaVariables)
      .mockResolvedValue({ nodes: [variable, second] });
    jest.mocked(browseOpcUaNodes).mockResolvedValue({
      nodes: [variable, second, source],
      has_more: false,
    } as any);
    jest.mocked(browseOpcUaServer).mockResolvedValue({
      nodes: [variable, second, source],
      has_more: false,
    } as any);
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
      expect(emit).toHaveBeenCalledWith("selection-change", variable, true);
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
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit).toHaveBeenCalledWith("selection-change", variable, false);
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
    expect(tree.checked.value).toEqual([]);
  });

  it("retains rapid checks during capability reads and deduplicates later drops", async () => {
    const { panel, tree } = await workspace("client", true);
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
    expect(tree.checked.value).toHaveLength(2);
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

  it.each(["server", "client"] as const)(
    "removes unchecked points from the %s draft and reflects right-side removals",
    async (role) => {
      const { panel, tree, treeApi } = await workspace(role, role === "client");
      await panel.addNodes([variable, second]);
      await flush();
      expect(tree.checked.value.map((node: any) => node.node_id)).toEqual([
        variable.node_id,
        second.node_id,
      ]);
      tree.onCheck(variable, { checkedNodes: [second] });
      await flush();
      expect(
        panel.realtimeNodes.value.map((node: any) => node.node_id),
      ).toEqual([second.node_id]);
      panel.removeRealtime(second.node_id);
      await flush();
      expect(tree.checked.value).toEqual([]);
      expect(treeApi.setCheckedKeys).toHaveBeenLastCalledWith([]);
    },
  );

  it("synchronizes both directions for history and events", async () => {
    const { panel, tree } = await workspace("server");
    panel.kind.value = "history";
    await panel.addNodes([variable]);
    await flush();
    expect(tree.checked.value[0].node_id).toBe(variable.node_id);
    tree.onCheck(variable, { checkedNodes: [] });
    expect(panel.historyNodes.value).toEqual([]);
    await panel.addNodes([variable]);
    panel.removeHistoryNode(variable.node_id);
    await flush();
    expect(tree.checked.value).toEqual([]);

    panel.kind.value = "events";
    await panel.addNodes([source]);
    await flush();
    expect(tree.checked.value[0].node_id).toBe(source.node_id);
    tree.onCheck(source, { checkedNodes: [] });
    expect(panel.eventNodes.value).toEqual([]);
    await panel.addNodes([source]);
    panel.removeEventSource(source.node_id);
    await flush();
    expect(tree.checked.value).toEqual([]);
  });

  it("follows the active dataset and data tab without deleting other drafts", async () => {
    const { panel, tree } = await workspace("server");
    await panel.addNodes([variable]);
    panel.publisher.value.writers.push({
      ...panel.variableWriter.value,
      writer_id: 3,
      fields: [],
    });
    panel.variableWriterId.value = 3;
    await panel.addNodes([second]);
    await flush();
    expect(tree.checked.value[0].node_id).toBe(second.node_id);
    panel.variableWriterId.value = 1;
    await flush();
    expect(tree.checked.value[0].node_id).toBe(variable.node_id);
    panel.kind.value = "history";
    await flush();
    expect(tree.checked.value).toEqual([]);
    await panel.addNodes([second]);
    panel.kind.value = "realtime";
    await flush();
    expect(tree.checked.value[0].node_id).toBe(variable.node_id);
    expect(panel.historyNodes.value[0].node_id).toBe(second.node_id);
  });

  it("follows the active client subscription", async () => {
    const { panel, tree } = await workspace("client", true);
    await panel.addNodes([variable]);
    panel.newSubscription();
    await flush();
    expect(tree.checked.value).toEqual([]);
    await panel.addNodes([second]);
    await flush();
    expect(tree.checked.value[0].node_id).toBe(second.node_id);
    panel.subscriptionIndex.value = 0;
    await flush();
    expect(tree.checked.value[0].node_id).toBe(variable.node_id);
  });

  it("does not restore a node unchecked before its capability read completes", async () => {
    const { panel, tree } = await workspace("client", true);
    let finish!: (node: any) => void;
    jest.mocked(getOpcUaNodeCapabilities).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    tree.onCheck(variable, { checkedNodes: [variable] });
    await flush();
    expect(tree.checked.value).toHaveLength(1);
    tree.onCheck(variable, { checkedNodes: [] });
    finish(variable);
    await flush();
    expect(panel.realtimeNodes.value).toEqual([]);
    expect(tree.checked.value).toEqual([]);
  });

  it("does not restore a right-side removal during a repeated add", async () => {
    const { panel, tree } = await workspace("client", true);
    await panel.addNodes([variable]);
    let finish!: (node: any) => void;
    jest.mocked(getOpcUaNodeCapabilities).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const addition = panel.addNodes([variable]);
    panel.removeRealtime(variable.node_id);
    await flush();
    expect(tree.checked.value).toEqual([]);
    finish(variable);
    await addition;
    await flush();
    expect(panel.realtimeNodes.value).toEqual([]);
  });

  it("restores checked state as refreshed and paged tree nodes load", async () => {
    const { panel, tree, treeApi } = await workspace("server");
    await panel.addNodes([variable]);
    tree.refresh();
    expect(tree.checked.value).toEqual([]);
    await tree.loadChildren(
      { level: 1, data: { node_id: "i=85", key: "i=85" } },
      jest.fn(),
    );
    expect(tree.checked.value[0].node_id).toBe(variable.node_id);

    tree.loadedNodes.delete(second.key);
    await panel.addNodes([second]);
    await flush();
    expect(tree.checked.value).toHaveLength(1);
    jest
      .mocked(browseOpcUaServer)
      .mockResolvedValueOnce({ nodes: [second], has_more: false } as any);
    await tree.loadMore({
      node_id: "i=85",
      parentKey: "i=85",
      key: "i=85/more/0",
      offset: 1,
    });
    expect(tree.checked.value).toHaveLength(2);
    expect(treeApi.setCheckedKeys).toHaveBeenLastCalledWith([
      variable.key,
      second.key,
    ]);
  });

  it("matches standard NodeId aliases across multiple tree paths", async () => {
    const { panel, tree, treeApi } = await workspace("server");
    panel.kind.value = "events";
    const alias = { ...source, node_id: "ns=0;i=2253", key: "another/server" };
    tree.loadedNodes.set(alias.key, alias);
    await panel.addNodes([source]);
    await flush();
    expect(treeApi.setCheckedKeys).toHaveBeenLastCalledWith([
      source.key,
      alias.key,
    ]);
    tree.onCheck(alias, { checkedNodes: [source] });
    await flush();
    expect(panel.eventNodes.value).toEqual([]);
    expect(tree.checked.value).toEqual([]);
  });
});
