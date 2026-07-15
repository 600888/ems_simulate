import { instance } from '@/api/http'
import type {
  DeleteImpact,
  ModelNode,
  ModelProject,
  NodeSchema,
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
}
