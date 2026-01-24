import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

import Icons from 'unplugin-icons/vite'
import IconsResolver from 'unplugin-icons/resolver'

export default defineConfig(({ mode }) => { // 使用 mode 参数
  const env = loadEnv(mode, process.cwd(), ''); // 加载环境变量

  return {
    build: {
      target: "esnext", // 支持最新 ES 特性
    },
    server: {
      host: '0.0.0.0',
      port: 8080,
      proxy: {
        '/api': {
          target: 'http://localhost:8888',
          changeOrigin: true,
        },
        '/device': {
          target: 'http://localhost:8888',
          changeOrigin: true,
        },
        '/channel': {
          target: 'http://localhost:8888',
          changeOrigin: true,
        },
      },
    },
    base: './', // 修改这里的值为您想要设置的新路径
    plugins: [
      vue(),
      vueDevTools(),
      AutoImport({
        resolvers: [ElementPlusResolver(), IconsResolver()],
      }),
      Components({
        resolvers: [
          ElementPlusResolver(),
          IconsResolver({
            prefix: false, // <--
            enabledCollections: ['mdi'],
          }),
        ],
      }),
      Icons({
        autoInstall: true,
      }),
    ],
    envPrefix: ['VITE', 'VUE'], // 环境变量前缀
    define: {
      'process.env.VITE_APP_BASE_API': JSON.stringify(env.VITE_APP_BASE_API || ''), // 确保有默认值
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    css: {
      preprocessorOptions: {
        scss: {
          api: 'modern',
        },
      },
    },
  };
});
