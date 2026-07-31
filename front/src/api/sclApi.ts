/**
 * SCL 文件管理 API
 * IEC 61850 SCL 文件（ICD/SCD/CID）上传、解析、预览、导入、对比
 * 后端为 FastAPI RESTful 风格: GET 查询 / POST FormData / DELETE 删除
 */

import i18n from "@/i18n";
import { instance, requestApi } from "./http";
import { SCL_API } from "@/constants";
import { HTTP_TIMEOUT_LONG } from "@/constants/app";

// ===== 类型定义 =====

export interface SclFileInfo {
  filename: string;
  file_path: string;
  file_size: number;
  modified_time: string;
  extension: string;
  file_name?: string;
  file_type?: string;
  ied_name?: string;
  ied_names?: string[];
  ycCount?: number;
  yxCount?: number;
  ykCount?: number;
  ytCount?: number;
  size_display?: string;
  upload_time?: string;
  point_summary?: {
    yc: number;
    yx: number;
    yk: number;
    yt: number;
  };
}

export interface SclTreeNode {
  id: string;
  label: string;
  type:
    | "IED"
    | "AP"
    | "Server"
    | "LDevice"
    | "LN"
    | "DO"
    | "DA"
    | "DataSet"
    | "FCDA"
    | "GoCB"
    | "RCB"
    | "DataType"
    | "Communication";
  children?: SclTreeNode[];
  icon?: string;
  badge?: string;
  meta?: Record<string, any>;
}

export interface SclNodeDetail {
  path: string;
  attributes: Record<string, string>;
  children: SclChildInfo[];
}

export interface SclChildInfo {
  name: string;
  fc?: string;
  type: string;
  description?: string;
}

export interface SclPreviewData {
  file_name: string;
  ied_name: string;
  points: {
    yc: SclPointInfo[];
    yx: SclPointInfo[];
    yk: SclPointInfo[];
    yt: SclPointInfo[];
  };
  counts: {
    yc: number;
    yx: number;
    yk: number;
    yt: number;
    ds_count: number;
    go_cb_count: number;
    rcb_count: number;
  };
  validation: SclValidationItem[];
}

export interface SclPointInfo {
  code: string;
  name: string;
  ref: string;
  category: "YC" | "YX" | "YK" | "YT";
  fc: string;
  type: string;
}

export interface SclValidationItem {
  level: "info" | "warning" | "error";
  message: string;
}

export interface SclImportOptions {
  file_name: string;
  channel_id: number;
  overwrite: boolean;
  import_goose: boolean;
  goose_interface: string;
  import_reports: boolean;
}

export interface SclImportResult {
  success: boolean;
  total_points: number;
  yc: number;
  yx: number;
  yk: number;
  yt: number;
  goose_count: number;
  report_count: number;
  errors: string[];
  warnings: string[];
}

export interface SclDiffResult {
  additions: number;
  deletions: number;
  modifications: number;
  details: SclDiffItem[];
}

export interface SclDiffItem {
  path: string;
  type: "added" | "deleted" | "modified";
  left_value?: string;
  right_value?: string;
}

export interface DiscoveryProgressData {
  phase: string;
  current: number;
  total: number;
  message: string;
  discovered_lds: number;
  discovered_lns: number;
  discovered_dos: number;
  discovered_das: number;
  elapsed: number;
}

// ===== 辅助函数 =====

/** GET 请求（带 query params） */
async function getApi(
  url: string,
  params: Record<string, any> = {},
): Promise<any> {
  const response = await instance.request({ url, method: "get", params });
  return response.data;
}

/** DELETE 请求（带 query params） */
async function deleteApi(
  url: string,
  params: Record<string, any> = {},
): Promise<any> {
  const response = await instance.request({ url, method: "delete", params });
  return response.data;
}

/**
 * POST FormData 请求
 * 关键: 必须清除实例默认的 'Content-Type': 'application/json'
 * 让 axios 自动设置为 multipart/form-data + boundary
 * 文件操作使用长超时 (60s)
 */
