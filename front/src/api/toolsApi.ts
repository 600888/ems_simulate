import { requestApi } from "./http";

export interface SubnetHost {
  ip: string;
  reachable: boolean;
  latency_ms: number | null;
}

export interface SubnetScan {
  id: string;
  subnet: string;
  total: number;
  completed: number;
  reachable: number;
  unreachable: number;
  status: "running" | "completed" | "cancelled" | "failed";
  error: string | null;
  results: SubnetHost[];
}

const scanUrl = "/api/tools/subnet-scans";

export function startSubnetScan(
  subnet: string,
  timeout_ms: number,
): Promise<SubnetScan> {
  return requestApi(scanUrl, "POST", { subnet, timeout_ms });
}

export function getSubnetScan(id: string): Promise<SubnetScan> {
  return requestApi(`${scanUrl}/${encodeURIComponent(id)}`, "GET", null);
}

export function stopSubnetScan(id: string): Promise<SubnetScan> {
  return requestApi(`${scanUrl}/${encodeURIComponent(id)}`, "DELETE", null);
}
