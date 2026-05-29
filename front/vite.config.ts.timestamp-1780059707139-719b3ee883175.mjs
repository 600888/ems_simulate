// vite.config.ts
import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "file:///E:/github_project/ems_simulate/front/node_modules/vite/dist/node/index.js";
import vue from "file:///E:/github_project/ems_simulate/front/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import vueDevTools from "file:///E:/github_project/ems_simulate/front/node_modules/vite-plugin-vue-devtools/dist/vite.mjs";
import AutoImport from "file:///E:/github_project/ems_simulate/front/node_modules/unplugin-auto-import/dist/vite.js";
import Components from "file:///E:/github_project/ems_simulate/front/node_modules/unplugin-vue-components/dist/vite.js";
import { ElementPlusResolver } from "file:///E:/github_project/ems_simulate/front/node_modules/unplugin-vue-components/dist/resolvers.js";
import Icons from "file:///E:/github_project/ems_simulate/front/node_modules/unplugin-icons/dist/vite.js";
import IconsResolver from "file:///E:/github_project/ems_simulate/front/node_modules/unplugin-icons/dist/resolver.js";
var __vite_injected_original_import_meta_url = "file:///E:/github_project/ems_simulate/front/vite.config.ts";
var vite_config_default = defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    build: {
      target: "esnext",
      // 支持最新 ES 特性
      outDir: "../www",
      emptyOutDir: true,
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules")) {
              if (id.includes("element-plus")) {
                return "element-plus";
              }
              return "vendor";
            }
          }
        }
      }
    },
    server: {
      host: "0.0.0.0",
      port: 8080,
      proxy: {
        "/api": {
          target: "http://localhost:8991",
          changeOrigin: true
        },
        "/device": {
          target: "http://localhost:8991",
          changeOrigin: true
        },
        "/channel": {
          target: "http://localhost:8991",
          changeOrigin: true
        }
      }
    },
    base: "./",
    // 修改这里的值为您想要设置的新路径
    plugins: [
      vue(),
      mode !== "production" && vueDevTools(),
      AutoImport({
        resolvers: [ElementPlusResolver(), IconsResolver()]
      }),
      Components({
        resolvers: [
          ElementPlusResolver(),
          IconsResolver({
            prefix: false,
            // <--
            enabledCollections: ["mdi"]
          })
        ]
      }),
      Icons({
        autoInstall: true
      })
    ],
    envPrefix: ["VITE", "VUE"],
    // 环境变量前缀
    define: {
      "process.env.VITE_APP_BASE_API": JSON.stringify(env.VITE_APP_BASE_API || "")
      // 确保有默认值
    },
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", __vite_injected_original_import_meta_url))
      }
    },
    css: {
      preprocessorOptions: {
        scss: {
          api: "modern",
          additionalData: `@use "@/styles/breakpoints.scss" as bp;
`
        }
      }
    }
  };
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJFOlxcXFxnaXRodWJfcHJvamVjdFxcXFxlbXNfc2ltdWxhdGVcXFxcZnJvbnRcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkU6XFxcXGdpdGh1Yl9wcm9qZWN0XFxcXGVtc19zaW11bGF0ZVxcXFxmcm9udFxcXFx2aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vRTovZ2l0aHViX3Byb2plY3QvZW1zX3NpbXVsYXRlL2Zyb250L3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZmlsZVVSTFRvUGF0aCwgVVJMIH0gZnJvbSAnbm9kZTp1cmwnXG5cbmltcG9ydCB7IGRlZmluZUNvbmZpZywgbG9hZEVudiB9IGZyb20gJ3ZpdGUnXG5pbXBvcnQgdnVlIGZyb20gJ0B2aXRlanMvcGx1Z2luLXZ1ZSdcbmltcG9ydCB2dWVEZXZUb29scyBmcm9tICd2aXRlLXBsdWdpbi12dWUtZGV2dG9vbHMnXG5pbXBvcnQgQXV0b0ltcG9ydCBmcm9tICd1bnBsdWdpbi1hdXRvLWltcG9ydC92aXRlJ1xuaW1wb3J0IENvbXBvbmVudHMgZnJvbSAndW5wbHVnaW4tdnVlLWNvbXBvbmVudHMvdml0ZSdcbmltcG9ydCB7IEVsZW1lbnRQbHVzUmVzb2x2ZXIgfSBmcm9tICd1bnBsdWdpbi12dWUtY29tcG9uZW50cy9yZXNvbHZlcnMnXG5cbmltcG9ydCBJY29ucyBmcm9tICd1bnBsdWdpbi1pY29ucy92aXRlJ1xuaW1wb3J0IEljb25zUmVzb2x2ZXIgZnJvbSAndW5wbHVnaW4taWNvbnMvcmVzb2x2ZXInXG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZygoeyBtb2RlIH0pID0+IHsgLy8gXHU0RjdGXHU3NTI4IG1vZGUgXHU1M0MyXHU2NTcwXG4gIGNvbnN0IGVudiA9IGxvYWRFbnYobW9kZSwgcHJvY2Vzcy5jd2QoKSwgJycpOyAvLyBcdTUyQTBcdThGN0RcdTczQUZcdTU4ODNcdTUzRDhcdTkxQ0ZcblxuICByZXR1cm4ge1xuICAgIGJ1aWxkOiB7XG4gICAgICB0YXJnZXQ6IFwiZXNuZXh0XCIsIC8vIFx1NjUyRlx1NjMwMVx1NjcwMFx1NjVCMCBFUyBcdTcyNzlcdTYwMjdcbiAgICAgIG91dERpcjogXCIuLi93d3dcIixcbiAgICAgIGVtcHR5T3V0RGlyOiB0cnVlLFxuICAgICAgY2h1bmtTaXplV2FybmluZ0xpbWl0OiAxNTAwLFxuICAgICAgcm9sbHVwT3B0aW9uczoge1xuICAgICAgICBvdXRwdXQ6IHtcbiAgICAgICAgICBtYW51YWxDaHVua3MoaWQpIHtcbiAgICAgICAgICAgIGlmIChpZC5pbmNsdWRlcygnbm9kZV9tb2R1bGVzJykpIHtcbiAgICAgICAgICAgICAgLy8gU3BsaXQgRWxlbWVudCBQbHVzIGludG8gaXRzIG93biBjaHVua1xuICAgICAgICAgICAgICBpZiAoaWQuaW5jbHVkZXMoJ2VsZW1lbnQtcGx1cycpKSB7XG4gICAgICAgICAgICAgICAgcmV0dXJuICdlbGVtZW50LXBsdXMnO1xuICAgICAgICAgICAgICB9XG4gICAgICAgICAgICAgIC8vIEdyb3VwIG90aGVyIGRlcGVuZGVuY2llcyBpbnRvIGEgdmVuZG9yIGNodW5rXG4gICAgICAgICAgICAgIHJldHVybiAndmVuZG9yJztcbiAgICAgICAgICAgIH1cbiAgICAgICAgICB9XG4gICAgICAgIH1cbiAgICAgIH1cbiAgICB9LFxuICAgIHNlcnZlcjoge1xuICAgICAgaG9zdDogJzAuMC4wLjAnLFxuICAgICAgcG9ydDogODA4MCxcbiAgICAgIHByb3h5OiB7XG4gICAgICAgICcvYXBpJzoge1xuICAgICAgICAgIHRhcmdldDogJ2h0dHA6Ly9sb2NhbGhvc3Q6ODk5MScsXG4gICAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgICAnL2RldmljZSc6IHtcbiAgICAgICAgICB0YXJnZXQ6ICdodHRwOi8vbG9jYWxob3N0Ojg5OTEnLFxuICAgICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcbiAgICAgICAgfSxcbiAgICAgICAgJy9jaGFubmVsJzoge1xuICAgICAgICAgIHRhcmdldDogJ2h0dHA6Ly9sb2NhbGhvc3Q6ODk5MScsXG4gICAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgfSxcbiAgICB9LFxuICAgIGJhc2U6ICcuLycsIC8vIFx1NEZFRVx1NjUzOVx1OEZEOVx1OTFDQ1x1NzY4NFx1NTAzQ1x1NEUzQVx1NjBBOFx1NjBGM1x1ODk4MVx1OEJCRVx1N0Y2RVx1NzY4NFx1NjVCMFx1OERFRlx1NUY4NFxuICAgIHBsdWdpbnM6IFtcbiAgICAgIHZ1ZSgpLFxuICAgICAgbW9kZSAhPT0gJ3Byb2R1Y3Rpb24nICYmIHZ1ZURldlRvb2xzKCksXG4gICAgICBBdXRvSW1wb3J0KHtcbiAgICAgICAgcmVzb2x2ZXJzOiBbRWxlbWVudFBsdXNSZXNvbHZlcigpLCBJY29uc1Jlc29sdmVyKCldLFxuICAgICAgfSksXG4gICAgICBDb21wb25lbnRzKHtcbiAgICAgICAgcmVzb2x2ZXJzOiBbXG4gICAgICAgICAgRWxlbWVudFBsdXNSZXNvbHZlcigpLFxuICAgICAgICAgIEljb25zUmVzb2x2ZXIoe1xuICAgICAgICAgICAgcHJlZml4OiBmYWxzZSwgLy8gPC0tXG4gICAgICAgICAgICBlbmFibGVkQ29sbGVjdGlvbnM6IFsnbWRpJ10sXG4gICAgICAgICAgfSksXG4gICAgICAgIF0sXG4gICAgICB9KSxcbiAgICAgIEljb25zKHtcbiAgICAgICAgYXV0b0luc3RhbGw6IHRydWUsXG4gICAgICB9KSxcbiAgICBdLFxuICAgIGVudlByZWZpeDogWydWSVRFJywgJ1ZVRSddLCAvLyBcdTczQUZcdTU4ODNcdTUzRDhcdTkxQ0ZcdTUyNERcdTdGMDBcbiAgICBkZWZpbmU6IHtcbiAgICAgICdwcm9jZXNzLmVudi5WSVRFX0FQUF9CQVNFX0FQSSc6IEpTT04uc3RyaW5naWZ5KGVudi5WSVRFX0FQUF9CQVNFX0FQSSB8fCAnJyksIC8vIFx1Nzg2RVx1NEZERFx1NjcwOVx1OUVEOFx1OEJBNFx1NTAzQ1xuICAgIH0sXG4gICAgcmVzb2x2ZToge1xuICAgICAgYWxpYXM6IHtcbiAgICAgICAgJ0AnOiBmaWxlVVJMVG9QYXRoKG5ldyBVUkwoJy4vc3JjJywgaW1wb3J0Lm1ldGEudXJsKSksXG4gICAgICB9LFxuICAgIH0sXG4gICAgY3NzOiB7XG4gICAgICBwcmVwcm9jZXNzb3JPcHRpb25zOiB7XG4gICAgICAgIHNjc3M6IHtcbiAgICAgICAgICBhcGk6ICdtb2Rlcm4nLFxuICAgICAgICAgIGFkZGl0aW9uYWxEYXRhOiBgQHVzZSBcIkAvc3R5bGVzL2JyZWFrcG9pbnRzLnNjc3NcIiBhcyBicDtcXG5gLFxuICAgICAgICB9LFxuICAgICAgfSxcbiAgICB9LFxuICB9O1xufSk7XG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQXNTLFNBQVMsZUFBZSxXQUFXO0FBRXpVLFNBQVMsY0FBYyxlQUFlO0FBQ3RDLE9BQU8sU0FBUztBQUNoQixPQUFPLGlCQUFpQjtBQUN4QixPQUFPLGdCQUFnQjtBQUN2QixPQUFPLGdCQUFnQjtBQUN2QixTQUFTLDJCQUEyQjtBQUVwQyxPQUFPLFdBQVc7QUFDbEIsT0FBTyxtQkFBbUI7QUFWNkosSUFBTSwyQ0FBMkM7QUFZeE8sSUFBTyxzQkFBUSxhQUFhLENBQUMsRUFBRSxLQUFLLE1BQU07QUFDeEMsUUFBTSxNQUFNLFFBQVEsTUFBTSxRQUFRLElBQUksR0FBRyxFQUFFO0FBRTNDLFNBQU87QUFBQSxJQUNMLE9BQU87QUFBQSxNQUNMLFFBQVE7QUFBQTtBQUFBLE1BQ1IsUUFBUTtBQUFBLE1BQ1IsYUFBYTtBQUFBLE1BQ2IsdUJBQXVCO0FBQUEsTUFDdkIsZUFBZTtBQUFBLFFBQ2IsUUFBUTtBQUFBLFVBQ04sYUFBYSxJQUFJO0FBQ2YsZ0JBQUksR0FBRyxTQUFTLGNBQWMsR0FBRztBQUUvQixrQkFBSSxHQUFHLFNBQVMsY0FBYyxHQUFHO0FBQy9CLHVCQUFPO0FBQUEsY0FDVDtBQUVBLHFCQUFPO0FBQUEsWUFDVDtBQUFBLFVBQ0Y7QUFBQSxRQUNGO0FBQUEsTUFDRjtBQUFBLElBQ0Y7QUFBQSxJQUNBLFFBQVE7QUFBQSxNQUNOLE1BQU07QUFBQSxNQUNOLE1BQU07QUFBQSxNQUNOLE9BQU87QUFBQSxRQUNMLFFBQVE7QUFBQSxVQUNOLFFBQVE7QUFBQSxVQUNSLGNBQWM7QUFBQSxRQUNoQjtBQUFBLFFBQ0EsV0FBVztBQUFBLFVBQ1QsUUFBUTtBQUFBLFVBQ1IsY0FBYztBQUFBLFFBQ2hCO0FBQUEsUUFDQSxZQUFZO0FBQUEsVUFDVixRQUFRO0FBQUEsVUFDUixjQUFjO0FBQUEsUUFDaEI7QUFBQSxNQUNGO0FBQUEsSUFDRjtBQUFBLElBQ0EsTUFBTTtBQUFBO0FBQUEsSUFDTixTQUFTO0FBQUEsTUFDUCxJQUFJO0FBQUEsTUFDSixTQUFTLGdCQUFnQixZQUFZO0FBQUEsTUFDckMsV0FBVztBQUFBLFFBQ1QsV0FBVyxDQUFDLG9CQUFvQixHQUFHLGNBQWMsQ0FBQztBQUFBLE1BQ3BELENBQUM7QUFBQSxNQUNELFdBQVc7QUFBQSxRQUNULFdBQVc7QUFBQSxVQUNULG9CQUFvQjtBQUFBLFVBQ3BCLGNBQWM7QUFBQSxZQUNaLFFBQVE7QUFBQTtBQUFBLFlBQ1Isb0JBQW9CLENBQUMsS0FBSztBQUFBLFVBQzVCLENBQUM7QUFBQSxRQUNIO0FBQUEsTUFDRixDQUFDO0FBQUEsTUFDRCxNQUFNO0FBQUEsUUFDSixhQUFhO0FBQUEsTUFDZixDQUFDO0FBQUEsSUFDSDtBQUFBLElBQ0EsV0FBVyxDQUFDLFFBQVEsS0FBSztBQUFBO0FBQUEsSUFDekIsUUFBUTtBQUFBLE1BQ04saUNBQWlDLEtBQUssVUFBVSxJQUFJLHFCQUFxQixFQUFFO0FBQUE7QUFBQSxJQUM3RTtBQUFBLElBQ0EsU0FBUztBQUFBLE1BQ1AsT0FBTztBQUFBLFFBQ0wsS0FBSyxjQUFjLElBQUksSUFBSSxTQUFTLHdDQUFlLENBQUM7QUFBQSxNQUN0RDtBQUFBLElBQ0Y7QUFBQSxJQUNBLEtBQUs7QUFBQSxNQUNILHFCQUFxQjtBQUFBLFFBQ25CLE1BQU07QUFBQSxVQUNKLEtBQUs7QUFBQSxVQUNMLGdCQUFnQjtBQUFBO0FBQUEsUUFDbEI7QUFBQSxNQUNGO0FBQUEsSUFDRjtBQUFBLEVBQ0Y7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
