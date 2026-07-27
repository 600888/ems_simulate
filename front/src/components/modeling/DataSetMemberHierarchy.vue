<template>
  <div ref="containerRef" v-loading="loading" class="dataset-hierarchy">
    <div class="hierarchy-columns">
      <span>{{ $t("modeling.datasetMemberHierarchy.header") }}</span>
      <span>{{ $t("modeling.datasetMemberHierarchy.type") }}</span>
      <span>FC</span>
      <span>{{ $t("modeling.datasetMemberHierarchy.status") }}</span>
    </div>
    <el-tree-v2
      :data="treeData"
      :props="treeProps"
      :height="treeHeight"
      :item-size="40"
      :default-expanded-keys="defaultExpandedKeys"
      :expand-on-click-node="false"
      highlight-current
      @node-click="handleNodeClick"
    >
      <template #default="{ data }">
        <div
          class="hierarchy-row"
          :class="[`hierarchy-${data.type}`, { leaf: data.member }]"
          :title="data.reference || data.label"
        >
          <div class="hierarchy-name">
            <span class="hierarchy-kind">{{ kindCode(data.type) }}</span>
            <div>
              <strong>{{ data.label }}</strong>
              <small v-if="data.reference">{{ data.reference }}</small>
            </div>
          </div>
          <span class="hierarchy-type">{{
            data.member
              ? data.member.attributes.daName
                ? $t("modeling.datasetMemberHierarchy.daExact")
                : $t("modeling.datasetMemberHierarchy.doGroup")
              : groupTypeLabel(data.type)
          }}</span>
          <el-tag
            v-if="data.member"
            size="small"
            effect="plain"
            :type="fcTagType(String(data.member.attributes.fc || ''))"
          >
            {{ data.member.attributes.fc || "—" }}
          </el-tag>
          <span v-else></span>
          <span class="hierarchy-status" :class="{ group: !data.member }">
            <i></i
            >{{
              data.member
                ? $t("modeling.datasetMemberHierarchy.active")
                : $t("modeling.datasetMemberHierarchy.itemCount", {
                    count: data.leafCount || 0,
                  })
            }}
          </span>
        </div>
      </template>
    </el-tree-v2>
    <el-empty
      v-if="!loading && !treeData.length"
      :image-size="64"
      :description="$t('modeling.datasetMemberHierarchy.noMembers')"
    />
  </div>
</template>

<script setup lang="ts">
import {
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
} from "vue";
import { useI18n } from "vue-i18n";
import type { ModelNode } from "@/types/modeling";

interface HierarchyNode {
  id: string;
  label: string;
  type: "ld" | "ln" | "do" | "da";
  reference?: string;
  leafCount?: number;
  member?: ModelNode;
  children?: HierarchyNode[];
}

const props = defineProps<{ members: ModelNode[] }>();
const emit = defineEmits<{ select: [member: ModelNode] }>();

const { t } = useI18n();

const containerRef = ref<HTMLElement>();
const treeHeight = ref(320);
const loading = ref(false);
const treeData = shallowRef<HierarchyNode[]>([]);
const defaultExpandedKeys = shallowRef<string[]>([]);
const treeProps = { children: "children", label: "label", value: "id" };
let resizeObserver: ResizeObserver | undefined;
let buildWorker: Worker | undefined;
let buildRequest = 0;

watch(
  () => props.members,
  () => void rebuildHierarchy(),
  { immediate: true },
);

onMounted(() => {
  resizeObserver = new ResizeObserver(updateHeight);
  if (containerRef.value) resizeObserver.observe(containerRef.value);
  updateHeight();
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  buildWorker?.terminate();
});

function updateHeight() {
  const height = containerRef.value?.clientHeight || 0;
  treeHeight.value = Math.max(160, height - 39);
}

async function rebuildHierarchy() {
  const requestId = ++buildRequest;
  loading.value = true;
  try {
    const result = await buildHierarchyOffMainThread(props.members);
    if (requestId !== buildRequest) return;
    treeData.value = result;
    const first = result[0];
    defaultExpandedKeys.value = [
      first?.id,
      first?.children?.[0]?.id,
      first?.children?.[0]?.children?.[0]?.id,
    ].filter((id): id is string => Boolean(id));
    await nextTick();
    updateHeight();
  } finally {
    if (requestId === buildRequest) loading.value = false;
  }
}

