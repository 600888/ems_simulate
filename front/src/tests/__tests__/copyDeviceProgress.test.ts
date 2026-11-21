/// <reference types="jest" />
/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer, nextTick, reactive } from "vue";
import {
  getActiveDeviceCopyTask,
  getDeviceCopyTask,
  startSingleDeviceCopyTask,
  startDeviceCopyTask,
  type DeviceCopyTask,
} from "@/api/channelApi";

jest.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
jest.mock("@element-plus/icons-vue", () => ({}));
jest.mock("@/api/http", () => ({
  getApiErrorMessage: (error: Error) => error.message,
}));
jest.mock("@/api/channelApi", () => ({
  getActiveDeviceCopyTask: jest.fn(),
  getDeviceCopyTask: jest.fn(),
  startSingleDeviceCopyTask: jest.fn(),
  startDeviceCopyTask: jest.fn(),
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
  "../../components/device/CopyDeviceDialog.vue",
);
const { descriptor } = parse(readFileSync(filename, "utf8"), { filename });
const script = compileScript(descriptor, { id: "copy-progress-test" });
const { outputText } = transpileModule(script.content, {
  compilerOptions: { module: ModuleKind.CommonJS, target: ScriptTarget.ES2020 },
});
const compiled = { exports: {} as any };
new Function("require", "module", "exports", outputText)(
  require,
  compiled,
  compiled.exports,
);

function task(status: DeviceCopyTask["status"] = "running"): DeviceCopyTask {
  return {
    id: "copy-job-1",
    source_channel_id: 1,
    source_name: "Source",
    status,
    total: 1,
    completed: status === "running" ? 0 : 1,
    progress: status === "running" ? 45 : 100,
    copied_count: status === "completed" ? 1 : 0,
    failed_count: 0,
    skipped_count: 0,
    warning_count: 0,
    error: null,
    items: [
      {
        index: 1,
        name: "Target",
        status: status === "running" ? "running" : "completed",
        stage: status === "running" ? "points" : "completed",
        progress: status === "running" ? 45 : 100,
        points_completed: 10,
        points_total: 25,
        message: "",
      },
    ],
  };
}

const cleanup: (() => void)[] = [];
function mountDialog() {
  const props = reactive({
    visible: false,
    channelId: 1,
    deviceName: "Source",
    deviceCode: "SOURCE",
    deviceIp: "192.168.1.1",
    devicePort: 502,
  });
  const emit = jest.fn();
  let state: any;
  const app = renderer.createApp({
    setup() {
      state = compiled.exports.default.setup(props, { expose() {}, emit });
      return () => null;
    },
  });
  app.mount({});
  state.formRef.value = {
    validate: async (callback: (valid: boolean) => unknown) => callback(true),
    clearValidate() {},
  };
  cleanup.push(() => app.unmount());
  return { state, props, emit };
}

async function flush() {
  await nextTick();
  await Promise.resolve();
  await Promise.resolve();
  await nextTick();
}

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  jest.mocked(getActiveDeviceCopyTask).mockResolvedValue(null);
  jest.mocked(getDeviceCopyTask).mockResolvedValue(task());
  jest.mocked(startSingleDeviceCopyTask).mockResolvedValue(task());
});
afterEach(() => {
  cleanup.splice(0).forEach((unmount) => unmount());
  jest.useRealTimers();
});

it("submits once, polls real point progress and retains the completion page", async () => {
  const { state, props, emit } = mountDialog();
  props.visible = true;
  await flush();
  await state.handleSubmit();
  await flush();
  expect(startSingleDeviceCopyTask).toHaveBeenCalledTimes(1);
  expect(startDeviceCopyTask).not.toHaveBeenCalled();
  expect(state.copyTask.value.items[0].points_completed).toBe(10);
  jest.mocked(getDeviceCopyTask).mockResolvedValue(task("completed"));
  await jest.advanceTimersByTimeAsync(500);
  expect(state.copyTask.value.progress).toBe(100);
  expect(state.loading.value).toBe(false);
  expect(emit.mock.calls.filter(([event]) => event === "success")).toHaveLength(
    1,
  );
  expect(emit).not.toHaveBeenCalledWith("update:visible", false);
});

it("recovers an active background copy without submitting another task", async () => {
  jest.mocked(getActiveDeviceCopyTask).mockResolvedValue(task());
  const { state, props } = mountDialog();
  props.visible = true;
  await flush();
  expect(state.copyTask.value.id).toBe("copy-job-1");
  expect(state.loading.value).toBe(true);
  await state.handleSubmit();
  expect(startSingleDeviceCopyTask).not.toHaveBeenCalled();
  state.handleClose();
  props.visible = false;
  await flush();
  jest.mocked(getDeviceCopyTask).mockResolvedValue(task("completed"));
  await jest.advanceTimersByTimeAsync(500);
  expect(state.copyTask.value.status).toBe("completed");
});

it("reconnects progress after a network failure without repeating a copy", async () => {
  const { state } = mountDialog();
  await state.handleSubmit();
  await flush();
  jest
    .mocked(getDeviceCopyTask)
    .mockRejectedValueOnce(new Error("Network unavailable"));
  await jest.advanceTimersByTimeAsync(500);
  expect(state.progressError.value).toBe("Network unavailable");
  expect(state.loading.value).toBe(true);
  jest.mocked(getDeviceCopyTask).mockResolvedValue(task("completed"));
  await state.pollCopyTask();
  expect(state.copyTask.value.status).toBe("completed");
  expect(startSingleDeviceCopyTask).toHaveBeenCalledTimes(1);
});

it("recovers server work when submission loses its response", async () => {
  jest
    .mocked(startSingleDeviceCopyTask)
    .mockRejectedValueOnce(new Error("timeout"));
  jest.mocked(getActiveDeviceCopyTask).mockResolvedValue(task());
  const { state } = mountDialog();
  await state.handleSubmit();
  await flush();
  expect(state.copyTask.value.id).toBe("copy-job-1");
  expect(state.progressError.value).toBe("");
  expect(startSingleDeviceCopyTask).toHaveBeenCalledTimes(1);
});
