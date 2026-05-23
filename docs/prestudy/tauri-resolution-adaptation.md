## 用户需求

将已嵌入 Tauri v2 桌面客户端的前端应用改造为响应式布局，使界面能随客户端窗口自由缩放而自适应调整。

## 产品概述

该项目为 EMS 模拟设备管理系统，前端采用 Vue 3 + Element Plus 经典后台布局（侧边栏 + 顶部导航 + 标签页 + 主内容区）。当前所有布局尺寸均为硬编码固定像素值，嵌入 Tauri 客户端后无法随窗口尺寸变化自适应。Tauri 窗口默认 1280x800，最小 960x600，支持自由拖拽调整大小。

## 核心功能

- **响应式布局骨架**：建立 SCSS 断点系统（1400px / 1200px / 960px 三档），随窗口宽度自动缩放侧边栏、头部、标签栏等布局组件尺寸
- **CSS 变量驱动缩放**：在不同断点下动态调整 `--sidebar-width`、`--header-height` 等 CSS 变量值，所有引用这些变量的组件自动响应
- **Element Plus 组件适配**：表格列宽、对话框尺寸、表单控件在窄窗口下缩小或溢出滚动，保证可用性
- **侧边栏智能折叠**：窄窗口下自动折叠侧边栏，释放主内容空间；宽窗口恢复展开
- **全局 mixin 注入**：通过 Vite SCSS `additionalData` 全局注入响应式断点 mixin，所有 `.vue` 组件可直接使用，无需手动 import

## 技术栈

- **前端框架**：Vue 3.5 + TypeScript
- **UI 组件库**：Element Plus 2.9.3（按需自动导入，unplugin-vue-components）
- **CSS 预处理器**：SCSS (sass 1.89, modern API)
- **构建工具**：Vite 5
- **桌面壳**：Tauri v2

## 实现方案

### 核心策略：断点系统 + CSS 变量联动 + 全局 Mixin 注入

采用 **断点驱动 CSS 变量** 的方式实现响应式。在 `theme-vars.scss` 中利用 `@media` 覆盖 CSS 变量值，所有布局组件读取变量即可自动响应窗口变化。同时通过 Vite 的 `additionalData` 将断点 mixin 全局注入到每个 SCSS 上下文，让任意 `.vue` 组件的 scoped style 都能直接使用 `@include respond-to()` 等 mixin，无需手动 import。

### 断点设计（基于 Tauri 最小 960px）

| 断点名称 | 宽度范围 | 侧边栏 | 头部高度 | 标签栏高度 | 适用场景 |
| --- | --- | --- | --- | --- | --- |
| `large` | >= 1400px | 230px（展开） | 48px | 34px | 大屏/全屏桌面 |
| `medium` | 1200px - 1399px | 200px（展开） | 44px | 32px | 标准桌面窗口 |
| `small` | 960px - 1199px | 64px（强制折叠） | 40px | 30px | 最小窗口/笔记本 |


### 关键设计决策

1. **small 断点强制折叠侧边栏**：Tauri 最小宽度 960px 时主内容区仅剩约 900px，侧边栏 230px 挤占过多空间，自动切换为折叠态（仅 64px 图标）。用户可通过 toggle 手动展开但此时侧边栏会 overlay 显示（z-index 提升 + 阴影遮盖），类似移动端抽屉模式。

2. **CSS 变量优于 JS 监听**：避免 `window.resize` 高频事件触发 Vue 响应式更新导致的性能问题。CSS 变量方案由浏览器原生 media query 驱动，零 JS 开销，GPU 加速。

3. **SCSS modern API 兼容**：项目已启用 `api: 'modern'`，使用 `@use` 替代 `@import`。`additionalData` 注入的字符串会在每个 SCSS 编译单元前自动拼接，需使用 `@use` 语法并确保命名空间可用。

### 性能分析

- CSS `@media` 查询由浏览器原生引擎处理，无需 JS 计算，主线程零负担
- `additionalData` 注入在每个 SCSS 文件的编译时完成，对运行时无影响，构建产物仅增加少量全局 CSS 规则（约 2KB）
- Element Plus 响应式覆盖复用其已有的 `--el-*` 变量体系，无额外 DOM 开销

## 目录结构

