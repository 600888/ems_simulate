<template>
  <div class="sidebar-header" v-if="!isCollapse">
    <div class="logo-box">
      <el-icon class="logo-icon"><Cpu /></el-icon>
      <span class="logo-text">设备列表</span>
      <div class="theme-toggle-wrapper" @click.stop="toggleTheme">
        <el-icon class="theme-icon">
          <Sunny v-if="currentTheme === 'dark'" />
          <Moon v-else />
        </el-icon>
      </div>
    </div>
  </div>
  <!-- 折叠状态下的简化头部 -->
  <div class="sidebar-header-collapsed" v-else>
    <div class="logo-box-collapsed">
      <el-icon class="logo-icon"><Cpu /></el-icon>
    </div>
    <div class="theme-toggle-collapsed" @click.stop="toggleTheme">
      <el-icon class="theme-icon">
        <Sunny v-if="currentTheme === 'dark'" />
        <Moon v-else />
      </el-icon>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { Cpu, Sunny, Moon } from "@element-plus/icons-vue";
import { currentTheme, toggleTheme } from "@/utils/theme";

defineProps<{
  isCollapse: boolean;
}>();
</script>

<style lang="scss" scoped>
.sidebar-header {
  padding: 20px 16px 12px;
}

.logo-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px 18px;
  background: var(--sb-logo-bg);
  border-radius: 12px;
  box-shadow: 0 4px 15px var(--sb-logo-shadow);
  transition: all 0.3s ease;
  border: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
}

.logo-box:hover {
  transform: translateY(-2px);
}

.logo-icon {
  font-size: 22px;
  color: #fff;
}

.logo-text {
  margin: 0;
  font-size: 1.15em;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 1px;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.theme-toggle-wrapper {
  margin-left: auto;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.15);
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.theme-toggle-wrapper:hover {
  background: rgba(255, 255, 255, 0.25);
  transform: rotate(15deg);
}

.theme-icon {
  font-size: 16px;
  color: #fff;
}

/* 折叠状态下的头部样式 */
.sidebar-header-collapsed {
  padding: 16px 8px 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.logo-box-collapsed {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background: var(--sb-logo-bg);
  border-radius: 10px;
  box-shadow: 0 4px 12px var(--sb-logo-shadow);
  transition: all 0.3s ease;
  
  .logo-icon {
    font-size: 20px;
    color: #fff;
  }
}

.theme-toggle-collapsed {
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  
  &:hover {
    background: rgba(255, 255, 255, 0.2);
    transform: rotate(15deg);
  }
  
  .theme-icon {
    font-size: 16px;
    color: var(--text-secondary);
  }
}
</style>
