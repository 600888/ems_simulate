<template>
  <el-header class="app-header">
    <el-icon @click="setCollapse(!isCollapse)">
      <Expand v-show="isCollapse" />
      <Fold v-show="!isCollapse" />
    </el-icon>

    <el-breadcrumb separator="/">
      <el-breadcrumb-item v-for="(item, index) in breadList" :key="index" :to="item.path">
        {{ item.meta.title }}
      </el-breadcrumb-item>
    </el-breadcrumb>
    <div class="breadcrumb-divider"></div>
    
    <div class="link-container">
      <!-- Gitee Link -->
      <a href="https://gitee.com/chen-dongyu123" target="_blank" class="icon-link" title="Gitee 仓库">
        <svg t="1586506471804" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="2299" width="24" height="24">
          <path d="M512 1024C230.4 1024 0 793.6 0 512S230.4 0 512 0s512 230.4 512 512-230.4 512-512 512z m259.2-569.6H480c-12.8 0-25.6 12.8-25.6 25.6v64c0 12.8 12.8 25.6 25.6 25.6h176c12.8 0 25.6 12.8 25.6 25.6v12.8c0 41.6-35.2 76.8-76.8 76.8h-240c-12.8 0-25.6-12.8-25.6-25.6V416c0-41.6 35.2-76.8 76.8-76.8h355.2c12.8 0 25.6-12.8 25.6-25.6v-64c0-12.8-12.8-25.6-25.6-25.6H416c-105.6 0-192 86.4-192 192v256c0 105.6 86.4 192 192 192h240c105.6 0 192-86.4 192-192V518.4c0-35.2-28.8-64-64-64z" fill="#C71D23" p-id="2300"></path>
        </svg>
      </a>

      <!-- GitHub Link -->
      <a href="https://github.com/600888" target="_blank" class="icon-link" title="GitHub 仓库">
        <svg height="24" viewBox="0 0 16 16" version="1.1" width="24" aria-hidden="true">
          <path fill="var(--text-secondary)" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
        </svg>
      </a>

      <!-- Online Documentation Link -->
      <a href="https://600888.github.io/ems_simulate/" target="_blank" class="icon-link" title="在线文档">
        <el-icon :size="24" color="var(--text-secondary)"><Document /></el-icon>
      </a>
    </div>
  </el-header>
</template>

<script setup="AppHeader">
import { ref, watch } from "vue";
import { Expand, Fold, Document } from "@element-plus/icons-vue";
import { useRoute } from "vue-router";
import { isCollapse } from "./isCollapse";
const route = useRoute();
const breadList = ref([]);

const setCollapse = (val) => {
  isCollapse.value = val;
  localStorage.setItem("isCollapse", isCollapse.value.toString());
};

// 过滤有效路由并生成面包屑
const updateBreadcrumb = () => {
  if (route.name === 'device-detail' || route.path.startsWith('/device/')) {
    const deviceName = route.params.deviceName;
    breadList.value = [
      { path: route.path, meta: { title: deviceName || '设备详情' } }
    ];
  } else {
    breadList.value = route.matched.filter((item) => item.meta?.title);
  }
};

watch(() => route.path, updateBreadcrumb, { immediate: true });
</script>

<style lang="scss" scoped>
.app-header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  padding: 0 16px;
  background-color: var(--panel-bg);
  border-bottom: 1px solid var(--sidebar-border);
  transition: all 0.3s;
  
  .collapse-icon {
    font-size: 20px;
    margin-right: 20px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: color 0.3s;
    
    &:hover {
      color: var(--color-primary);
    }
  }

  .link-container {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .icon-link {
    display: flex;
    align-items: center;
    color: var(--text-secondary);
    transition: all 0.3s;
    
    &:hover {
      opacity: 0.8;
      
      path {
        fill: var(--color-primary);
      }
      
      .el-icon {
        color: var(--color-primary);
      }
    }
  }
}

.breadcrumb-container {
  :deep(.el-breadcrumb__inner) {
    color: var(--text-secondary) !important;
    font-weight: 500;
    transition: color 0.3s;
    
    &.is-link:hover {
      color: var(--color-primary) !important;
    }
  }
  
  :deep(.el-breadcrumb__item:last-child .el-breadcrumb__inner) {
    color: var(--text-primary) !important;
    font-weight: 600;
  }
}
</style>
