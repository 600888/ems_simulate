import { instance } from '@/api/http'
import type {
  DeleteImpact,
  ModelNode,
  ModelProject,
  ModelVersion,
  NodeSchema,
  SclArtifact,
  ValidationResult,
} from '@/types/modeling'

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

function unwrap<T>(response: { data: ApiEnvelope<T> }): T {
  return response.data.data
}

export interface CreateProjectPayload {
  name: string
  code: string
  description: string
  file_type: 'ICD' | 'CID' | 'SCD'
  standard_version: string
  namespace?: string
  ied: {
    name: string
    manufacturer: string
    type: string
    configVersion: string
    desc?: string
  }
  access_point_name: string
  logical_devices: Array<{ inst: string; desc: string }>
}

export const modelingApi = {
  async listProjects(params: { keyword?: string; status?: string; page?: number; page_size?: number }) {
    return unwrap<{ items: ModelProject[]; total: number; page: number; page_size: number }>(
      await instance.get('/api/modeling/projects', { params }),
    )
  },

  async createProject(payload: CreateProjectPayload) {
    return unwrap<{ project: ModelProject; tree: ModelNode[] }>(
      await instance.post('/api/modeling/projects', payload),
    )
  },

  async getProject(projectId: string) {
    return unwrap<ModelProject>(await instance.get(`/api/modeling/projects/${projectId}`))
  },

  async deleteProject(projectId: string) {
    return unwrap<null>(await instance.delete(`/api/modeling/projects/${projectId}`))
  },

  async getTree(projectId: string) {
    return unwrap<ModelNode[]>(await instance.get(`/api/modeling/projects/${projectId}/tree`))
  },

  async getNode(projectId: string, nodeId: string) {
    return unwrap<ModelNode>(await instance.get(`/api/modeling/projects/${projectId}/nodes/${nodeId}`))
  },

  async createNode(
    projectId: string,
    payload: { parent_id: string; kind: string; name: string; attributes: Record<string, unknown> },
  ) {
    return unwrap<ModelNode>(await instance.post(`/api/modeling/projects/${projectId}/nodes`, payload))
  },

  async updateNode(
    projectId: string,
    nodeId: string,
    payload: { name: string; attributes: Record<string, unknown>; expected_revision: number },
  ) {
    return unwrap<ModelNode>(
      await instance.patch(`/api/modeling/projects/${projectId}/nodes/${nodeId}`, payload),
    )
  },

  async getDeleteImpact(projectId: string, nodeId: string) {
    return unwrap<DeleteImpact>(
      await instance.get(`/api/modeling/projects/${projectId}/nodes/${nodeId}/delete-impact`),
    )
  },

  async deleteNode(projectId: string, nodeId: string, force = false) {
    return unwrap<{ deleted_node_id: string; deleted_count: number }>(
      await instance.delete(`/api/modeling/projects/${projectId}/nodes/${nodeId}`, { params: { force } }),
    )
  },

  async validate(projectId: string) {
    return unwrap<ValidationResult>(await instance.post(`/api/modeling/projects/${projectId}/validate`))
  },

  async getNodeSchema(kind: string) {
    return unwrap<NodeSchema>(await instance.get(`/api/modeling/node-kinds/${kind}/schema`))
  },

  async listVersions(projectId: string) {
    return unwrap<ModelVersion[]>(await instance.get(`/api/modeling/projects/${projectId}/versions`))
  },

  async createVersion(projectId: string, payload: { label: string; description: string }) {
    return unwrap<ModelVersion>(await instance.post(`/api/modeling/projects/${projectId}/versions`, payload))
  },

  async restoreVersion(projectId: string, versionId: string) {
    return unwrap<{ restored_version: ModelVersion; project_revision: number; node_count: number }>(
      await instance.post(`/api/modeling/projects/${projectId}/versions/${versionId}/restore`),
    )
  },

  async deleteVersion(projectId: string, versionId: string) {
    return unwrap<null>(await instance.delete(`/api/modeling/projects/${projectId}/versions/${versionId}`))
  },

  async previewScl(projectId: string) {
    return unwrap<SclArtifact>(await instance.get(`/api/modeling/projects/${projectId}/scl-preview`))
  },

  async downloadScl(projectId: string) {
    const response = await instance.get<string>(`/api/modeling/projects/${projectId}/scl-download`, {
      responseType: 'text',
    })
    const disposition = response.headers['content-disposition'] || ''
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'model.icd'
    return { content: response.data, filename }
  },

  async publish(projectId: string, payload: { label: string; description: string }) {
    return unwrap<{
      version: ModelVersion
      validation: ValidationResult
      artifact: { filename: string; size: number; revision: number }
    }>(await instance.post(`/api/modeling/projects/${projectId}/publish`, payload))
  },
}
