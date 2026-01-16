export interface PointLimit {
  minValueLimit: number;
  maxValueLimit: number;
}

export enum PointType {
  YC = 0,
  YX = 1,
  YK = 2,
  YT = 3,
}

export const PointTypeMap = {
  "遥测": PointType.YC,
  "遥信": PointType.YX,
  "遥控": PointType.YK,
  "遥调": PointType.YT,
} as const;

export function getPointType(
  chineseName: string,
  defaultValue: PointType = PointType.YC
): PointType {
  return PointTypeMap[chineseName as keyof typeof PointTypeMap] ?? defaultValue;
}