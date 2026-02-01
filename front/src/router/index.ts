// src/router/index.js
import { createRouter, createWebHashHistory } from 'vue-router';
import Device from '../views/Device.vue';

// 创建路由器实例
const menuRouter = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/device/:deviceName',
      name: 'device-detail', // Use a fixed name for the route config
      component: Device,
      props: true // Allow params to be passed as props if needed
    },
    // Optional: Add a default redirect or home route if needed
    // { path: '/', redirect: '/device/some-default' } 
  ],
});

export async function setUpRoutes() {
  // Deprecated: No longer needed as we use dynamic params
  console.log('setUpRoutes is deprecated and no longer needed.');
}

export default menuRouter;