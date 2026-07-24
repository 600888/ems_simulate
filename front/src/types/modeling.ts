export interface ModelProject {
  id: string;
  name: string;
  code: string;
  description: string;
  file_type: "ICD" | "CID" | "SCD";
  standard_version: string;
  modeling_mode: string;
  status: "DRAFT" | "VALID" | "PUBLISHED" | "ARCHIVED";
  revision: number;
  validation_errors: number;
  validation_warnings: number;
  node_count: number;
  created_at: string;
  updated_at: string;
  summary?: { by_kind: Record<string, number> };
}

export interface ModelNode {
  id: string;
  project_id: string;
  parent_id: string | null;
  kind: string;
  kind_label: string;
  name: string;
  label: string;
  path?: string;
  sort_order: number;
  attributes: Record<string, unknown>;
  revision: number;
  child_count: number;
  protected: boolean;
  detail_loaded?: boolean;
  children?: ModelNode[];
  schema?: NodeSchema;
}

export interface NodeFieldSchema {
  key: string;
  label: string;
  component: "input" | "textarea" | "number" | "switch" | "select";
  required?: boolean;
  options?: string[];
}

export interface NodeSchema {
  kind: string;
  label: string;
  fields: NodeFieldSchema[];
  allowed_children: Array<{ kind: string; label: string }>;
  protected: boolean;
}

export interface DeleteImpact {
  node: ModelNode;
  subtree_count: number;
  descendant_count: number;
  inbound_references: Array<{
    id: string;
    source_node_id: string;
    target_node_id: string;
    relation_type: string;
  }>;
  outbound_reference_count: number;
  protected: boolean;
  can_delete: boolean;
  blocking_reason: string;
}

export interface ValidationIssue {
  level: "ERROR" | "WARNING";
  rule_code: string;
  node_id: string | null;
  path: string;
  field: string;
  message: string;
}

export interface ValidationResult {
  passed: boolean;
  error_count: number;
  warning_count: number;
  issues: ValidationIssue[];
  validated_revision: number;
}

export interface ModelVersion {
  id: string;
  project_id: string;
  version_number: number;
  label: string;
  description: string;
  status: "SNAPSHOT" | "PUBLISHED";
  source_revision: number;
  created_at: string;
}

export interface SclArtifact {
  xml: string;
  filename: string;
  size: number;
  revision: number;
  status: ModelProject["status"];
}
