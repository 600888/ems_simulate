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
  breadList.value = route.matched.filter((item) => item.meta?.title);
};

// 初始加载和路由变化时更新
watch(() => route.path, updateBreadcrumb, { immediate: true });
</script>

<style lang="scss" scoped>
.el-header {
  display: flex;
  margin: 0px 0px 0px 0px;
  align-items: center;
  box-shadow: 0 1px 0 0 #dcdfe6;
  .el-icon {
    margin-right: 10px;
  }
}

.app-header {
  //居中
  height: 40px;
  display: flex;
  position: relative;
}

.breadcrumb-divider {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 0.1px;
  background-color: #e4e7ed;
}
</style>
