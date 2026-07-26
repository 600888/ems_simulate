import {
  createModelingFormSnapshot,
  normalizeModelingFormAttributes,
} from "@/utils/modelingFormSnapshot";
import type { NodeFieldSchema } from "@/types/modeling";

const fields: NodeFieldSchema[] = [
  { key: "name", label: "名称", component: "input" },
  { key: "modify", label: "允许修改", component: "switch" },
  { key: "max", label: "最大数量", component: "number" },
  { key: "desc", label: "描述", component: "input" },
];

describe("modeling property form snapshot", () => {
  it("treats imported XML values and mounted control values as equivalent", () => {
    const imported = createModelingFormSnapshot(
      {
        name: "ConfDataSet",
        attributes: { modify: "false", max: "34" },
      },
      fields,
    );
    const mounted = createModelingFormSnapshot(
      {
        name: "ConfDataSet",
        attributes: { modify: false, max: 34, desc: "" },
      },
      fields,
    );

    expect(mounted).toBe(imported);
  });

  it("normalizes true-like XML switch values without hiding real edits", () => {
    const imported = createModelingFormSnapshot(
      { name: "Report", attributes: { modify: "true" } },
      fields,
    );
    const unchanged = createModelingFormSnapshot(
      { name: "Report", attributes: { modify: true } },
      fields,
    );
    const changed = createModelingFormSnapshot(
      { name: "Report", attributes: { modify: false } },
      fields,
    );

    expect(unchanged).toBe(imported);
    expect(changed).not.toBe(imported);
  });

  it("normalizes imported values before Element Plus controls mount", () => {
    const attributes = normalizeModelingFormAttributes(
      {
        modify: "true",
        max: "34",
        desc: null,
        vendorExtension: "preserved",
      },
      fields,
    );

    expect(attributes).toEqual({
      modify: true,
      max: 34,
      desc: "",
      vendorExtension: "preserved",
    });
  });

  it("does not mutate the form while filling missing control defaults", () => {
    const attributes: Record<string, unknown> = {};

    createModelingFormSnapshot({ name: "P1", attributes }, fields);

    expect(attributes).toEqual({});
  });
});
