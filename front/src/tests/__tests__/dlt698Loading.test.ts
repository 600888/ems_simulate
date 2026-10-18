/// <reference types="node" />
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer, nextTick, reactive } from "vue";
import { dlt698Api } from "@/api/dlt698Api";
import { defaultDlt698Config } from "@/utils/dlt698";

jest.mock("vue-i18n", () => ({
  useI18n: () => ({ locale: { value: "en-US" } }),
}));
jest.mock("@/api/http", () => ({
  getApiErrorMessage: (error: Error) => error.message,
}));
jest.mock("@/api/dlt698Api", () => ({
  dlt698Api: {
    status: jest.fn(),
    config: jest.fn(),
    points: jest.fn(),
    read: jest.fn(),
    operation: jest.fn(),
  },
}));

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
const filename = resolve(
  __dirname,
  "../../components/device/dlt698/Dlt698Panel.vue",
);
const { descriptor } = parse(readFileSync(filename, "utf8"), { filename });
const script = compileScript(descriptor, { id: "Dlt698Panel" });
const { outputText } = transpileModule(script.content, {
  compilerOptions: { module: ModuleKind.CommonJS, target: ScriptTarget.ES2020 },
});
const componentModule = { exports: {} as any };
new Function("require", "module", "exports", outputText)(
  (id: string) =>
    id.endsWith(".vue")
      ? {}
      : require(id.startsWith(".") ? resolve(dirname(filename), id) : id),
  componentModule,
  componentModule.exports,
);
const cleanup: (() => void)[] = [];
function mount() {
  const props = reactive({
    channelId: 3,
    deviceName: "meter",
    role: "client",
    running: true,
  });
  let state: any;
  const app = renderer.createApp({
    setup() {
      state = componentModule.exports.default.setup(props, {
        expose() {},
        emit() {},
      });
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
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const point = {
  code: "frequency",
  oad: "200F0200",
  data_type: "UInt16",
  initial_value: { type: "UInt16", value: "5000" },
};
beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(dlt698Api.status).mockResolvedValue({
    available: true,
    state: "associated",
    sessions: [],
    security_backend: false,
    features: { get: { supported: true }, set: { supported: true } },
  });
  jest.mocked(dlt698Api.config).mockResolvedValue(defaultDlt698Config());
  jest.mocked(dlt698Api.points).mockResolvedValue([point] as any);
});
afterEach(() => cleanup.splice(0).forEach((dispose) => dispose()));

test.each(["point", "batch", "operation"] as const)(
  "%s read owns its loading state even when there is just one target",
  async (source) => {
    const { state } = mount();
    await flush();
    const pending = deferred<any[]>();
    jest.mocked(dlt698Api.read).mockReturnValueOnce(pending.promise);
    const request = state.readPoints([point], source);
    expect(state.busy.value).toBe(true);
    expect(state.busyKind.value).toBe(`read-${source}`);
    expect(state.busyPointCode.value).toBe(
      source === "batch" ? "" : point.code,
    );
    await state.readPoints([point], "batch");
    expect(dlt698Api.read).toHaveBeenCalledTimes(1);
    expect(state.busyKind.value).toBe(`read-${source}`);
    pending.resolve([]);
    await request;
    expect(state.busy.value).toBe(false);
    expect(state.busyKind.value).toBe("");
    expect(state.busyPointCode.value).toBe("");
  },
);

test("a failed single read clears its loading state and retains the error", async () => {
  const { state } = mount();
  await flush();
  jest.mocked(dlt698Api.read).mockRejectedValueOnce(new Error("Read failed"));
  await state.readPoints([point], "point");
  expect(state.busy.value).toBe(false);
  expect(state.busyPointCode.value).toBe("");
  expect(state.workspaceError.value).toBe("Read failed");
});

test("inline SET owns only the edited point's saving state", async () => {
  const { state } = mount();
  await flush();
  const pending = deferred<any[]>();
  jest.mocked(dlt698Api.operation).mockReturnValueOnce(pending.promise);
  const request = state.setInlineValue(point, point.initial_value);
  expect(state.busyKind.value).toBe("point-value");
  expect(state.busyPointCode.value).toBe(point.code);
  pending.resolve([{ kind: "dar", dar: 0 }]);
  await request;
  expect(state.busyPointCode.value).toBe("");
});

test("a previous channel's completed read cannot clear the current channel's loading state", async () => {
  const { state, props } = mount();
  await flush();
  const old = deferred<any[]>(),
    current = deferred<any[]>();
  jest
    .mocked(dlt698Api.read)
    .mockReturnValueOnce(old.promise)
    .mockReturnValueOnce(current.promise);
  const previous = state.readPoints([point], "point");
  props.channelId = 4;
  await flush();
  const request = state.readPoints([point], "batch");
  old.resolve([]);
  await previous;
  expect(state.busyKind.value).toBe("read-batch");
  current.resolve([]);
  await request;
  expect(state.busy.value).toBe(false);
});
