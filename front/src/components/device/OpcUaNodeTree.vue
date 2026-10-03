<template>
  <aside class="ua-node-tree ua-section">
    <div class="ua-section-heading">
      <h3>{{ t("opcua.addressSpaceTree") }}</h3>
      <el-button text :loading="loading" @click="refresh">{{
        t("opcua.refresh")
      }}</el-button>
    </div>
    <el-input
      v-model="search"
      :placeholder="t('opcua.loadedNodeSearch')"
      clearable
    />
    <p class="ua-muted">{{ t("opcua.treeDragHint") }}</p>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <el-alert
      v-if="!running"
      type="info"
      :title="
        t(role === 'server' ? 'opcua.liveValuesStopped' : 'opcua.connectHint')
      "
      :closable="false"
    />
    <div class="tree-scroll">
      <el-tree
        v-if="running || role === 'server'"
        :key="generation"
        ref="tree"
        node-key="key"
        lazy
        :load="loadChildren"
        show-checkbox
        check-strictly
        :props="{ label: 'browse_name', isLeaf: 'leaf' }"
        :filter-node-method="filter"
        :default-expanded-keys="['i=85']"
        @check="onCheck"
      >
        <template #default="{ data }">
          <div
            class="tree-node"
            :draggable="!data.more"
            @dragstart="drag($event, data)"
            :title="data.node_id"
          >
            <span class="node-symbol">{{
              data.node_class === "Variable" ? "V" : "O"
            }}</span>
            <span class="node-name">{{ data.browse_name }}</span>
            <el-button
              v-if="data.more"
              link
              :loading="loading"
              @click.stop="loadMore(data)"
              >{{ t("opcua.nextPage") }}</el-button
            >
          </div>
        </template>
      </el-tree>
    </div>
    <el-button
      type="primary"
      plain
      :disabled="!checked.length"
      @click="emit('add', checked)"
      >{{ t("opcua.addSelectedNodes") }} ({{ checked.length }})</el-button
    >
  </aside>
</template>
<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElTree } from "element-plus";
import {
  browseOpcUaNodes,
  browseOpcUaServer,
  listOpcUaVariables,
} from "@/api/opcuaApi";
import { DRAG_MIME, encodeUaDrag, type UaSelection } from "@/utils/opcuaPubSub";
import type Node from "element-plus/es/components/tree/src/model/node";
import type { CheckedInfo } from "element-plus/es/components/tree/src/tree.type";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
  revision?: number;
}>();
const emit = defineEmits<{ add: [nodes: UaSelection[]] }>();
const { t } = useI18n();
type TreeNode = UaSelection & {
  key: string;
  leaf?: boolean;
  more?: boolean;
  parentKey?: string;
  offset?: number;
};
const tree = ref<InstanceType<typeof ElTree>>(),
  search = ref(""),
  checked = ref<TreeNode[]>([]);
const generation = ref(0),
  loading = ref(false),
  error = ref("");
function refresh() {
  generation.value++;
  checked.value = [];
  error.value = "";
}
function filter(value: string, data: Record<string, any>) {
  return (
    !value ||
    `${data.browse_name} ${data.node_id}`
      .toLowerCase()
      .includes(value.toLowerCase())
  );
}
function onCheck(node: TreeNode, selection: CheckedInfo) {
  checked.value = (selection.checkedNodes as TreeNode[]).filter((n) => !n.more);
  if (!node.more && checked.value.some((n) => n.key === node.key))
    emit("add", [node]);
}
function drag(event: DragEvent, node: TreeNode) {
  if (!event.dataTransfer || node.more) return;
  const nodes = checked.value.some((n) => n.node_id === node.node_id)
    ? checked.value
    : [node];
  event.dataTransfer.setData(DRAG_MIME, encodeUaDrag(props.channelId, nodes));
  event.dataTransfer.effectAllowed = "copy";
}
async function page(
  nodeId: string,
  parentKey: string,
  offset = 0,
): Promise<TreeNode[]> {
  const response = await (
    props.role === "server" ? browseOpcUaServer : browseOpcUaNodes
  )(props.channelId, nodeId, offset);
  const children: TreeNode[] = response.nodes.map((n) => ({
    ...n,
    key: `${parentKey}/${n.node_id}`,
    leaf: n.node_class === "Variable",
  }));
  if (response.has_more)
    children.push({
      node_id: nodeId,
      browse_name: "…",
      node_class: "",
      key: `${parentKey}/more/${offset}`,
      more: true,
      leaf: true,
      parentKey,
      offset: offset + response.nodes.length,
    });
  return children;
}
async function loadChildren(node: Node, resolve: (nodes: TreeNode[]) => void) {
  const epoch = generation.value;
  loading.value = true;
  try {
    let children: TreeNode[];
    if (node.level === 0)
      children = [
        {
          node_id: "i=85",
          key: "i=85",
          browse_name: "Objects",
          node_class: "Object",
        },
      ];
    else if (!props.running) {
      children =
        node.data.node_id === "i=85"
          ? [
              {
                node_id: "i=2253",
                key: "i=85/i=2253",
                browse_name: "Server",
                node_class: "Object",
                leaf: true,
              },
              ...(await listOpcUaVariables(props.channelId)).nodes.map((n) => ({
                ...n,
                key: `i=85/${n.node_id}`,
                node_class: "Variable",
                leaf: true,
              })),
            ]
          : [];
    } else children = await page(node.data.node_id, node.data.key);
    resolve(epoch === generation.value ? children : []);
    await nextTick();
    tree.value?.filter(search.value);
  } catch (e) {
    if (epoch === generation.value)
      error.value = e instanceof Error ? e.message : String(e);
    resolve([]);
  } finally {
    if (epoch === generation.value) loading.value = false;
  }
}
async function loadMore(data: TreeNode) {
  const epoch = generation.value;
  loading.value = true;
  try {
    const nodes = await page(data.node_id, data.parentKey!, data.offset);
    if (epoch !== generation.value) return;
    tree.value?.remove(data);
    nodes.forEach((n) => tree.value?.append(n, data.parentKey!));
    await nextTick();
    tree.value?.filter(search.value);
  } catch (e) {
    if (epoch === generation.value)
      error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (epoch === generation.value) loading.value = false;
  }
}
watch(search, (value) => tree.value?.filter(value));
watch(() => [props.channelId, props.running, props.revision], refresh);
</script>
<style scoped>
.ua-node-tree {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}
.ua-section-heading {
  margin-bottom: 0;
}
.ua-muted {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.tree-scroll {
  min-height: 330px;
  max-height: 630px;
  overflow: auto;
  flex: 1;
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  cursor: grab;
  min-width: 0;
}
.node-symbol {
  font-size: 10px;
  color: var(--ua-primary);
  background: var(--el-color-primary-light-9);
  padding: 1px 4px;
  border-radius: 3px;
}
.node-name {
  overflow: hidden;
  text-overflow: ellipsis;
}
.tree-scroll :deep(.el-tree-node__content) {
  height: 34px;
}
</style>
