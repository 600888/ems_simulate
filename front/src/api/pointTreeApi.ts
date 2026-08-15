/**
 * 测点树 API
 */

import { requestApi } from "./http";
import { POINT_TREE_API } from "@/constants";

export interface PointLeaf {
  code: string;
  name: string;
  value: any;
  rtu_addr: number;
  reg_addr: string;
  type: string;
}

/** 分组节点（可嵌套）。DLT645 设备下遥测按 数据标识前缀 → 结算日 分组。 */
export interface GroupNode {
  label: string;
  /** DLT645 数据标识前缀 (0-4)；非 DLT645 分组为空 */
  dlt645_prefix?: number | null;
  /** DLT645 结算日 (0=当前, 1-12=上N结算日)；无结算日分组为空 */
  dlt645_settlement?: number | null;
  children: (GroupNode | PointLeaf)[];
}

export type TreeNode = GroupNode | PointLeaf;

export interface TypeNode {
  label: string;
  children: TreeNode[];
}

export interface DeviceNode {
  label: string;
  children: TypeNode[];
}

export interface TreeResponse {
  code: number;
  message: string;
  data: DeviceNode[];
}

export async function getPointTree(deviceName?: string): Promise<DeviceNode[]> {
  try {
    return await requestApi(POINT_TREE_API.TREE, "post", {
      device_name: deviceName ?? null,
    });
  } catch (error) {
    console.error("Error fetching point tree:", error);
    throw error;
  }
}
