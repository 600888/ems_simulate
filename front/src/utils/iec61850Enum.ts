import type {
  IEC61850EnumDefinition,
  IEC61850EnumItem,
} from "@/api/channelApi";

export function enumOptionLabel(item: IEC61850EnumItem): string {
  return [String(item.ord), item.literal, item.desc]
    .filter(Boolean)
    .join(" · ");
}

/** Keep the raw value in row data; format only at the point of presentation. */
export function formatEnumValue(
  value: unknown,
  definition?: IEC61850EnumDefinition,
  unknownLabel = "未知枚举值",
): string {
  if (value === "" || value === null || value === undefined) return "";
  if (!definition) return String(value);
  const ordinal =
    typeof value === "number" || typeof value === "string"
      ? Number(value)
      : NaN;
  const item = definition.items.find((candidate) => candidate.ord === ordinal);
  return item ? enumOptionLabel(item) : `${unknownLabel}（${String(value)}）`;
}

export function isEnumSelection(
  value: unknown,
  definition: IEC61850EnumDefinition,
): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    definition.items.some((item) => item.ord === value)
  );
}