async function postFormApi(
  url: string,
  formData: FormData,
  timeout?: number,
): Promise<any> {
  const response = await instance.request({
    url,
    method: "post",
    data: formData,
    headers: { "Content-Type": undefined },
    timeout: timeout ?? HTTP_TIMEOUT_LONG,
  });
  return response.data;
}

// ===== API 函数 =====

/** 获取 SCL 文件列表 (GET) */
export async function getSclFileList(): Promise<SclFileInfo[]> {
  const res = await getApi(SCL_API.FILE_LIST);
  return res?.data || [];
}

/** 上传 SCL 文件 (POST multipart) */
export async function uploadSclFile(formData: FormData): Promise<any> {
  return postFormApi(SCL_API.FILE_UPLOAD, formData);
}

/** 获取文件详情 (GET ?filename=) */
export async function getSclFileInfo(fileName: string): Promise<any> {
  const res = await getApi(SCL_API.FILE_DETAIL, { filename: fileName });
  return res?.data;
}

/** 获取 SCL 结构树 (GET /api/scl/browse-tree?filename=) */
export async function getSclTree(fileName: string): Promise<SclTreeNode[]> {
  const res = await getApi(SCL_API.FILE_BROWSE_TREE, { filename: fileName });
  return convertBackendTree(res?.data);
}

function convertBackendTree(tree: any): SclTreeNode[] {
  const nodes: SclTreeNode[] = [];
  if (tree?.header) {
    nodes.push({
      id: "header",
      label: `Header: ${tree.header.id}`,
      type: "DataType",
      meta: tree.header,
    });
  }
  if (!tree?.ieds) return nodes;
  for (const ied of tree.ieds) {
    const iedNode: SclTreeNode = {
      id: `ied-${ied.name}`,
      label: ied.name,
      type: "IED",
      badge: ied.desc || "",
      children: [],
    };
    for (const ap of ied.access_points || []) {
      const apNode: SclTreeNode = {
        id: `${iedNode.id}-ap-${ap.name}`,
        label: `AccessPoint ${ap.name}`,
        type: "AP",
        children: [],
      };
      for (const ld of ap.ldevices || []) {
        const ldNode: SclTreeNode = {
          id: `${apNode.id}-ld-${ld.inst}`,
          label: `LD ${ld.inst}`,
          type: "LDevice",
          badge: ld.desc || "",
          children: [],
        };
        for (const ln of ld.logical_nodes || []) {
          const lnNode: SclTreeNode = {
            id: `${ldNode.id}-${ln.ln_name || ln.ln_class}`,
            label: `${ln.ln_name || ln.ln_class}${ln.ln_class ? ` (${ln.ln_class})` : ""}`,
            type: "LN",
            badge: `DO:${ln.do_count || 0}`,
            children: [],
          };
          // 后端返回的真实 DO 名称
          if (ln.dois && ln.dois.length > 0) {
            ln.dois.forEach((doi: any, idx: number) => {
              lnNode.children!.push({
                id: `${lnNode.id}-doi-${idx}`,
                label: doi.name,
                type: "DO",
                badge: doi.desc || `DA:${doi.dai_count || 0}`,
                meta: { dai_count: doi.dai_count, desc: doi.desc },
              });
            });
          }
          if (ln.dataset_count > 0)
            lnNode.children!.push({
              id: `${lnNode.id}-datasets`,
              label: `📊 DataSets (${ln.dataset_count})`,
              type: "DataSet",
            });
          if (ln.gse_control_count > 0)
            lnNode.children!.push({
              id: `${lnNode.id}-gse`,
              label: `🎛️ GoCB (${ln.gse_control_count})`,
              type: "GoCB",
            });
          if (ln.report_control_count > 0)
            lnNode.children!.push({
              id: `${lnNode.id}-rcb`,
              label: `📋 RCB (${ln.report_control_count})`,
              type: "RCB",
            });
          ldNode.children!.push(lnNode);
        }
        apNode.children!.push(ldNode);
      }
      iedNode.children!.push(apNode);
    }
    nodes.push(iedNode);
  }
  return nodes;
}

