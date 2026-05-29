<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Setting, Brush, Iphone } from '@element-plus/icons-vue'
import { zoomLevel, setZoom, currentLocale, setLocale, ZOOM_MIN, ZOOM_MAX, ZOOM_STEP } from '@/composables/useAppSettings'
import type { LocaleType } from '@/i18n'

const { t, locale } = useI18n()

type MenuKey = 'appearance' | 'language'

const activeMenu = ref<MenuKey>('appearance')

const menuItems = computed(() => [
  { key: 'appearance' as MenuKey, icon: Brush, label: t('settings.appearance') },
  { key: 'language' as MenuKey, icon: Iphone, label: t('settings.region') },
])

const localeOptions = computed<{ value: LocaleType; label: string }[]>(() => [
  { value: 'zh-CN', label: t('settings.zh') },
  { value: 'en-US', label: t('settings.en') },
])

function handleLocaleChange(val: LocaleType) {
  setLocale(val)
  locale.value = val
}
</script>

<template>
  <div class="settings-container">
    <!-- 左侧菜单栏 -->
    <div class="settings-sidebar">
      <el-menu
        :default-active="activeMenu"
        class="settings-menu"
        @select="(key: MenuKey) => (activeMenu = key)"
      >
        <el-menu-item v-for="item in menuItems" :key="item.key" :index="item.key">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </div>

    <!-- 右侧内容区 -->
    <div class="settings-content">
      <!-- 外观设置 -->
      <div v-show="activeMenu === 'appearance'" class="settings-section">
        <h3 class="section-title">{{ t('settings.appearance') }}</h3>
        <div class="section-card">
          <div class="setting-item">
            <div class="setting-info">
              <div class="setting-label">{{ t('settings.zoom') }}</div>
              <div class="setting-desc">{{ t('settings.zoomHint') }}</div>
            </div>
            <div class="setting-control zoom-control">
              <span class="zoom-value">{{ zoomLevel }}%</span>
              <el-slider
                v-model="zoomLevel"
                :min="ZOOM_MIN"
                :max="ZOOM_MAX"
                :step="ZOOM_STEP"
                @input="setZoom"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 语言设置 -->
      <div v-show="activeMenu === 'language'" class="settings-section">
        <h3 class="section-title">{{ t('settings.region') }}</h3>
        <div class="section-card">
          <div class="setting-item">
            <div class="setting-info">
              <div class="setting-label">{{ t('settings.language') }}</div>
              <div class="setting-desc">{{ t('settings.languageHint') }}</div>
            </div>
            <div class="setting-control">
              <el-radio-group
                :model-value="currentLocale"
                @change="handleLocaleChange"
              >
                <el-radio-button
                  v-for="opt in localeOptions"
                  :key="opt.value"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </el-radio-button>
              </el-radio-group>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.settings-container {
  display: flex;
  height: 480px;
  background-color: var(--bg-main);
  border-radius: 12px;
  overflow: hidden;
}

.settings-sidebar {
  width: 200px;
  flex-shrink: 0;
  background-color: var(--panel-bg);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;

  .settings-menu {
    border-right: none;
    background: transparent;

    .el-menu-item {
      height: 40px;
      line-height: 40px;
      margin: 2px 8px;
      border-radius: 8px;
      color: var(--text-secondary);
      transition: all 0.2s;

      &:hover {
        background-color: var(--item-hover-bg);
        color: var(--text-primary);
      }

      &.is-active {
        background-color: var(--item-active-bg);
        color: var(--color-primary);
        font-weight: 500;
      }

      .el-icon {
        font-size: 18px;
      }
    }
  }
}

.settings-content {
  flex: 1;
  padding: 24px 28px;
  overflow-y: auto;
  overflow-x: hidden;
  min-width: 0;
}

.settings-section {
  max-width: 520px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 20px;
}

.section-card {
  background: var(--panel-bg);
  border: 1px solid var(--sidebar-border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--box-shadow-base);
}

.setting-item {
  display: flex;
  align-items: center;
  gap: 16px;

  &:not(:last-child) {
    padding-bottom: 16px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--sidebar-border);
  }
}

.setting-info {
  flex: 1;
  min-width: 0;
  overflow-wrap: break-word;
  word-break: break-word;
}

.setting-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.setting-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

.setting-control {
  flex: 1;
  min-width: 180px;
}

.zoom-control {
  display: flex;
  align-items: center;
  gap: 10px;

  .zoom-value {
    flex-shrink: 0;
    width: 44px;
    font-size: 14px;
    font-weight: 600;
    color: var(--color-primary);
    text-align: center;
  }

  .el-slider {
    flex: 1;
    max-width: 240px;
  }
}
</style>
