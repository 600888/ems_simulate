import type { NodeFieldSchema } from "@/types/modeling";

type PropertyFormSnapshotSource = {
  name: string;
  attributes: Record<string, unknown>;
};

function normalizeFieldValue(field: NodeFieldSchema, value: unknown): unknown {
  if (field.component === "switch") {
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (normalized === "true" || normalized === "1") return true;
      if (normalized === "false" || normalized === "0" || normalized === "")
        return false;
    }
    return value == null ? false : value;
  }

  if (field.component === "number") {
    if (value == null || value === "") return null;
    if (typeof value === "string") {
      const normalized = Number(value);
      if (Number.isFinite(normalized)) return normalized;
    }
    return value;
  }

  return value == null ? "" : value;
}

/**
 * Build a value-semantic snapshot of the property form.
 *
 * SCL attributes arrive from XML as strings, while Element Plus normalizes
 * mounted switch/number controls to booleans and numbers. Normalizing both
 * sides here prevents simply opening the advanced tab from marking the node
 * as edited.
 */
export function createModelingFormSnapshot(
  form: PropertyFormSnapshotSource,
  fields: NodeFieldSchema[],
): string {
  const attributes = { ...form.attributes };
  for (const field of fields) {
    if (field.key === "name") continue;
    attributes[field.key] = normalizeFieldValue(field, attributes[field.key]);
  }
  const canonicalAttributes = Object.fromEntries(
    Object.entries(attributes).sort(([left], [right]) =>
      left.localeCompare(right),
    ),
  );
  return JSON.stringify({
    name: form.name,
    attributes: canonicalAttributes,
  });
}
