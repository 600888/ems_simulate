<template>
  <el-aside class="sidebar">
    <el-scrollbar>
      <el-menu
        @select="handleMenuSelect"
        class="menu"
        :default-active="defaultActive"
        :collapse="isCollapse"
      >
        <div class="sidebar-header">
          <h1>设备列表</h1>
        </div>
        <!-- 动态生成菜单项 -->
        <el-menu-item
          v-for="route in menuRouter.getRoutes()"
          :key="route.path"
          :index="route.path"
        >
          <el-icon>
            <component :is="Warning" />
            <!-- 动态渲染图标 -->
          </el-icon>
          <span>{{ route.name }}</span>
        </el-menu-item>
      </el-menu>
    </el-scrollbar>
  </el-aside>

  <el-container>
    <el-main>
      <el-scrollbar>
        <AppHeader />
        <router-view />
      </el-scrollbar>
    </el-main>
  </el-container>
</template>

<script lang="ts" setup>
import { useRouter } from "vue-router";
import menuRouter from "@/router/index";
import { Warning } from "@element-plus/icons-vue";
import { onMounted, ref, watch } from "vue";
import { isCollapse } from "@/components/header/isCollapse";
import AppHeader from "@/components/header/AppHeader.vue";
const router = useRouter();
const defaultActive = ref("/");

onMounted(() => {
  // 获取所有路由
  const routes = menuRouter.getRoutes();
  if (routes.length > 0) {
    // 设置默认选中的路由
    defaultActive.value = routes[0].path;

    // 从 localStorage 中恢复选中的路由
    const savedActive = localStorage.getItem("activeRoute");
    if (savedActive) {
      defaultActive.value = savedActive;
    }
  }

  const isCollapseValue = localStorage.getItem("isCollapse");
  if (isCollapseValue) {
    isCollapse.value = isCollapseValue === "true";
  }

  // 确保页面加载时导航到默认路由
  router.push(defaultActive.value);
});

const handleMenuSelect = (path: string) => {
  // 保存选中的路由到 localStorage
  localStorage.setItem("activeRoute", path);
  // 导航到选中的路由
  router.push(path);
};
</script>

<style scoped>
.el-container {
  padding: 0;
  margin: 0;
  width: 100%;
  height: 100vh; /* 确保占满视口 */
}

.el-aside {
  height: 100vh;
  width: auto;
}

.el-main {
  padding: 0;
  margin: 0px 0px 0px 0px;
}

.sidebar {
  width: auto;
  height: 100vh;
  background-color: #f8f9ff;
}

.sidebar-header {
  text-align: center;
  margin-top: 10px;
  margin-bottom: 10px;
}

.sidebar-header h1 {
  margin: 0;
  font-size: 1.5em;
  color: #333;
  transition: opacity 0.1s ease;
}

/* el-scrollbar 样式调整 */
.el-scrollbar {
  height: 100%; /* 让 el-scrollbar 占满侧边栏高度 */
}

.el-scrollbar__wrap {
  overflow-x: hidden; /* 隐藏横向滚动条 */
}

.el-menu {
  width: 200px;
  border-right: none;
  position: relative;
  background-color: transparent !important;
  will-change: width;

  .is-active {
    background-color: #dbeafe !important; /* 浅蓝色 */
    color: #333 !important;
  }

  /* 折叠状态 */
  &.el-menu--collapse {
    width: 60px;
    & h1 {
      display: none;
    }
  }
}

.menu {
  width: 200px;
  border-right: none;
  background-color: transparent;
}

.borderless-button {
  border: none;
  background-color: transparent;
  font-size: 20px;
  margin-right: 5px;
  /* 其他你需要的样式 */
}
</style>
