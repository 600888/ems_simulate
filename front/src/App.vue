<script setup>
import Sidebar from "./views/SideBar.vue";
import AppHeader from "@/components/header/AppHeader.vue";
import { currentTheme } from "@/utils/theme";
</script>

<template>
  <div :class="`theme-wrapper theme-${currentTheme}`">
    <el-container class="app-container">
      <Sidebar />
      <el-container direction="vertical">
        <AppHeader />
        <el-main class="main-content">
          <el-scrollbar>
            <router-view />
          </el-scrollbar>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<style lang="scss">
.theme-wrapper {
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: var(--bg-main);
  transition: all 0.3s ease;
}

.app-container {
  height: 100%;
  width: 100%;
}

.main-content {
  flex: 1;
  padding: 0 !important;
  background-color: var(--bg-main);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
