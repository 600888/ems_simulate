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
    return value === true || value === 1;
  }

  if (field.component === "number") {
    if (value == null || value === "") return null;
    const normalized = Number(value);
    return Number.isFinite(normalized) ? normalized : null;
  }

  return value == null ? "" : value;
}

/**
 * Convert persisted SCL attribute strings into the value types expected by
 * Element Plus before controls mount. In particular, el-switch treats the
 * string "true" as an invalid value and emits false during setup.
 */
export function normalizeModelingFormAttributes(
  attributes: Record<string, unknown>,
  fields: NodeFieldSchema[],
): Record<string, unknown> {
  const normalized = { ...attributes };
  for (const field of fields) {
    if (field.key === "name" || !(field.key in normalized)) continue;
    normalized[field.key] = normalizeFieldValue(field, normalized[field.key]);
  }
  return normalized;
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