function buildHierarchyOffMainThread(members: ModelNode[]) {
  if (typeof Worker === "undefined") {
    return Promise.resolve(buildHierarchy(members));
  }
  buildWorker?.terminate();
  const source = `
    self.onmessage = ({ data }) => {
      const { members, labels } = data;
      const roots = new Map();
      const logicalNodes = new Map();
      const dataObjects = new Map();
      for (const member of members) {
        if (member.kind !== "FCDA") continue;
        const attrs = member.attributes || {};
        const ld = String(attrs.ldInst || labels.currentLD);
        const ln = [attrs.prefix || "", attrs.lnClass || "", attrs.lnInst || ""].join("") || labels.currentLN;
        const doName = String(attrs.doName || labels.doNotSet);
        const daName = String(attrs.daName || labels.doLevelRef);
        let ldNode = roots.get(ld);
        if (!ldNode) {
          ldNode = { id: "ds-ld:" + ld, label: ld, type: "ld", leafCount: 0, children: [] };
          roots.set(ld, ldNode);
        }
        const lnId = ldNode.id + "/ln:" + ln;
        let lnNode = logicalNodes.get(lnId);
        if (!lnNode) {
          lnNode = { id: lnId, label: ln, type: "ln", leafCount: 0, children: [] };
          logicalNodes.set(lnId, lnNode);
          ldNode.children.push(lnNode);
        }
        const doSegments = doName.split(".").filter(Boolean);
        const groupSegments = attrs.daName ? doSegments : doSegments.slice(0, -1);
        let parent = lnNode;
        let doPath = "";
        for (const segment of groupSegments) {
          doPath = doPath ? doPath + "." + segment : segment;
          const doId = lnId + "/do:" + doPath;
          let doNode = dataObjects.get(doId);
          if (!doNode) {
            doNode = { id: doId, label: segment, type: "do", leafCount: 0, children: [] };
            dataObjects.set(doId, doNode);
            parent.children.push(doNode);
          }
          parent = doNode;
        }
        const reference = ld + "/" + ln + "." + doName + (attrs.daName ? "." + daName : "");
        parent.children.push({
          id: member.id,
          label: attrs.daName ? daName : (doSegments[doSegments.length - 1] || doName),
          type: attrs.daName ? "da" : "do",
          reference,
          leafCount: 1,
          member,
        });
        ldNode.leafCount += 1;
        lnNode.leafCount += 1;
        let currentPath = "";
        for (const segment of groupSegments) {
          currentPath = currentPath ? currentPath + "." + segment : segment;
          const node = dataObjects.get(lnId + "/do:" + currentPath);
          if (node) node.leafCount += 1;
        }
      }
      self.postMessage(Array.from(roots.values()));
    };
  `;
  return new Promise<HierarchyNode[]>((resolve, reject) => {
    const url = URL.createObjectURL(
      new Blob([source], { type: "text/javascript" }),
    );
    const worker = new Worker(url);
    buildWorker = worker;
    const cleanup = () => {
      worker.terminate();
      if (buildWorker === worker) buildWorker = undefined;
      URL.revokeObjectURL(url);
    };
    worker.onmessage = ({ data }) => {
      cleanup();
      resolve(data);
    };
    worker.onerror = (event) => {
      cleanup();
      reject(new Error(t("common.requestFailed")));
    };
    worker.postMessage({
      members,
      labels: {
        currentLD: t("modeling.datasetMemberHierarchy.currentLD"),
        currentLN: t("modeling.datasetMemberHierarchy.currentLN"),
        doNotSet: t("modeling.datasetMemberHierarchy.doNotSet"),
        doLevelRef: t("modeling.datasetMemberHierarchy.doLevelRef"),
      },
    });
  });
}

