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
  virtual?: boolean;
  inherited?: boolean;
  instance_override?: boolean;
  source_node_id?: string | null;
  source_kind?: string;
  template_path?: string;
  logical_node_id?: string;
  effective_fc?: string;
  cdc?: string;
  effective_model_warnings?: EffectiveInstanceTree["warnings"];
  effective_model_summary?: EffectiveInstanceTree["summary"];
  detail_loaded?: boolean;
  children_partial?: boolean;
  children?: ModelNode[];
  schema?: NodeSchema;
}

export interface EffectiveInstanceTree {
  logical_node_id: string;
  ln_type: string;
  ln_type_node_id?: string;
  resolved: boolean;
  nodes: ModelNode[];
  warnings: Array<{
    code: string;
    path: string;
    message: string;
  }>;
  summary: {
    data_objects: number;
    data_attributes: number;
    overrides: number;
  };
}

export interface LNodeTypeOption {
  node_id: string;
  id: string;
  name: string;
  lnClass: string;
  description: string;
  data_objects: number;
  data_attributes: number;
  warnings: Array<{
    code: string;
    path: string;
    message: string;
  }>;
}

export interface LNodeDoTemplateParameters {
  name_pattern: string;
  start_index: number;
  quantity: number;
  index_width: number;
  do_type_ref: string;
  expected_project_revision?: number;
}

export interface LNodeDoTemplatePreview {
  target: {
    id: string;
    name: string;
    lnClass: string;
    revision: number;
  };
  do_type: {
    id: string;
    name: string;
    cdc: string;
    description: string;
  };
  parameters: LNodeDoTemplateParameters;
  items: Array<{
    name: string;
    index: number;
    action: "CREATE" | "KEEP" | "CONFLICT";
    reason: string;
    existing_node_id: string | null;
    attributes: { type: string };
  }>;
  summary: {
    total: number;
    create: number;
    keep: number;
    conflict: number;
  };
  project_revision: number;
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
    relation_label: string;
    reference_value: string;
    source: {
      id: string;
      kind: string;
      kind_label: string;
      name: string;
      path: string;
    };
    target: {
      id: string;
      kind: string;
      kind_label: string;
      name: string;
      path: string;
    };
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

export interface DataSetMemberCandidate {
  id: string;
  reference: string;
  logical_device: string;
  logical_node: string;
  data_object: string;
  data_attribute: string;
  fc: string;
  b_type: string;
  description: string;
  group_key: string;
  selection_level: "DO" | "DA";
  is_companion: boolean;
  existing: boolean;
  existing_node_id: string | null;
  attributes: Record<string, string>;
}

export interface ExistingDataSetMember {
  node_id: string;
  name: string;
  reference: string;
  candidate_id: string | null;
  valid: boolean;
  reason: string;
  attributes: Record<string, unknown>;
  sort_order: number;
}

export interface DataSetMemberDiscovery {
  dataset: {
    id: string;
    name: string;
    path: string;
    revision: number;
  };
  candidates: DataSetMemberCandidate[];
  existing_members: ExistingDataSetMember[];
  summary: {
    candidate_count: number;
    existing_count: number;
    invalid_count: number;
  };
}
