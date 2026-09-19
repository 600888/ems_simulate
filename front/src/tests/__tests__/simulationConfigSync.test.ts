/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compileScript, parse } from "@vue/compiler-sfc";
import { ModuleKind, ScriptTarget, transpileModule } from "typescript";
import { createRenderer, nextTick, reactive } from "vue";
import { ElMessage } from "element-plus";
import { showErrorOnce } from "@/api/http";
import {
  applySimulationConfig,
  getSimulationConfig,
  startSimulation,
} from "@/api/deviceApi";
import {
  getPointInfo,
  setSinglePointSimulateMethod,
  setSinglePointStep,
  setPointSimulationRange,
} from "@/api/pointApi";
import { getPointTree } from "@/api/pointTreeApi";
import { notifySimulationConfigChanged } from "@/composables/useSimulationConfigSync";

jest.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
jest.mock("element-plus", () => ({
  ElMessage: { success: jest.fn(), warning: jest.fn() },
}));
jest.mock("@element-plus/icons-vue", () => ({}));
jest.mock("@/api/http", () => ({ showErrorOnce: jest.fn() }));
jest.mock("@/api/deviceApi", () => ({
  getSimulationConfig: jest.fn(),
  applySimulationConfig: jest.fn(),
  startSimulation: jest.fn(),
  stopSimulation: jest.fn(),
}));
jest.mock("@/api/pointTreeApi", () => ({ getPointTree: jest.fn() }));
jest.mock("@/api/pointApi", () => ({
  getPointInfo: jest.fn(),
  setSinglePointSimulateMethod: jest.fn(),
  setSinglePointStep: jest.fn(),
  setPointSimulationRange: jest.fn(),
  batchPointValues: jest.fn(),
}));

// Run the real SFC setup and Vue watchers without a browser or Element Plus DOM.
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

function mountPanel(name: string, props: Record<string, unknown>) {
  let component = components.get(name);
  if (!component) {
    const filename = resolve(__dirname, `../../components/point/${name}.vue`);
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
      require,
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
      state = component.setup(panelProps, { expose() {}, emit: jest.fn() });
      return () => null;
    },
  });
  app.mount({});
  cleanup.push(() => app.unmount());
  return { state, props: panelProps };
}