function buildHierarchy(members: ModelNode[]): HierarchyNode[] {
  const roots = new Map<string, HierarchyNode>();
  const logicalNodes = new Map<string, HierarchyNode>();
  const dataObjects = new Map<string, HierarchyNode>();
  const currentLD = t("modeling.datasetMemberHierarchy.currentLD");
  const currentLN = t("modeling.datasetMemberHierarchy.currentLN");
  const doNotSet = t("modeling.datasetMemberHierarchy.doNotSet");
  const doLevelRef = t("modeling.datasetMemberHierarchy.doLevelRef");
  for (const member of members) {
    if (member.kind !== "FCDA") continue;
    const attributes = member.attributes;
    const ld = String(attributes.ldInst || currentLD);
    const ln =
      ["prefix", "lnClass", "lnInst"]
        .map((key) => String(attributes[key] || ""))
        .join("") || currentLN;
    const doName = String(attributes.doName || doNotSet);
    const daName = String(attributes.daName || doLevelRef);
    let ldNode = roots.get(ld);
    if (!ldNode) {
      ldNode = {
        id: `ds-ld:${ld}`,
        label: ld,
        type: "ld",
        leafCount: 0,
        children: [],
      };
      roots.set(ld, ldNode);
    }
    const lnId = `${ldNode.id}/ln:${ln}`;
    let lnNode = logicalNodes.get(lnId);
    if (!lnNode) {
      lnNode = {
        id: lnId,
        label: ln,
        type: "ln",
        leafCount: 0,
        children: [],
      };
      logicalNodes.set(lnId, lnNode);
      ldNode.children!.push(lnNode);
    }
    const doSegments = doName.split(".").filter(Boolean);
    const groupSegments = attributes.daName
      ? doSegments
      : doSegments.slice(0, -1);
    let parent = lnNode;
    let doPath = "";
    for (const segment of groupSegments) {
      doPath = doPath ? `${doPath}.${segment}` : segment;
      const doId = `${lnId}/do:${doPath}`;
      let doNode = dataObjects.get(doId);
      if (!doNode) {
        doNode = {
          id: doId,
          label: segment,
          type: "do",
          leafCount: 0,
          children: [],
        };
        dataObjects.set(doId, doNode);
        parent.children!.push(doNode);
      }
      parent = doNode;
    }
    const reference = `${ld}/${ln}.${doName}${
      attributes.daName ? `.${daName}` : ""
    }`;
    parent.children!.push({
      id: member.id,
      label: attributes.daName
        ? daName
        : doSegments[doSegments.length - 1] || doName,
      type: attributes.daName ? "da" : "do",
      reference,
      leafCount: 1,
      member,
    });
    ldNode.leafCount = (ldNode.leafCount || 0) + 1;
    lnNode.leafCount = (lnNode.leafCount || 0) + 1;
    let currentPath = "";
    for (const segment of groupSegments) {
      currentPath = currentPath ? `${currentPath}.${segment}` : segment;
      const node = dataObjects.get(`${lnId}/do:${currentPath}`);
      if (node) node.leafCount = (node.leafCount || 0) + 1;
    }
  }
  return Array.from(roots.values());
}

function handleNodeClick(data: HierarchyNode) {
  if (data.member) emit("select", data.member);
}

function kindCode(type: HierarchyNode["type"]) {
  return type.toUpperCase();
}

function groupTypeLabel(type: HierarchyNode["type"]) {
  return { ld: "LDevice", ln: "Logical Node", do: "Data Object", da: "FCDA" }[
    type
  ];
}

function fcTagType(fc: string): "primary" | "success" | "danger" | "info" {
  if (fc === "ST") return "success";
  if (fc === "CO") return "danger";
  if (fc === "MX") return "primary";
  return "info";
}
</script>

<style scoped>
.dataset-hierarchy {
  position: relative;
  height: 100%;
  min-height: 180px;
  overflow: hidden;
  background: var(--panel-bg);
}
.hierarchy-columns {
  height: 38px;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 116px 56px 76px;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
  background: var(--bg-subtle);
  font-size: 11px;
  font-weight: 600;
  box-sizing: border-box;
}
.dataset-hierarchy :deep(.el-tree-v2) {
  padding: 7px 8px 14px;
  background: var(--panel-bg);
  box-sizing: border-box;
}
.dataset-hierarchy :deep(.el-tree-node__content) {
  height: 40px;
  margin: 1px 0;
  border: 1px solid transparent;
  border-radius: 7px;
}
.dataset-hierarchy :deep(.el-tree-node__content:hover) {
  border-color: #dbeafe;
  background: var(--bg-subtle);
}
.dataset-hierarchy :deep(.el-tree-node.is-current .el-tree-node__content) {
  border-color: #bfdbfe;
  background: #eff6ff;
}
.hierarchy-row {
  min-width: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 116px 56px 76px;
  align-items: center;
  gap: 8px;
  padding-right: 10px;
}
.hierarchy-name {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.hierarchy-name > div {
  min-width: 0;
}
.hierarchy-name strong,
.hierarchy-name small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hierarchy-name strong {
  color: var(--text-primary);
  font-size: 12px;
}
.hierarchy-name small {
  margin-top: 3px;
  color: var(--text-secondary);
  font:
    9px "Geist Mono",
    monospace;
}
.hierarchy-kind {
  display: grid;
  place-items: center;
  width: 28px;
  height: 23px;
  flex: 0 0 28px;
  border: 1px solid #dbeafe;
  border-radius: 5px;
  color: #2563eb;
  background: #eff6ff;
  font:
    700 8px "Geist Mono",
    monospace;
}
.hierarchy-ln .hierarchy-kind {
  border-color: #ddd6fe;
  color: #7c3aed;
  background: #f5f3ff;
}
.hierarchy-do .hierarchy-kind {
  border-color: #fed7aa;
  color: #c2410c;
  background: #fff7ed;
}
.hierarchy-da .hierarchy-kind {
  border-color: #ccfbf1;
  color: #0f766e;
  background: #f0fdfa;
}
.hierarchy-type {
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
}
.hierarchy-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #15803d;
  font-size: 10px;
}
.hierarchy-status i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
}
.hierarchy-status.group {
  color: var(--text-secondary);
}
.hierarchy-status.group i {
  background: #94a3b8;
}
</style>
