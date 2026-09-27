/** Byte-order suffixes describe bytes on the Modbus wire. */
export const DECODE_GROUPS = [
  {
    labelKey: "decode.bit8",
    codes: ["UINT8_AB", "INT8_AB", "UINT8_BA", "INT8_BA"],
  },
  {
    labelKey: "decode.int16",
    codes: ["UINT16_AB", "INT16_AB", "UINT16_BA", "INT16_BA"],
  },
  {
    labelKey: "decode.int32",
    codes: [
      "UINT32_ABCD",
      "INT32_ABCD",
      "UINT32_BADC",
      "INT32_BADC",
      "UINT32_CDAB",
      "INT32_CDAB",
      "UINT32_DCBA",
      "INT32_DCBA",
    ],
  },
  {
    labelKey: "decode.float32",
    codes: ["FLOAT32_ABCD", "FLOAT32_BADC", "FLOAT32_CDAB", "FLOAT32_DCBA"],
  },
  {
    labelKey: "decode.int64",
    codes: [
      "UINT64_ABCDEFGH",
      "INT64_ABCDEFGH",
      "UINT64_GHEFCDAB",
      "INT64_GHEFCDAB",
    ],
  },
  {
    labelKey: "decode.double",
    codes: [
      "DOUBLE_ABCDEFGH",
      "DOUBLE_BADCFEHG",
      "DOUBLE_GHEFCDAB",
      "DOUBLE_HGFEDCBA",
    ],
  },
] as const;

/** Show the persisted code together with its value type and actual wire layout. */
export function getDecodeOptionLabel(
  code: string,
  translate: (key: string) => string,
): string {
  const [kind, order] = code.split("_");
  const orderKey = kind.endsWith("8") ? `${order}8` : order;
  return `${code} — ${translate(`decode.types.${kind}`)} · ${translate(`decode.orders.${orderKey}`)}`;
}

export const LEGACY_DECODE_CODES: Record<string, string> = {
  "0x10": "UINT8_AB",
  "0x11": "INT8_AB",
  "0x20": "UINT16_AB",
  "0x21": "INT16_AB",
  "0x22": "UINT16_AB",
  "0xB0": "UINT16_AB",
  "0xB1": "INT16_AB",
  "0xC0": "UINT16_BA",
  "0xC1": "INT16_BA",
  "0x40": "UINT32_ABCD",
  "0x41": "INT32_ABCD",
  "0x42": "FLOAT32_ABCD",
  "0x43": "UINT32_DCBA",
  "0x44": "INT32_DCBA",
  "0x45": "FLOAT32_DCBA",
  "0xD0": "UINT32_CDAB",
  "0xD1": "INT32_CDAB",
  "0xD2": "FLOAT32_CDAB",
  "0xD3": "FLOAT32_CDAB",
  "0xD4": "UINT32_CDAB",
  "0xD5": "INT32_CDAB",
  "0x60": "UINT64_ABCDEFGH",
  "0x61": "INT64_ABCDEFGH",
  "0x62": "DOUBLE_ABCDEFGH",
  "0xE0": "UINT64_GHEFCDAB",
  "0xE1": "INT64_GHEFCDAB",
  "0xE2": "DOUBLE_GHEFCDAB",
};

export function normalizeDecode(code: string): string {
  const legacyKey =
    code.startsWith("0x") || code.startsWith("0X")
      ? `0x${code.slice(2).toUpperCase()}`
      : code.toUpperCase();
  return LEGACY_DECODE_CODES[legacyKey] ?? code.toUpperCase();
}

export function getRegisterSpan(code: string): number {
  const normalized = normalizeDecode(code);
  if (normalized.startsWith("DOUBLE_") || normalized.includes("64_")) return 4;
  if (normalized.includes("32_")) return 2;
  return 1;
}