/** 获取节点详情 — 从 detail 接口构造 */
export async function getSclNodeDetail(
  fileName: string,
  nodePath: string,
): Promise<SclNodeDetail> {
  const res = await getSclFileInfo(fileName);
  return {
    path: nodePath,
    attributes: {
      名称: nodePath.split("/").pop() || nodePath,
      文件: fileName,
      IED: res?.ied_name || "",
      测点: res?.point_counts
        ? `${res.point_counts.yc}YC / ${res.point_counts.yx}YX / ${res.point_counts.yk}YK / ${res.point_counts.yt}YT`
        : "",
      GOOSE: `${res?.gse_control_count || 0} 个`,
      Report: `${res?.report_control_count || 0} 个`,
    },
    children: [],
  };
}

/** 预览 (POST Form: filename) */
export async function previewSclFile(fileName: string): Promise<any> {
  const fd = new FormData();
  fd.append("filename", fileName);
  const res = await postFormApi(SCL_API.FILE_PARSE, fd);
  return res?.data;
}

/** 获取校验结果 (POST Form: filename) */
export async function getSclValidation(
  fileName: string,
): Promise<SclValidationItem[]> {
  const fd = new FormData();
  fd.append("filename", fileName);
  const res = await postFormApi(SCL_API.FILE_VALIDATE, fd);
  const data = res?.data;
  if (!data) return [];
  const items: SclValidationItem[] = [];
  if (data.issues)
    for (const msg of data.issues)
      items.push({ level: "warning", message: msg });
  if (items.length === 0)
    items.push({
      level: "info",
      message: i18n.global.t("scl.validationSummary", {
        errors: data.error_count,
        warnings: data.warning_count,
      }),
    });
  return items;
}

/** 导入 (POST Form) — 简化版: 优先 import-points */
export async function importSclFile(
  options: SclImportOptions,
): Promise<SclImportResult> {
  const fd = new FormData();
  fd.append("channel_id", String(options.channel_id));
  fd.append("filename", options.file_name);

  const url = options.import_goose
    ? SCL_API.FILE_IMPORT_FULL
    : SCL_API.FILE_IMPORT_POINTS;
  if (options.import_goose)
    fd.append("interface", options.goose_interface || "eth0");

  const res = await postFormApi(url, fd);
  const d = res?.data || {};
  const gooseSummary = d.goose?.summary;
  return {
    success: res?.code !== 400,
    total_points: d.total || 0,
    yc: d.yc_count || 0,
    yx: d.yx_count || 0,
    yk: d.yk_count || 0,
    yt: d.yt_count || 0,
    goose_count: gooseSummary?.gse_control_count || 0,
    report_count: (d.report_controls || []).length,
    errors: res?.code === 400 ? [res.message] : [],
    warnings: [],
  };
}

/** 删除文件 (DELETE ?filename=) */
export async function deleteSclFile(fileName: string): Promise<boolean> {
  const res = await deleteApi(SCL_API.FILE_DELETE, { filename: fileName });
  return res?.code !== 404;
}

/** 对比两个 SCL 文件 (POST Form) */
export async function diffSclFiles(
  fileA: string,
  fileB: string,
): Promise<SclDiffResult> {
  const fd = new FormData();
  fd.append("filename_a", fileA);
  fd.append("filename_b", fileB);
  const res = await postFormApi(SCL_API.FILE_DIFF, fd);
  const data = res?.data;
  if (!data)
    return { additions: 0, deletions: 0, modifications: 0, details: [] };
  return {
    additions: data.ied_names?.added?.length || 0,
    deletions: data.ied_names?.removed?.length || 0,
    modifications: 0,
    details: [
      ...(data.ied_names?.added || []).map((n: string) => ({
        path: `IED/${n}`,
        type: "added" as const,
      })),
      ...(data.ied_names?.removed || []).map((n: string) => ({
        path: `IED/${n}`,
        type: "deleted" as const,
      })),
    ],
  };
}

/** 获取 SCL 文件原始 XML 内容 */
export async function getSclFileContent(fileName: string): Promise<string> {
  const res = await getApi(SCL_API.FILE_CONTENT, { filename: fileName });
  return res || "";
}
