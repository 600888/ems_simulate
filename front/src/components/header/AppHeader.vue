<template>
  <el-header class="app-header">
    <el-icon @click="setCollapse(!isCollapse)">
      <Expand v-show="sidebarDisplayCollapsed" />
      <Fold v-show="!sidebarDisplayCollapsed" />
    </el-icon>

    <el-breadcrumb separator="/">
      <el-breadcrumb-item
        v-for="(item, index) in breadList"
        :key="index"
        :to="item.path"
      >
        {{ item.meta.title }}
      </el-breadcrumb-item>
    </el-breadcrumb>
    <div class="breadcrumb-divider"></div>

    <div class="link-container">
      <!-- Language Switch -->
      <el-icon
        :size="24"
        class="icon-link clickable"
        :title="
          currentLocale === 'zh-CN'
            ? $t('layout.header.switchToEnglish')
            : $t('layout.header.switchToChinese')
        "
        @click="toggleLang"
      >
        <span class="lang-text">{{
          currentLocale === "zh-CN"
            ? $t("layout.header.en")
            : $t("layout.header.zh")
        }}</span>
      </el-icon>

      <!-- SCL Management -->
      <router-link
        to="/scl/modeling"
        class="icon-link scl-link"
        :title="t('scl.title')"
      >
        <el-icon :size="24" color="var(--text-secondary)"><Files /></el-icon>
      </router-link>

      <!-- Log Viewer Button -->
      <el-badge
        :value="logErrorCount"
        :hidden="logErrorCount <= 0"
        :max="999"
        class="log-badge"
      >
        <el-icon
          :size="24"
          class="icon-link clickable log-btn"
          :title="t('log.viewer')"
          @click="emit('open-logs')"
        >
          <Document />
        </el-icon>
      </el-badge>

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
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  Expand,
  Fold,
  Setting,
  Files,
  Document,
} from "@element-plus/icons-vue";
import { useRoute } from "vue-router";
import { isCollapse, sidebarOverlayMode } from "./isCollapse";
import { currentLocale, setLocale } from "@/composables/useAppSettings";
import { effectiveViewportWidth } from "@/composables/useAppSettings";
import type { LocaleType } from "@/i18n";

const { t, locale } = useI18n();
const emit = defineEmits(["open-settings", "open-logs"]);
const isCompactViewport = computed(() => effectiveViewportWidth.value < 1200);
const sidebarDisplayCollapsed = computed(() =>
  isCompactViewport.value ? !sidebarOverlayMode.value : isCollapse.value,
);

const props = withDefaults(
  defineProps<{
    logErrorCount?: number;
  }>(),
  {
    logErrorCount: 0,
  },
);

function toggleLang() {
  const newLocale: LocaleType =
    currentLocale.value === "zh-CN" ? "en-US" : "zh-CN";
  setLocale(newLocale);
  locale.value = newLocale;
}

const route = useRoute();
const breadList = ref<any[]>([]);

const openSettings = () => {
  emit("open-settings");
};

const setCollapse = (val: boolean) => {
  // small 断点 (< 1200px): 切换 overlay 弹出模式
  if (isCompactViewport.value) {
    sidebarOverlayMode.value = !sidebarOverlayMode.value;
    return;
  }
  isCollapse.value = val;
  localStorage.setItem("isCollapse", isCollapse.value.toString());
};

watch(isCompactViewport, (compact) => {
  if (!compact) sidebarOverlayMode.value = false;
});

// 过滤有效路由并生成面包屑
const updateBreadcrumb = () => {
  if (route.name === "device-detail" || route.path.startsWith("/device/")) {
    const deviceName = route.params.deviceName;
    breadList.value = [
      {
        path: route.path,
        meta: { title: deviceName || t("header.deviceDetail") },
      },
    ];
  } else if (route.path.startsWith("/goose")) {
    breadList.value = [
      { path: "/goose", meta: { title: t("header.gooseManagement") } },
    ];
  } else if (route.path.startsWith("/reports")) {
    breadList.value = [
      { path: "/reports", meta: { title: t("header.reportsManagement") } },
    ];
  } else if (route.path.startsWith("/files")) {
    breadList.value = [
      { path: "/files", meta: { title: t("header.filesExplorer") } },
    ];
  } else if (route.path.startsWith("/scl")) {
    const items = [{ path: "/scl/modeling", meta: { title: t("scl.title") } }];
    if (route.path.startsWith("/scl/modeling/new")) {
      items.push({
        path: route.path,
        meta: { title: t("layout.header.modelingNew") },
      });
    } else if (route.name === "model-workspace") {
      items.push({
        path: route.path,
        meta: { title: t("layout.header.modelingWorkspace") },
      });
    } else if (route.path.startsWith("/scl/manager")) {
      items.push({
        path: route.path,
        meta: { title: t("layout.header.sclFiles") },
      });
    }
    breadList.value = items;
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

  @include bp.respond-to("medium-down") {
    padding: 0 10px;

    .el-breadcrumb {
      font-size: 13px;
    }

    .link-container {
      gap: 10px;
    }
  }

  @include bp.respond-to("small") {
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

  .log-btn {
    position: relative;

    &:hover {
      .el-icon {
        color: var(--color-primary) !important;
      }
    }
  }

  .log-badge {
    :deep(.el-badge__content) {
      z-index: 1;
    }
  }

  .lang-text {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.5px;
    font-style: normal;
  }

  .goose-link,
  .scl-link {
    position: relative;

    &::after {
      content: "";
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
