<script setup>
import Sidebar from "./views/SideBar.vue";
import AppHeader from "@/components/header/AppHeader.vue";
import TagsView from "@/components/layout/TagsView.vue";
import { currentTheme } from "@/utils/theme";
import { sidebarOverlayMode, closeSidebarOverlay } from "@/components/header/isCollapse";
import { isTauri, onCloseRequested } from "@/utils/tauri";
import { ref, onMounted } from "vue";

const isClosing = ref(false);

onMounted(async () => {
  if (isTauri()) {
    await onCloseRequested(() => {
      isClosing.value = true;
    });
  }
});
</script>

<template>
  <div :class="`theme-wrapper theme-${currentTheme}`">
    <!-- 关闭动画覆盖层 -->
    <Transition name="close-fade">
      <div v-if="isClosing" class="closing-overlay">
        <div class="closing-content">
          <div class="closing-spinner"></div>
          <div class="closing-text">正在关闭...</div>
        </div>
      </div>
    </Transition>
    <el-container class="app-container">
      <Sidebar />
      <!-- 侧边栏 overlay 遮罩 (small 断点下展开时显示) -->
      <div
        class="sidebar-overlay"
        :class="{ active: sidebarOverlayMode }"
        @click="closeSidebarOverlay"
      ></div>
      <el-container direction="vertical">
        <AppHeader />
        <!-- 标签页 -->
        <TagsView />
        <el-main class="main-content">
          <el-scrollbar view-class="app-scrollbar-view">
            <div class="app-view-container">
              <router-view v-slot="{ Component, route }">
                <keep-alive>
                  <component :is="Component" :key="route.fullPath" />
                </keep-alive>
              </router-view>
            </div>
            <!-- 全局底部版权 -->
            <footer class="app-footer">
              Copyright © 2026 CDY
            </footer>
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
  position: relative;
}

.main-content {
  flex: 1;
  padding: 0 !important;
  background-color: var(--bg-main);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 修复内容不足时 footer 上浮的问题 */
.app-scrollbar-view {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.app-view-container {
  flex: 1;
}

.app-footer {
  height: var(--footer-height);
  line-height: var(--footer-height);
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
  opacity: 0.6;
  background-color: var(--bg-main);
  flex-shrink: 0;
  margin-top: auto;
}

/* small 断点下侧边栏 overlay 遮罩 */
.sidebar-overlay {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.35);
  z-index: 998;
  opacity: 0;
  transition: opacity 0.3s ease;
  pointer-events: none;

  &.active {
    display: block;
    opacity: 1;
    pointer-events: auto;
  }
}

/* 关闭动画 */
.closing-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.closing-content {
  text-align: center;
}

.closing-spinner {
  display: inline-block;
  width: 36px;
  height: 36px;
  border: 3px solid rgba(255, 255, 255, 0.15);
  border-top-color: #4fc3f7;
  border-radius: 50%;
  animation: closing-spin 0.7s linear infinite;
  margin-bottom: 16px;
}

.closing-text {
  color: #ccc;
  font-size: 14px;
  letter-spacing: 1px;
}

@keyframes closing-spin {
  to { transform: rotate(360deg); }
}

.close-fade-enter-active {
  animation: close-fade-in 0.4s ease forwards;
}

@keyframes close-fade-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
</style>
