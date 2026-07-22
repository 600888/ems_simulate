import { instance } from "@/api/http";
import type {
  DeleteImpact,
  ModelNode,
  ModelProject,
  ModelVersion,
  NodeSchema,
  SclArtifact,
  ValidationResult,
} from "@/types/modeling";

interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
}

function unwrap<T>(response: { data: ApiEnvelope<T> }): T {
  return response.data.data;
}

const multipartConfig = { headers: { "Content-Type": undefined } };

export interface CreateProjectPayload {
  name: string;
  code: string;
  description: string;
  file_type: "ICD" | "CID" | "SCD";
  standard_version: string;
  namespace?: string;
  ied: {
    name: string;
    manufacturer: string;
    type: string;
    configVersion: string;
    desc?: string;
  };
  access_point_name: string;
  logical_devices: Array<{ inst: string; desc: string }>;
  profiles: string[];
}

export interface ModelingProfile {
  id: string;
  version: string;
  name: string;
  description: string;
  category: "core" | "service" | "domain";
  dependencies: string[];
  default: boolean;
}

export interface ImportPreview {
  project: {
    name: string;
    code: string;
    file_type: string;
    standard_version: string;
    ied_name: string;
  };
  summary: {
    node_count: number;
    by_kind: Record<string, number>;
    extension_count: number;
  };
  warnings: Array<{ code: string; message: string }>;
}

export interface FileVariantCapability {
  file_type: "ICD" | "CID" | "SCD" | "IID" | "SED";
  status: "SUPPORTED" | "PREVIEW_ONLY" | "NOT_SUPPORTED";
  publishable: boolean;
  description: string;
}

export interface ArtifactMetadata {
  kind: "SCL" | "CFG" | "CSV";
  filename: string;
  media_type: string;
  size: number;
  sha256: string;
}

export interface ModelingJob<T = unknown> {
  id: string;
  operation: string;
  status:
    "QUEUED" | "RUNNING" | "CANCELLING" | "CANCELLED" | "COMPLETED" | "FAILED";
  phase: string;
  progress: number;
  message: string;
  input_size: number;
  result: T | null;
  error: string;
}

export interface CdcTemplateAttribute {
  name: string;
  bType: string;
  fc: string;
  type?: string;
  dchg?: boolean;
  qchg?: boolean;
}

export interface CdcTemplate {
  id: string;
  name: string;
  description: string;
  mode: "COMMON" | "CDC";
  cdc?: string;
  attributes: CdcTemplateAttribute[];
}