describe("simulation settings synchronization", () => {
  let config: any;
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    config = {
      point_code: "P1",
      simulate_method: "Random",
      step: 1,
      fixed_value: 0,
      enabled: true,
    };
    jest.mocked(getPointTree).mockResolvedValue([
      {
        label: "device",
        children: [
          {
            label: "YC",
            frame_type: 0,
            children: [
              {
                code: "P1",
                name: "Point",
                value: 0,
                reg_addr: "1",
                rtu_addr: 1,
                type: "YC",
              },
            ],
          },
        ],
      },
    ]);
    jest
      .mocked(getSimulationConfig)
      .mockImplementation(async () => [{ ...config }]);
    jest.mocked(getPointInfo).mockImplementation(async () => ({
      ...config,
      min_value: 0,
      max_value: 100,
    }));
    jest
      .mocked(setSinglePointSimulateMethod)
      .mockImplementation(async (_device, _code, method, fixed) => {
        config.simulate_method = method;
        if (fixed !== undefined) config.fixed_value = fixed;
        return true;
      });
    jest
      .mocked(setSinglePointStep)
      .mockImplementation(async (_device, _code, step) => {
        config.step = step;
        return true;
      });
    jest.mocked(setPointSimulationRange).mockResolvedValue(true);
    jest
      .mocked(applySimulationConfig)
      .mockImplementation(async (_device, items) => {
        config = items.length ? { ...items[0] } : { ...config, enabled: false };
        return { applied: items.map((item) => item.point_code), failed: [] };
      });
  });
  afterEach(() => {
    cleanup.splice(0).forEach((dispose) => dispose());
    jest.useRealTimers();
  });

  function dialog() {
    return mountPanel("SimulationConfigDialog", {
      modelValue: true,
      deviceName: "device",
      deviceRunning: true,
    }).state;
  }
  function point() {
    return mountPanel("PointSimulator", {
      deviceName: "device",
      pointCode: "P1",
      active: true,
    }).state;
  }

  it("reads table edits on every open, including points not selected for simulation", async () => {
    const settings = dialog();
    await settings.handleOpen();
    await settings.handleSave();
    const table = point();
    await nextTick();
    table.simulateForm.simulateMethod = "FixedValue";
    table.simulateForm.fixedValue = 42;
    table.simulateForm.step = 2;
    await table.saveSettings();
    await settings.handleOpen();
    expect(settings.selectedLeaves.value[0]).toMatchObject({
      simulate_method: "FixedValue",
      fixed_value: 42,
      step: 2,
    });

    config.enabled = false;
    await settings.handleOpen();
    expect(settings.selectedLeaves.value).toHaveLength(0);
    settings.moveAllIn();
    expect(settings.selectedLeaves.value[0].simulate_method).toBe("FixedValue");
  });

  it("saves immediately and refreshes an already expanded table panel", async () => {
    const table = point();
    const settings = dialog();
    await settings.handleOpen();
    Object.assign(settings.selectedLeaves.value[0], {
      simulate_method: "None",
      step: 3,
      fixed_value: 12,
    });
    await settings.handleSave();
    await nextTick();
    expect(table.simulateForm).toMatchObject({
      simulateMethod: "None",
      step: 3,
      fixedValue: 12,
    });
    expect(startSimulation).not.toHaveBeenCalled();
    expect(ElMessage.success).toHaveBeenCalledWith("simConfig.saveSuccess");
  });

  it("preserves an empty selection after saving and reopening", async () => {
    const settings = dialog();
    await settings.handleOpen();
    settings.moveAllOut();
    await settings.handleSave();
    expect(applySimulationConfig).toHaveBeenLastCalledWith("device", []);
    await settings.handleOpen();
    expect(settings.selectedLeaves.value).toHaveLength(0);
  });

  it("waits for the backend before reporting a successful save", async () => {
    const settings = dialog();
    await settings.handleOpen();
    let complete!: (result: { applied: string[]; failed: [] }) => void;
    jest.mocked(applySimulationConfig).mockReturnValueOnce(
      new Promise((resolve) => {
        complete = resolve;
      }),
    );
    const pending = settings.handleSave();
    expect(settings.saving.value).toBe(true);
    expect(ElMessage.success).not.toHaveBeenCalled();
    complete({ applied: ["P1"], failed: [] });
    await pending;
    expect(settings.saving.value).toBe(false);
    expect(ElMessage.success).toHaveBeenCalledWith("simConfig.saveSuccess");
  });

  it("cannot overwrite backend settings when loading the config fails", async () => {
    const settings = dialog();
    jest
      .mocked(getSimulationConfig)
      .mockRejectedValueOnce(new Error("offline"));
    const logError = jest.spyOn(console, "error").mockImplementation(() => {});
    try {
      await settings.handleOpen();
      await settings.handleSave();
      await settings.toggleSimulation();
      expect(applySimulationConfig).not.toHaveBeenCalled();
      expect(startSimulation).not.toHaveBeenCalled();
      expect(settings.configLoaded.value).toBe(false);
    } finally {
      logError.mockRestore();
    }
  });

  it("reports partial failures and does not start or report a successful save", async () => {
    const settings = dialog();
    await settings.handleOpen();
    jest.mocked(applySimulationConfig).mockResolvedValue({
      applied: [],
      failed: [{ point_code: "P1", reason: "missing" }],
    });
    await settings.handleSave();
    await settings.toggleSimulation();
    expect(showErrorOnce).toHaveBeenCalledWith(
      expect.stringContaining("P1: missing"),
    );
    expect(ElMessage.success).not.toHaveBeenCalled();
    expect(startSimulation).not.toHaveBeenCalled();
    expect(settings.saving.value).toBe(false);
  });

  it("ignores updates from other devices and refreshes inactive panels when activated", async () => {
    const panel = mountPanel("PointSimulator", {
      deviceName: "device",
      pointCode: "P1",
      active: true,
    });
    await nextTick();
    jest.mocked(getPointInfo).mockClear();
    notifySimulationConfigChanged("another-device");
    await nextTick();
    expect(getPointInfo).not.toHaveBeenCalled();
    panel.props.active = false;
    await nextTick();
    config.simulate_method = "Pulse";
    notifySimulationConfigChanged("device");
    await nextTick();
    expect(getPointInfo).not.toHaveBeenCalled();
    panel.props.active = true;
    await nextTick();
    await nextTick();
    expect(panel.state.simulateForm.simulateMethod).toBe("Pulse");
  });
});
