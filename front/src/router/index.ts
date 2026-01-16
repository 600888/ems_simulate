// src/router/index.js
import { createRouter, createWebHashHistory, createWebHistory } from 'vue-router';
import { getDeviceList } from "@/api/deviceApi";
import Device from '../views/Device.vue';

// 创建路由器实例
const menuRouter = createRouter({
  history: createWebHashHistory(),
  routes: [],
});
// 标志变量，用于记录 setUpRoutes 是否已经被调用
let routesSetup = false;
// 确保 setUpRoutes 只调用一次
if (!routesSetup) {
  await setUpRoutes();
}
// 动态添加路由的函数
export async function setUpRoutes() {
  // 如果已经调用过，直接返回
  if (routesSetup) {
    return;
  }

  try {
    const deviceList = await getDeviceList();
    // 将动态路由添加到路由器实例中
    for (const deviceName of deviceList) {
      const route = {
        path: `/device/${deviceName}`,
        name: deviceName,
        meta: {
          title: deviceName
        },
        component: () => import('../views/Device.vue')
      };
      menuRouter.addRoute(route);
    }
    routesSetup = true;
  } catch (error) {
    console.error('Error adding dynamic routes:', error);
  }
}

export default menuRouter;