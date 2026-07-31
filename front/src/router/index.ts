// src/router/index.js
import { createRouter, createWebHashHistory } from "vue-router";
import { addView } from "@/store/tagsView";

// 创建路由器实例
const menuRouter = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/device/:deviceName",
      name: "device-detail", // Use a fixed name for the route config
      component: () => import("../views/Device.vue"),
      props: true, // Allow params to be passed as props if needed
    },
    {
      path: "/goose",
      name: "goose-manager",
      component: () => import("../views/GooseView.vue"),
    },
    {
      path: "/reports",
      name: "reports-manager",
      component: () => import("../views/ReportsView.vue"),
    },
    {
      path: "/files",
      name: "files-explorer",
      component: () => import("../views/FilesView.vue"),
    },
    {
      path: "/message-view/:deviceName",
      name: "message-view",
      component: () => import("../views/MessageView.vue"),
      meta: { standalone: true },
    },
    // SCL 文件管理
    {
      path: "/scl",
      redirect: "/scl/modeling",
    },
    {
      path: "/scl/modeling",
      name: "model-projects",
      component: () => import("../views/modeling/ModelProjectListView.vue"),
      meta: { title: "layout.header.iec61850Modeling" },
    },
    {
      path: "/scl/modeling/new",
      name: "model-create",
      component: () => import("../views/modeling/ModelCreateWizardView.vue"),
      meta: { title: "layout.header.modelingNew" },
    },
    {
      path: "/scl/modeling/:projectId",
      name: "model-workspace",
      component: () => import("../views/modeling/ModelWorkspaceView.vue"),
      props: true,
      meta: { title: "modeling.workspace.defaultTitle" },
    },
    {
      path: "/scl/manager",
      name: "scl-manager",
      component: () => import("../views/SclView.vue"),
    },
    {
      path: "/scl/preview/:fileName",
      name: "scl-preview",
      component: () => import("../components/scl/SclPreview.vue"),
    },
    {
      path: "/scl/import",
      name: "scl-import",
      component: () => import("../components/scl/SclImportWizard.vue"),
    },
    {
      path: "/scl/diff",
      name: "scl-diff",
      component: () => import("../components/scl/SclDiffViewer.vue"),
    },
    {
      path: "/scl/viewer/:fileName",
      name: "scl-xml-viewer",
      component: () => import("../components/scl/SclXmlViewer.vue"),
    },
    // Optional: Add a default redirect or home route if needed
    // { path: '/', redirect: '/device/some-default' }
  ],
});

// 全局后置钩子，用于收集访问过的页面作为标签页
menuRouter.afterEach((to) => {
  // GOOSE/Reports/Files 都属于具体设备，复用设备标签；仅设备和 SCL 页面创建独立标签。
  if (!to.path.startsWith("/device") && !to.path.startsWith("/scl")) return;

  // addView 内部已按 path 去重：存在则更新，不存在则新增
  // 页面刷新时 visitedViews 从 localStorage 恢复，addView 会找到已有标签并更新，不会重复创建
  addView(to);
});

export async function setUpRoutes() {
  // Deprecated: No longer needed as we use dynamic params
  console.log("setUpRoutes is deprecated and no longer needed.");
}

export default menuRouter;
