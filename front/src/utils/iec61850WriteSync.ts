import type { IEC61850DoNode } from "@/api/channelApi";

export interface Iec61850ReadbackTarget {
  pointCode: string;
  fc: string;
  mmsType: string;
}

export interface Iec61850WriteResult {
  point_code: string;
  value: number | string;
}

/** Find feedback in the actual model, without reading FC=CO command attributes. */
export function resolveIec61850ReadbackTarget(
  node: IEC61850DoNode,
): Iec61850ReadbackTarget | null {
  const candidates = (node.children || []).flatMap((da) => [
    { path: da.da_path, code: da.point_code, fc: da.fc, type: da.mms_type },
    ...(da.children || []).map((bda) => ({
      path: bda.bda_path,
      code: bda.point_code,
      fc: bda.fc,
      type: bda.mms_type,
    })),
  ]);
  const valuePaths = [
    "stVal",
    "mag.f",
    "mag.i",
    "cVal.mag.f",
    "cVal.mag.i",
    "instMag.f",
    "instMag.i",
    "setMag.f",
    "setMag.i",
    "setVal",
    "actVal",
  ];
  for (const path of valuePaths) {
    const match = candidates.find(
      (item) => item.path === path && item.code && item.fc && item.fc !== "CO",
    );
    if (match) {
      return { pointCode: match.code, fc: match.fc, mmsType: match.type || "" };
    }
  }
  return null;
}

/** Keep the accepted command and measured feedback under their own point codes. */
export async function syncIec61850WriteResult(
  result: Iec61850WriteResult,
  target: Iec61850ReadbackTarget | null,
  read: (target: Iec61850ReadbackTarget) => Promise<{ value: unknown } | null>,
  update: (pointCode: string, value: unknown) => void,
): Promise<void> {
  update(result.point_code, result.value);
  if (!target || target.fc === "CO") return;
  const readback = await read(target);
  if (readback && readback.value !== null && readback.value !== undefined) {
    update(target.pointCode, readback.value);
  }
}
