import {
  enumOptionLabel,
  formatEnumValue,
  isEnumSelection,
} from "@/utils/iec61850Enum";
import type { IEC61850EnumDefinition } from "@/api/channelApi";

const definition: IEC61850EnumDefinition = {
  type_id: "VendorState",
  desc: "状态",
  items: [
    { ord: -1, literal: "invalid", desc: "无效" },
    { ord: 0, literal: "idle", desc: "空闲" },
    { ord: 20, literal: "charging", desc: "充电" },
    { ord: 99, literal: "fault", desc: "故障" },
  ],
};

describe("IEC61850 model-driven enumeration values", () => {
  it("preserves zero, negative and sparse ordinals", () => {
    expect(isEnumSelection(0, definition)).toBe(true);
    expect(isEnumSelection(-1, definition)).toBe(true);
    expect(isEnumSelection(99, definition)).toBe(true);
    expect(isEnumSelection(3, definition)).toBe(false);
    expect(isEnumSelection("20", definition)).toBe(false);
    expect(isEnumSelection(true, definition)).toBe(false);
  });
  it("formats raw read values without replacing their stored ordinal", () => {
    expect(formatEnumValue(0, definition)).toBe("0 · idle · 空闲");
    expect(formatEnumValue("20", definition)).toBe("20 · charging · 充电");
    expect(enumOptionLabel(definition.items[3])).toBe("99 · fault · 故障");
  });
  it("shows unknown read values and keeps the numeric fallback without metadata", () => {
    expect(formatEnumValue(17, definition)).toBe("未知枚举值（17）");
    expect(formatEnumValue(20)).toBe("20");
    expect(formatEnumValue("", definition)).toBe("");
    expect(formatEnumValue(null, definition)).toBe("");
    expect(formatEnumValue(false, definition)).toBe("未知枚举值（false）");
  });
});
