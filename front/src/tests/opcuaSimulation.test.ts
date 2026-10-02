import {
  createSimulationRule,
  ruleToForm,
  serializeSimulationRule,
  SimulationRuleError,
} from "@/utils/opcuaSimulation";
import type { OpcUaVariable } from "@/api/opcuaApi";

const variable: OpcUaVariable = {
  node_id: "ns=2;s=temperature",
  browse_name: "Temperature",
  data_type: "Double",
  initial_value: 0,
  writable: true,
};

describe("OPC UA simulation configuration", () => {
  it("defaults nonnumeric nodes to fixed values and preserves false and empty strings", () => {
    for (const node of [
      { ...variable, data_type: "Boolean" as const, initial_value: false },
      { ...variable, data_type: "String" as const, initial_value: "" },
    ]) {
      const form = createSimulationRule(node);
      expect(form.kind).toBe("fixed");
      expect(serializeSimulationRule(form, node).value).toBe(
        node.initial_value,
      );
    }
  });

  it("round-trips tagged fixed values without losing Int64 precision or ByteString encoding", () => {
    for (const node of [
      {
        ...variable,
        data_type: "Int64" as const,
        initial_value: { integer: "9223372036854775807" },
      },
      {
        ...variable,
        data_type: "ByteString" as const,
        initial_value: { base64: "AAE=" },
      },
    ]) {
      const form = createSimulationRule(node);
      form.kind = "fixed";
      const saved = serializeSimulationRule(form, node);
      expect(saved.value).toEqual(node.initial_value);
      expect(serializeSimulationRule(ruleToForm(saved), node)).toEqual(saved);
      expect(saved).not.toHaveProperty("valueText");
    }
  });

  it("ignores unused fixed input for numeric waveforms", () => {
    const form = createSimulationRule(variable);
    form.valueText = "invalid JSON";
    expect(serializeSimulationRule(form, variable).kind).toBe("random");
  });

  it("rejects missing nodes, invalid ranges, invalid intervals and incompatible waveforms", () => {
    const form = createSimulationRule(variable);
    expect(() => serializeSimulationRule(form, undefined)).toThrow(
      SimulationRuleError,
    );
    expect(() =>
      serializeSimulationRule({ ...form, minimum: 101 }, variable),
    ).toThrow("simulationInvalidRange");
    for (const interval_ms of [49, 500.5, 3600001, NaN]) {
      expect(() =>
        serializeSimulationRule({ ...form, interval_ms }, variable),
      ).toThrow("simulationInvalidParameters");
    }
    expect(() =>
      serializeSimulationRule(form, { ...variable, data_type: "Boolean" }),
    ).toThrow("simulationNumericOnly");
    expect(() =>
      serializeSimulationRule(
        { ...form, maximum: 256 },
        { ...variable, data_type: "Byte" },
      ),
    ).toThrow();
    expect(() =>
      serializeSimulationRule({ ...form, maximum: Infinity }, variable),
    ).toThrow();
  });
});
