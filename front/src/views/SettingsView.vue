<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Brush, Iphone, User, Document, Link } from '@element-plus/icons-vue'
import { zoomLevel, setZoom, currentLocale, setLocale, ZOOM_MIN, ZOOM_MAX, ZOOM_STEP } from '@/composables/useAppSettings'
import type { LocaleType } from '@/i18n'
import { ElMessage } from 'element-plus'

const { t, locale } = useI18n()

type MenuKey = 'appearance' | 'language' | 'contact'

const activeMenu = ref<MenuKey>('appearance')

const menuItems = computed(() => [
  { key: 'appearance' as MenuKey, icon: Brush, label: t('settings.appearance') },
  { key: 'language' as MenuKey, icon: Iphone, label: t('settings.region') },
  { key: 'contact' as MenuKey, icon: User, label: t('settings.contact') },
])

const localeOptions = computed<{ value: LocaleType; label: string }[]>(() => [
  { value: 'zh-CN', label: t('settings.zh') },
  { value: 'en-US', label: t('settings.en') },
])

function handleLocaleChange(val: LocaleType) {
  setLocale(val)
  locale.value = val
}

const contactLinks = computed(() => [
  {
    name: t('settings.gitee'),
    value: 'https://gitee.com/chen-dongyu123',
    icon: 'gitee',
    color: '#C71D23',
    showValue: false,
  },
  {
    name: t('settings.github'),
    value: 'https://github.com/600888',
    icon: 'github',
    color: 'var(--text-primary)',
    showValue: false,
  },
  {
    name: t('settings.onlineDoc'),
    value: 'https://600888.github.io/ems_simulate/',
    icon: 'doc',
    color: 'var(--color-primary)',
    showValue: false,
  },
  {
    name: t('settings.wechat'),
    value: t('settings.wechatId'),
    icon: 'wechat',
    color: '#07C160',
    showValue: true,
  },
  {
    name: t('settings.qq'),
    value: t('settings.qqId'),
    icon: 'qq',
    color: '#12B7F5',
    showValue: true,
  },
])

function copyText(text: string) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '-9999px'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  try {
    ;(document as any).execCommand('copy')
    ElMessage.success(t('settings.copySuccess'))
  } catch {
    ElMessage.warning(t('settings.copyFail'))
  }
  document.body.removeChild(textarea)
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

      <!-- 联系作者 -->
      <div v-show="activeMenu === 'contact'" class="settings-section contact-section">
        <h3 class="section-title">{{ t('settings.contact') }}</h3>
        <p class="contact-hint">{{ t('settings.contactHint') }}</p>

        <div class="contact-grid">
          <div
            v-for="link in contactLinks"
            :key="link.name"
            class="contact-card"
            @click="copyText(link.value)"
          >
            <!-- Gitee SVG -->
            <svg v-if="link.icon === 'gitee'" class="contact-icon" viewBox="0 0 1024 1024" width="32" height="32">
              <path d="M512 1024C230.4 1024 0 793.6 0 512S230.4 0 512 0s512 230.4 512 512-230.4 512-512 512z m259.2-569.6H480c-12.8 0-25.6 12.8-25.6 25.6v64c0 12.8 12.8 25.6 25.6 25.6h176c12.8 0 25.6 12.8 25.6 25.6v12.8c0 41.6-35.2 76.8-76.8 76.8h-240c-12.8 0-25.6-12.8-25.6-25.6V416c0-41.6 35.2-76.8 76.8-76.8h355.2c12.8 0 25.6-12.8 25.6-25.6v-64c0-12.8-12.8-25.6-25.6-25.6H416c-105.6 0-192 86.4-192 192v256c0 105.6 86.4 192 192 192h240c105.6 0 192-86.4 192-192V518.4c0-35.2-28.8-64-64-64z" :fill="link.color"/>
            </svg>
            <!-- GitHub SVG -->
            <svg v-else-if="link.icon === 'github'" class="contact-icon" viewBox="0 0 16 16" width="32" height="32">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" :fill="link.color"/>
            </svg>
            <!-- Document icon -->
            <el-icon v-else-if="link.icon === 'doc'" :size="32" :color="link.color">
              <Document />
            </el-icon>
            <!-- WeChat SVG -->
            <svg v-else-if="link.icon === 'wechat'" class="contact-icon" viewBox="0 0 1024 1024" width="32" height="32">
              <path d="M864 448c0-158.4-161.6-288-360-288S144 289.6 144 448c0 84.8 44.8 161.6 116.8 217.6l-28.8 89.6 100.8-52.8c48 17.6 99.2 28.8 153.6 28.8 20.8 0 41.6-1.6 62.4-4.8-11.2-33.6-17.6-68.8-17.6-105.6 0-176 161.6-320 360-320 25.6 0 51.2 1.6 76.8 6.4C836.8 508.8 864 475.2 864 448zM448 384m-48 0a48 48 0 1 0 96 0 48 48 0 1 0-96 0M640 384m-48 0a48 48 0 1 0 96 0 48 48 0 1 0-96 0" fill="#07C160"/>
              <path d="M864 576c0-124.8-121.6-224-272-224s-272 99.2-272 224 121.6 224 272 224c35.2 0 68.8-4.8 100.8-14.4l80 44.8-22.4-72C792 732.8 864 656 864 576zM656 544m-36 0a36 36 0 1 0 72 0 36 36 0 1 0-72 0m-112 0m-36 0a36 36 0 1 0 72 0 36 36 0 1 0-72 0" fill="#07C160"/>
            </svg>
            <!-- QQ SVG -->
            <svg v-else-if="link.icon === 'qq'" class="contact-icon" viewBox="0 0 1024 1024" width="32" height="32">
              <path d="M512 64C266.6 64 64 212.6 64 400c0 107.4 64 201.6 160 262.4-16 48-44.8 92.8-76.8 129.6-12.8 14.4-19.2 36.8-12.8 56 6.4 19.2 22.4 32 41.6 33.6 89.6 6.4 168-28.8 224-67.2 36.8 6.4 76.8 9.6 112 9.6s75.2-3.2 112-9.6c56 38.4 134.4 73.6 224 67.2 19.2-1.6 35.2-14.4 41.6-33.6 6.4-19.2 0-41.6-12.8-56-32-36.8-60.8-81.6-76.8-129.6 96-60.8 160-155.2 160-262.4 0-187.4-202.6-336-448-336z" fill="#12B7F5"/>
            </svg>
            <div class="contact-card-info">
              <span class="contact-card-label">{{ link.name }}</span>
              <span v-if="link.showValue" class="contact-card-value">{{ link.value }}</span>
            </div>
            <el-icon class="copy-icon" :size="16"><Link /></el-icon>
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

/* 联系作者样式 */
.contact-section {
  max-width: 100%;
}

.contact-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 24px;
  line-height: 1.5;
}

.contact-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.contact-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--panel-bg);
  border: 1px solid var(--sidebar-border);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s;
  box-shadow: var(--box-shadow-base);

  &:hover {
    border-color: var(--color-primary);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  &:active {
    transform: translateY(0);
  }

  .contact-icon {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
  }
}

.contact-card-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.contact-card-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.contact-card-value {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: monospace;
  word-break: break-all;
}

.copy-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
  opacity: 1;
}
</style>
