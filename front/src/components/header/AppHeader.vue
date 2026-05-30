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
      <!-- Language Switch -->
      <el-icon
        :size="24"
        class="icon-link clickable"
        :title="currentLocale === 'zh-CN' ? 'Switch to English' : '切换到中文'"
        @click="toggleLang"
      >
        <span class="lang-text">{{ currentLocale === 'zh-CN' ? 'EN' : '中' }}</span>
      </el-icon>

      <!-- GOOSE Management -->
      <router-link to="/goose" class="icon-link goose-link" :title="t('header.gooseManagement')">
        <el-icon :size="24" color="var(--text-secondary)"><Connection /></el-icon>
      </router-link>

      <!-- Settings Button -->
      <el-icon
        :size="24"
        class="icon-link clickable"
        :title="t('header.settings')"
        @click="openSettings"
      >
        <Setting />
      </el-icon>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Expand, Fold, Connection, Setting } from "@element-plus/icons-vue";
import { useRoute } from "vue-router";
import { isCollapse, sidebarOverlayMode } from "./isCollapse";
import { currentLocale, setLocale } from "@/composables/useAppSettings";
import type { LocaleType } from '@/i18n'

const { t, locale } = useI18n()
const emit = defineEmits(['open-settings'])

function toggleLang() {
  const newLocale: LocaleType = currentLocale.value === 'zh-CN' ? 'en-US' : 'zh-CN'
  setLocale(newLocale)
  locale.value = newLocale
}

const route = useRoute();
const breadList = ref<any[]>([]);

const openSettings = () => {
  emit('open-settings')
}

const setCollapse = (val: boolean) => {
  // small 断点 (< 1200px): 切换 overlay 弹出模式
  if (window.innerWidth < 1200) {
    sidebarOverlayMode.value = !sidebarOverlayMode.value;
    return;
  }
  isCollapse.value = val;
  localStorage.setItem("isCollapse", isCollapse.value.toString());
};

// 过滤有效路由并生成面包屑
const updateBreadcrumb = () => {
  if (route.name === 'device-detail' || route.path.startsWith('/device/')) {
    const deviceName = route.params.deviceName;
    breadList.value = [
      { path: route.path, meta: { title: deviceName || t('header.deviceDetail') } }
    ];
  } else if (route.path.startsWith('/goose')) {
    breadList.value = [
      { path: '/goose', meta: { title: t('header.gooseManagement') } }
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

  @include bp.respond-to('medium-down') {
    padding: 0 10px;

    .el-breadcrumb {
      font-size: 13px;
    }

    .link-container {
      gap: 10px;
    }
  }

  @include bp.respond-to('small') {
    padding: 0 8px;

    .el-breadcrumb {
      font-size: 12px;
    }
  }
  
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
    text-decoration: none;
    
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

  .clickable {
    cursor: pointer;
  }

  .lang-text {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.5px;
    font-style: normal;
  }

  .goose-link {
    position: relative;

    &::after {
      content: '';
      position: absolute;
      bottom: -2px;
      left: 50%;
      transform: translateX(-50%);
      width: 0;
      height: 2px;
      background: var(--color-primary);
      border-radius: 1px;
      transition: width 0.3s;
    }

    &:hover::after,
    &.router-link-active::after {
      width: 80%;
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