export const modelingApi = {
  async listProfiles() {
    return unwrap<ModelingProfile[]>(
      await instance.get("/api/modeling/profiles"),
    );
  },

  async listFileVariants() {
    return unwrap<FileVariantCapability[]>(
      await instance.get("/api/modeling/file-variants"),
    );
  },

  async listCdcTemplates() {
    return unwrap<CdcTemplate[]>(
      await instance.get("/api/modeling/cdc-templates"),
    );
  },

  async listProjects(params: {
    keyword?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }) {
    return unwrap<{
      items: ModelProject[];
      total: number;
      page: number;
      page_size: number;
    }>(await instance.get("/api/modeling/projects", { params }));
  },

  async createProject(payload: CreateProjectPayload) {
    return unwrap<{ project: ModelProject; tree: ModelNode[] }>(
      await instance.post("/api/modeling/projects", payload),
    );
  },

  async previewImport(file: File) {
    const data = new FormData();
    data.append("file", file);
    return unwrap<ImportPreview>(
      await instance.post(
        "/api/modeling/projects/import-preview",
        data,
        multipartConfig,
      ),
    );
  },

  async startImportPreviewJob(file: File) {
    const data = new FormData();
    data.append("file", file);
    return unwrap<ModelingJob<ImportPreview>>(
      await instance.post(
        "/api/modeling/jobs/import-preview",
        data,
        multipartConfig,
      ),
    );
  },

  async getJob<T = unknown>(jobId: string) {
    return unwrap<ModelingJob<T>>(
      await instance.get(`/api/modeling/jobs/${jobId}`),
    );
  },

  async cancelJob(jobId: string) {
    return unwrap<ModelingJob>(
      await instance.delete(`/api/modeling/jobs/${jobId}`),
    );
  },

  async importProject(file: File, code: string, name: string) {
    const data = new FormData();
    data.append("file", file);
    data.append("code", code);
    data.append("name", name);
    return unwrap<{
      project: ModelProject;
      tree: ModelNode[];
      summary: ImportPreview["summary"];
      warnings: ImportPreview["warnings"];
    }>(
      await instance.post(
        "/api/modeling/projects/import",
        data,
        multipartConfig,
      ),
    );
  },

  async getProject(projectId: string) {
    return unwrap<ModelProject>(
      await instance.get(`/api/modeling/projects/${projectId}`),
    );
  },

  async deleteProject(projectId: string) {
    return unwrap<null>(
      await instance.delete(`/api/modeling/projects/${projectId}`),
    );
  },

  async getTree(projectId: string) {
    return unwrap<ModelNode[]>(
      await instance.get(`/api/modeling/projects/${projectId}/tree`),
    );
  },

  async getNode(projectId: string, nodeId: string) {
    return unwrap<ModelNode>(
      await instance.get(`/api/modeling/projects/${projectId}/nodes/${nodeId}`),
    );
  },

  async createNode(
    projectId: string,
    payload: {
      parent_id: string;
      kind: string;
      name: string;
      attributes: Record<string, unknown>;
    },
  ) {
    return unwrap<ModelNode>(
      await instance.post(`/api/modeling/projects/${projectId}/nodes`, payload),
    );
  },

  async updateNode(
    projectId: string,
    nodeId: string,
    payload: {
      name: string;
      attributes: Record<string, unknown>;
      expected_revision: number;
    },
  ) {
    return unwrap<ModelNode>(
      await instance.patch(
        `/api/modeling/projects/${projectId}/nodes/${nodeId}`,
        payload,
      ),
    );
  },

  async applyCdcTemplate(
    projectId: string,
    nodeId: string,
    templateId: string,
  ) {
    return unwrap<{
      template_id: string;
      do_type_id: string;
      cdc: string;
      primary_fc: string;
      created: Array<{ kind: string; name: string }>;
      preserved: string[];
      conflicts: Array<{
        name: string;
        fields: Record<string, { current: unknown; template: unknown }>;
      }>;
      changed: boolean;
      project_revision: number;
    }>(
      await instance.post(
        `/api/modeling/projects/${projectId}/nodes/${nodeId}/apply-cdc-template`,
        {
          template_id: templateId,
        },
      ),
    );
  },

  async getDeleteImpact(projectId: string, nodeId: string) {
    return unwrap<DeleteImpact>(
      await instance.get(
        `/api/modeling/projects/${projectId}/nodes/${nodeId}/delete-impact`,
      ),
    );
  },

  async deleteNode(projectId: string, nodeId: string, force = false) {
    return unwrap<{ deleted_node_id: string; deleted_count: number }>(
      await instance.delete(
        `/api/modeling/projects/${projectId}/nodes/${nodeId}`,
        { params: { force } },
      ),
    );
  },

  async validate(projectId: string) {
    return unwrap<ValidationResult>(
      await instance.post(`/api/modeling/projects/${projectId}/validate`),
    );
  },

  async getNodeSchema(kind: string) {
    return unwrap<NodeSchema>(
      await instance.get(`/api/modeling/node-kinds/${kind}/schema`),
    );
  },

  async listVersions(projectId: string) {
    return unwrap<ModelVersion[]>(
      await instance.get(`/api/modeling/projects/${projectId}/versions`),
    );
  },

  async createVersion(
    projectId: string,
    payload: { label: string; description: string },
  ) {
    return unwrap<ModelVersion>(
      await instance.post(
        `/api/modeling/projects/${projectId}/versions`,
        payload,
      ),
    );
  },

  async restoreVersion(projectId: string, versionId: string) {
    return unwrap<{
      restored_version: ModelVersion;
      project_revision: number;
      node_count: number;
    }>(
      await instance.post(
        `/api/modeling/projects/${projectId}/versions/${versionId}/restore`,
      ),
    );
  },

  async deleteVersion(projectId: string, versionId: string) {
    return unwrap<null>(
      await instance.delete(
        `/api/modeling/projects/${projectId}/versions/${versionId}`,
      ),
    );
  },

  async previewScl(projectId: string) {
    return unwrap<SclArtifact>(
      await instance.get(`/api/modeling/projects/${projectId}/scl-preview`),
    );
  },

  async downloadScl(projectId: string) {
    const response = await instance.get<string>(
      `/api/modeling/projects/${projectId}/scl-download`,
      {
        responseType: "text",
      },
    );
    const disposition = response.headers["content-disposition"] || "";
    const filename =
      disposition.match(/filename="?([^";]+)"?/i)?.[1] || "model.icd";
    return { content: response.data, filename };
  },

  async previewArtifacts(projectId: string) {
    return unwrap<{
      filename: string;
      size: number;
      revision: number;
      manifest: Record<string, unknown>;
      artifacts: ArtifactMetadata[];
    }>(await instance.get(`/api/modeling/projects/${projectId}/artifacts`));
  },

  async downloadArtifacts(projectId: string) {
    const response = await instance.get<Blob>(
      `/api/modeling/projects/${projectId}/artifacts-download`,
      {
        responseType: "blob",
      },
    );
    const disposition = response.headers["content-disposition"] || "";
    const filename =
      disposition.match(/filename="?([^";]+)"?/i)?.[1] || "model-artifacts.zip";
    return { content: response.data, filename };
  },

  async publish(
    projectId: string,
    payload: { label: string; description: string },
  ) {
    return unwrap<{
      version: ModelVersion;
      validation: ValidationResult;
      artifact: { filename: string; size: number; revision: number };
    }>(
      await instance.post(
        `/api/modeling/projects/${projectId}/publish`,
        payload,
      ),
    );
  },
};
