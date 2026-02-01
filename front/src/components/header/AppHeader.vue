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
  </el-header>
</template>

<script setup="AppHeader">
import { ref, watch } from "vue";
import { Expand, Fold } from "@element-plus/icons-vue";
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
