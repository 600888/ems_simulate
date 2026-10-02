import type { OpcUaVariable } from "@/api/opcuaApi";
import { parseOpcUaScalar } from "./opcuaValue";

export type SimulationKind = "fixed" | "random" | "sine" | "step";
export interface OpcUaSimulationRule {
  node_id: string;
  kind: SimulationKind;
  minimum: number;
  maximum: number;
  period_s: number;
  offset_s: number;
  interval_ms: number;
  step: number;
  value: unknown;
  write_policy: "pause" | "overwrite" | "reject";
  enabled: boolean;
}
export interface SimulationRuleForm extends OpcUaSimulationRule {
  valueText: string;
}

export function isNumericVariable(node: OpcUaVariable): boolean {
  return !["Boolean", "String", "DateTime", "ByteString"].includes(
    node.data_type,
  );
}

export function simulationValueText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object") {
    if ("integer" in value) return String(value.integer);
    if ("base64" in value) return String(value.base64);
    return JSON.stringify(value);
  }
  return String(value);
}

export function ruleToForm(rule: OpcUaSimulationRule): SimulationRuleForm {
  return { ...rule, valueText: simulationValueText(rule.value) };
}

export function createSimulationRule(node: OpcUaVariable): SimulationRuleForm {
  return ruleToForm({
    node_id: node.node_id,
    kind: isNumericVariable(node) ? "random" : "fixed",
    minimum: 0,
    maximum: 100,
    period_s: 10,
    offset_s: 0,
    interval_ms: 500,
    step: 1,
    value: node.initial_value,
    write_policy: "pause",
    enabled: true,
  });
}

export class SimulationRuleError extends Error {
  constructor(readonly key: string) {
    super(key);
  }
}

// Keep the request compatible with the backend's Rule model. UI fields never
// reach the API, and unused fixed-value input cannot break a waveform rule.
export function serializeSimulationRule(
  form: SimulationRuleForm,
  node: OpcUaVariable | undefined,
): OpcUaSimulationRule {
  if (!node) throw new SimulationRuleError("simulationMissingNode");
  const { valueText, ...rule } = form;
  if (
    !Number.isInteger(rule.interval_ms) ||
    rule.interval_ms < 50 ||
    rule.interval_ms > 3600000 ||
    !Number.isFinite(rule.period_s) ||
    rule.period_s <= 0 ||
    rule.period_s > 86400 ||
    !Number.isFinite(rule.offset_s) ||
    Math.abs(rule.offset_s) > 86400 ||
    !Number.isFinite(rule.step) ||
    !Number.isFinite(rule.minimum) ||
    !Number.isFinite(rule.maximum)
  )
    throw new SimulationRuleError("simulationInvalidParameters");
  if (rule.minimum > rule.maximum)
    throw new SimulationRuleError("simulationInvalidRange");
  if (rule.kind === "fixed") {
    rule.value = parseOpcUaScalar(valueText, node.data_type);
  } else {
    if (!isNumericVariable(node))
      throw new SimulationRuleError("simulationNumericOnly");
    const integer = !["Float", "Double"].includes(node.data_type);
    // The simulation engine rounds integer waveforms before writing them.
    for (const bound of [rule.minimum, rule.maximum]) {
      parseOpcUaScalar(
        String(integer ? Math.round(bound) : bound),
        node.data_type,
      );
    }
  }
  return rule;
}
