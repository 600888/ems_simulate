import { defineConfig } from 'vitepress'

export default defineConfig({
    // 站点基础配置
    title: 'EMS Simulate',
    description: '能源管理系统模拟器 - 项目文档',

    // 配置浏览器标签页图标
    head: [
        ['link', { rel: 'icon', href: '/ems_simulate/img/m.ico' }]
    ],

    // GitHub Pages 部署路径
    base: '/ems_simulate/',

    // 主题配置
    themeConfig: {
        logo: '/img/m.ico',

        // 导航栏
        nav: [
            { text: '首页', link: '/' },
            { text: '快速开始', link: '/guide/install/getting-started' },
            { text: 'API 参考', link: '/api/overview' },
            { text: '更新日志', link: '/changelog/' },
            { text: 'GitHub', link: 'https://github.com/600888/ems_simulate' }
        ],

        // 侧边栏
        sidebar: {
            '/guide/': [
                {
                    text: '关于项目',
                    collapsed: false,
                    items: [
                        { text: '项目介绍', link: '/guide/about/project-introduction' }
                    ]
                },
                {
                    text: '安装部署',
                    collapsed: false,
                    items: [
                        { text: '快速开始', link: '/guide/install/getting-started' },
                        { text: '安装指南', link: '/guide/install/installation' },
                        { text: '配置说明', link: '/guide/install/configuration' },
                        { text: 'Debian 打包与部署', link: '/guide/install/packaging_deb' },
                    ]
                },
                {
                    text: '设备模块',
                    collapsed: false,
                    items: [
                        { text: '协议支持', link: '/guide/device/protocols' },
                        { text: '设备管理', link: '/guide/device/device-management' },
                        { text: '从机管理', link: '/guide/device/slave-management' },
                        { text: '报文查看', link: '/guide/device/packet-view' }
                    ]
                },
                {
                    text: '测点模块',
                    collapsed: false,
                    items: [
                        { text: '测点类型', link: '/guide/point/point-types' },
                        { text: '测点增删改查', link: '/guide/point/crud' },
                        { text: '测点模拟', link: '/guide/point/simulation' },
                        { text: '测点映射', link: '/guide/point/mapping' },
                        { text: '公式使用', link: '/guide/point/formula' },
                        { text: '寄存器解析', link: '/guide/point/register-parsing' },
                        { text: '变化回溯', link: '/guide/point/change-tracking' }
                    ]
                }
                // {
                //     text: '操作手册',
                //     collapsed: false,
                //     items: [
                //         { text: '用户使用手册', link: '/guide/manual/user-manual' }
                //     ]
                // }
            ],
            '/api/': [
                {
                    text: 'API 参考',
                    collapsed: false,
                    items: [
                        { text: '概述', link: '/api/overview' },
                        { text: '设备管理', link: '/api/device' },
                        { text: '测点操作', link: '/api/points' }
                    ]
                }
            ],
            '/changelog/': [
                {
                    text: '更新日志',
                    collapsed: false,
                    items: [
                        { text: '总览', link: '/changelog/' }
                    ]
                },
                {
                    text: '功能模块变更',
                    collapsed: false,
                    items: [
                        { text: 'IEC104 全 ASDU 类型支持', link: '/changelog/01-iec104-asdu-type-support' },
                        { text: 'Web API 层重构', link: '/changelog/02-api-refactoring' },
                        { text: 'Ruff 代码质量工具引入', link: '/changelog/03-ruff-introduction-plan' }
                    ]
                },
                {
                    text: 'IEC 61850',
                    collapsed: true,
                    items: [
                        { text: 'GOOSE 功能支持', link: '/changelog/iec61850/01-goose-support' },
                        { text: '模块化重构计划', link: '/changelog/iec61850/02-iec61850-refactoring-plan' },
                        { text: 'Reports 报告功能', link: '/changelog/iec61850/03-iec61850-reports-support' },
                        { text: 'SCL 文件模块', link: '/changelog/iec61850/04-iec61850-scl-file-module' },
                        { text: '文件下载服务模块', link: '/changelog/iec61850/05-iec61850-file-download-module' },
                        { text: 'GOOSE 模块插件化重构', link: '/changelog/iec61850/06-goose-plugin-refactoring' },
                        { text: 'SCL 模块重构实施', link: '/changelog/iec61850/07-iec61850-scl-refactoring-implementation' },
                        { text: '模型导出优化方案', link: '/changelog/iec61850/08-iec61850-model-export-optimization' },
                        { text: '统一模型架构重构', link: '/changelog/iec61850/09-iec61850-unified-model-refactoring' },
                        { text: '前端 UI 设计', link: '/changelog/iec61850/10-iec61850-frontend-ui-design' },
                        { text: '测点注册表精简优化', link: '/changelog/iec61850/11-iec61850-point-registry-optimization' },
                        { text: '元数据按需读取', link: '/changelog/iec61850/12-iec61850-metadata-reader' },
                        { text: '模型发现性能优化', link: '/changelog/iec61850/13-iec61850-discovery-performance-optimization' },
                        { text: 'ICD 导出器修复', link: '/changelog/iec61850/14-iec61850-icd-exporter-fix' }
                    ]
                },
                {
                    text: '软件优化',
                    collapsed: false,
                    items: [
                        { text: 'MSIX 后端启动修复', link: '/changelog/optimization/msix-backend-startup-fix' },
                        { text: '消除应用启动黑框', link: '/changelog/optimization/startup-black-screen-elimination' }
                    ]
                }
            ]
        },

        // 社交链接
        socialLinks: [
            { icon: 'github', link: 'https://github.com/600888/ems_simulate' }
        ],

        // 页脚
        footer: {
            message: 'Released under the Apache 2.0 License.',
            copyright: 'Copyright © 2026 CDY'
        },

        // 搜索
        search: {
            provider: 'local'
        },

        // 编辑链接
        editLink: {
            pattern: 'https://github.com/600888/ems_simulate/edit/main/docs/:path',
            text: '在 GitHub 上编辑此页'
        },

        // 最后更新时间
        lastUpdated: {
            text: '最后更新'
        },

        // 中文配置
        docFooter: {
            prev: '上一页',
            next: '下一页'
        },
        outline: {
            label: '页面导航'
        }
    },

    // 语言配置
    lang: 'zh-CN',

    // Markdown 配置
    markdown: {
        lineNumbers: true,
        math: true
    }
})