```
front/
├── src/
│   ├── styles/
│   │   ├── breakpoints.scss          # [NEW] 断点定义 + 响应式 mixin。定义 $breakpoint-large: 1400px, $breakpoint-medium: 1200px, $breakpoint-small: 960px 三个断点。提供 respond-to($size)、respond-between($min, $max) 等 mixin。所有 mixin 以 @content 方式注入，组件可直接嵌套使用。
│   │   ├── theme-vars.scss           # [MODIFY] 新增响应式 CSS 变量覆盖。在 :root 默认值之后，分别添加 @media (max-width: 1399px) 和 @media (max-width: 1199px) 块，覆盖 --sidebar-width、--header-height 等布局变量值。同时新增 --tags-height 变量。
│   │   └── index.scss                # [MODIFY] 新增 Element Plus 响应式全局覆盖。新增 @media 规则调整 el-dialog 在小窗口下宽度为 90vw，el-table 列宽使用百分比，el-form 在小窗口下 label 位置改为 top。
│   ├── constants/
│   │   └── app.ts                    # [MODIFY] 新增断点常量（BREAKPOINTS 对象），更新 SIDEBAR_WIDTH 为引用 CSS 变量的说明注释，新增 SIDEBAR_OVERLAY_WIDTH 常量。
│   ├── components/
│   │   ├── header/
│   │   │   └── AppHeader.vue         # [MODIFY] 头部高度已通过 var(--header-height) 引用，需确认响应式生效。面包屑文字在小窗口下缩小字号。
│   │   └── layout/
│   │       └── TagsView.vue          # [MODIFY] 标签栏高度改用 var(--tags-height) 替代硬编码 34px。标签项字号和 padding 在小窗口下缩小。
│   ├── views/
│   │   ├── App.vue                   # [MODIFY] footer 高度 32px 改为 CSS 变量 --footer-height。新增 .sidebar-overlay 类供 small 断点下侧边栏 overlay 模式使用。
│   │   ├── SideBar.vue               # [MODIFY] 侧边栏宽度引用 var(--sidebar-width)；折叠态 64px 拆分为独立 CSS 变量 --sidebar-collapsed-width。small 断点下添加 overlay 弹出模式样式（z-index 提升 + 背景遮罩）。
│   │   ├── Device.vue                # [MODIFY] 现有 768px 媒体查询更新为 Tauri 适用的断点，使用 @include respond-to(small) mixin。
│   │   └── GooseView.vue             # [MODIFY] 表格和表单在 small 断点下进行响应式适配，避免溢出。
│   └── vite.config.ts                # [MODIFY] 在 css.preprocessorOptions.scss 中添加 additionalData，全局注入 breakpoints.scss 的 @use 语句。
```

## 关键代码结构

### breakpoints.scss 核心定义

```
// 断点值
$breakpoint-small: 960px;
$breakpoint-medium: 1200px;
$breakpoint-large: 1400px;

// 响应式 mixin
@mixin respond-to($size) {
  @if $size == 'small' {
    @media (max-width: #{$breakpoint-medium - 1px}) { @content; }
  } @else if $size == 'medium' {
    @media (min-width: $breakpoint-medium) and (max-width: #{$breakpoint-large - 1px}) { @content; }
  } @else if $size == 'large' {
    @media (min-width: $breakpoint-large) { @content; }
  } @else if $size == 'medium-down' {
    @media (max-width: #{$breakpoint-large - 1px}) { @content; }
  } @else if $size == 'medium-up' {
    @media (min-width: $breakpoint-medium) { @content; }
  }
}
```

### theme-vars.scss 响应式变量覆盖核心逻辑

```
:root {
  --header-height: 48px;
  --sidebar-width: 230px;
  --sidebar-collapsed-width: 64px;
  --tags-height: 34px;
  --footer-height: 32px;
}

// medium 断点：适当缩小
@media (max-width: 1399px) {
  :root {
    --header-height: 44px;
    --sidebar-width: 200px;
    --tags-height: 32px;
    --footer-height: 28px;
  }
}

// small 断点：最紧凑
@media (max-width: 1199px) {
  :root {
    --header-height: 40px;
    --sidebar-width: 64px;   // 自动折叠
    --tags-height: 30px;
    --footer-height: 24px;
  }
}
```

### vite.config.ts additionalData 注入

```ts
css: {
  preprocessorOptions: {
    scss: {
      api: 'modern',
      additionalData: `@use "@/styles/breakpoints.scss" as bp;\n`,
    },
  },
},
```

组件中使用：`@include bp.respond-to('small') { ... }`