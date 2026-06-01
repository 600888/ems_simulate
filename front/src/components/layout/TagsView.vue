<template>
  <div class="tags-view-container">
    <el-scrollbar wrap-class="tags-view-wrapper">
      <router-link
        v-for="tag in visitedViews"
        :key="tag.path"
        :to="{ path: tag.path, query: tag.query }"
        class="tags-view-item"
        :class="isActive(tag) ? 'active' : ''"
        @contextmenu.prevent="openMenu(tag, $event)"
      >
        {{ tag.title }}
        <el-icon
          v-if="visitedViews.length > 1"
          class="el-icon-close"
          @click.prevent.stop="closeSelectedTag(tag)"
        >
          <Close />
        </el-icon>
      </router-link>
    </el-scrollbar>

    <!-- 右键菜单 -->
    <div
      v-show="contextMenuVisible"
      class="context-menu"
      :style="{ left: contextMenuX + 'px', top: contextMenuY + 'px' }"
      @click.stop
    >
      <div class="context-menu-item" @click="closeOthers">
        <span>关闭其他标签页</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Close } from '@element-plus/icons-vue';
import { visitedViews, delView, delOthersViews, getDeviceNameByChannelId, type TagView } from '@/store/tagsView';
import Sortable from 'sortablejs';

const route = useRoute();
const router = useRouter();

// 右键菜单状态
const contextMenuVisible = ref(false);
const contextMenuX = ref(0);
const contextMenuY = ref(0);
const contextMenuTag = ref<TagView | null>(null);

// 点击其他区域关闭菜单
const closeContextMenu = () => {
  contextMenuVisible.value = false;
};

onMounted(() => {
  initSortable();
  document.addEventListener('click', closeContextMenu);
});

const initSortable = () => {
  // `el-scrollbar` renders an inner wrapper `el-scrollbar__view` which contains the actual tag items.
  const el = document.querySelector('.tags-view-wrapper .el-scrollbar__view') as HTMLElement;
  if (!el) return;
  
  Sortable.create(el, {
    ghostClass: 'sortable-ghost',
    animation: 150,
    onEnd: (evt) => {
      const { oldIndex, newIndex } = evt;
      if (oldIndex !== undefined && newIndex !== undefined && oldIndex !== newIndex) {
        const targetRow = visitedViews.value.splice(oldIndex, 1)[0];
        visitedViews.value.splice(newIndex, 0, targetRow);
      }
    }
  });
};

const isActive = (tag: TagView) => {
  // 正常路径匹配
  if (tag.path === route.path) return true;
  // 报告/文件是设备的子页面，高亮对应的设备标签
  if ((route.path === '/reports' || route.path === '/files') && route.query.channel_id) {
    const deviceName = getDeviceNameByChannelId(Number(route.query.channel_id));
    if (deviceName) return tag.path === `/device/${deviceName}`;
  }
  return false;
};

const closeSelectedTag = async (view: TagView) => {
  const views = await delView(view);
  if (isActive(view)) {
    toLastView(views, view);
  }
};

const toLastView = (views: TagView[], view: TagView) => {
  const latestView = views.slice(-1)[0];
  if (latestView) {
    router.push(latestView.path as string);
  } else {
    // default redirect to home or somewhere safe if no views
    router.push('/');
  }
};

const openMenu = (tag: TagView, e: MouseEvent) => {
  contextMenuTag.value = tag;
  contextMenuX.value = e.clientX;
  contextMenuY.value = e.clientY;
  contextMenuVisible.value = true;
};

const closeOthers = async () => {
  if (!contextMenuTag.value) return;
  const currentTag = contextMenuTag.value;
  const currentPath = route.path;
  contextMenuVisible.value = false;
  await delOthersViews(currentTag);
  // 如果当前激活的标签被删除了，跳转到其他标签
  if (currentTag.path !== currentPath) {
    const remaining = visitedViews.value.slice(-1)[0];
    if (remaining) {
      router.push(remaining.path as string);
    } else {
      router.push('/');
    }
  }
};
</script>

<style lang="scss" scoped>
.tags-view-container {
  height: var(--tags-height);
  width: 100%;
  flex-shrink: 0; // prevent being squished by main content
  background: var(--bg-main);
  border-bottom: 1px solid var(--sidebar-border);
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.12), 0 0 3px 0 rgba(0, 0, 0, 0.04);
  z-index: 10; // ensure it is above the main scrollbar content if any shadows exist
  overflow: hidden;
  
  .tags-view-wrapper {
    .tags-view-item {
      display: inline-block;
      position: relative;
      cursor: pointer;
      height: calc(var(--tags-height) - 8px);
      line-height: calc(var(--tags-height) - 8px);
      border: 1px solid var(--sidebar-border);
      color: var(--text-primary);
      background: var(--panel-bg);
      padding: 0 8px;
      font-size: 13px;
      margin-left: 5px;
      margin-top: 4px;
      border-radius: 4px;
      text-decoration: none;

      @include bp.respond-to('medium-down') {
        font-size: 12px;
        padding: 0 6px;
      }

      @include bp.respond-to('small') {
        font-size: 11px;
        padding: 0 5px;
        margin-left: 3px;
      }
      
      &:first-of-type {
        margin-left: 15px;
      }
      
      &.active {
        background-color: var(--color-primary);
        color: #fff;
        border-color: var(--color-primary);
        
        &::before {
          content: '';
          background: #fff;
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          position: relative;
          margin-right: 2px;
        }
      }
      
      .el-icon-close {
        width: 16px;
        height: 16px;
        vertical-align: middle;
        border-radius: 50%;
        text-align: center;
        transition: all 0.3s cubic-bezier(0.645, 0.045, 0.355, 1);
        transform-origin: 100% 50%;
        margin-left: 2px;
        
        &:before {
          transform: scale(0.6);
          display: inline-block;
        }
        
        &:hover {
          background-color: #b4bccc;
          color: #fff;
        }
      }
      
      &.sortable-ghost {
        opacity: 0.3;
        background-color: var(--color-primary-light-9, #ecf5ff);
      }
    }
  }
}

.context-menu {
  position: fixed;
  z-index: 3000;
  background: var(--panel-bg, #fff);
  border: 1px solid var(--sidebar-border, #e4e7ed);
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  padding: 4px 0;
  min-width: 140px;

  .context-menu-item {
    padding: 6px 16px;
    font-size: 13px;
    color: var(--text-primary, #303133);
    cursor: pointer;
    white-space: nowrap;

    &:hover {
      background-color: var(--color-primary-light-9, #ecf5ff);
      color: var(--color-primary, #409eff);
    }
  }
}
</style>
