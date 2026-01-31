import { defineConfig } from 'vitepress'

export default defineConfig({
    // 站点基础配置
    title: 'EMS Simulate',
    description: '能源管理系统模拟器 - 项目文档',

    // GitHub Pages 部署路径
    base: '/ems_simulate/',

    // 主题配置
    themeConfig: {
        logo: '/img/m.ico',

        // 导航栏
        nav: [
            { text: '首页', link: '/' },
            { text: '快速开始', link: '/guide/getting-started' },
            { text: 'API 参考', link: '/api/overview' },
            { text: 'GitHub', link: 'https://github.com/600888/ems_simulate' }
        ],

        // 侧边栏
        sidebar: {
            '/guide/': [
                {
                    text: '指南',
                    items: [
                        { text: '快速开始', link: '/guide/getting-started' },
                        { text: '安装部署', link: '/guide/installation' },
                        { text: '配置说明', link: '/guide/configuration' }
                    ]
                },
                {
                    text: '核心概念',
                    items: [
                        { text: '测点类型', link: '/guide/point-types' },
                        { text: '协议支持', link: '/guide/protocols' },
                        { text: '解析码系统', link: '/guide/decode-system' }
                    ]
                }
            ],
            '/api/': [
                {
                    text: 'API 参考',
                    items: [
                        { text: '概述', link: '/api/overview' },
                        { text: '设备管理', link: '/api/device' },
                        { text: '测点操作', link: '/api/points' }
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
            copyright: 'Copyright © 2024-present'
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
        lineNumbers: true
    }
})
