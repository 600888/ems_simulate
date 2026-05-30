// src/router/index.js
import { createRouter, createWebHashHistory } from 'vue-router';
import { addView } from '@/store/tagsView';

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
  // 我们只收集设备页面或者其他需要标签页的页面
  if (to.name || to.path.startsWith('/device') || to.path.startsWith('/goose') || to.path.startsWith('/reports') || to.path.startsWith('/files')) {
    addView(to);
  }
});

export async function setUpRoutes() {
  // Deprecated: No longer needed as we use dynamic params
  console.log('setUpRoutes is deprecated and no longer needed.');
}

export default menuRouter;