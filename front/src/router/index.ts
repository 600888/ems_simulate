// src/router/index.js
import { createRouter, createWebHashHistory } from 'vue-router';
import { addView, visitedViews } from '@/store/tagsView';

// 创建路由器实例
const menuRouter = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/device/:deviceName',
      name: 'device-detail', // Use a fixed name for the route config
      component: () => import('../views/Device.vue'),
      props: true, // Allow params to be passed as props if needed
    },
    {
      path: '/goose',
      name: 'goose-manager',
      component: () => import('../views/GooseView.vue'),
    },
    {
      path: '/reports',
      name: 'reports-manager',
      component: () => import('../views/ReportsView.vue'),
    },
    {
      path: '/files',
      name: 'files-explorer',
      component: () => import('../views/FilesView.vue'),
    },
    // Optional: Add a default redirect or home route if needed
    // { path: '/', redirect: '/device/some-default' } 
  ],
});

// 全局后置钩子，用于收集访问过的页面作为标签页
menuRouter.afterEach((to) => {
  // 只有设备和 GOOSE 页面有独立标签页；Reports 和 Files 是设备子页面，不单独创建标签
  if (to.path.startsWith('/device') || to.path.startsWith('/goose')) {
    // addView 内部已按 path 去重：已存在则跳过，不存在才新建
    addView(to);
  }
});

export async function setUpRoutes() {
  // Deprecated: No longer needed as we use dynamic params
  console.log('setUpRoutes is deprecated and no longer needed.');
}

export default menuRouter;