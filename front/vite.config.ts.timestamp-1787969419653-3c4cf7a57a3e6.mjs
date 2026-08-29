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
  const backendTarget = env.VITE_BACKEND_URL || "http://127.0.0.1:8991";
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
          target: backendTarget,
          changeOrigin: true
        },
        "/device": {
          target: backendTarget,
          changeOrigin: true
        },
        "/channel": {
          target: backendTarget,
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
      "process.env.VITE_APP_BASE_API": JSON.stringify(
        env.VITE_APP_BASE_API || ""
      )
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
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJFOlxcXFxnaXRodWJfcHJvamVjdFxcXFxlbXNfc2ltdWxhdGVcXFxcZnJvbnRcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkU6XFxcXGdpdGh1Yl9wcm9qZWN0XFxcXGVtc19zaW11bGF0ZVxcXFxmcm9udFxcXFx2aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vRTovZ2l0aHViX3Byb2plY3QvZW1zX3NpbXVsYXRlL2Zyb250L3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZmlsZVVSTFRvUGF0aCwgVVJMIH0gZnJvbSBcIm5vZGU6dXJsXCI7XG5cbmltcG9ydCB7IGRlZmluZUNvbmZpZywgbG9hZEVudiB9IGZyb20gXCJ2aXRlXCI7XG5pbXBvcnQgdnVlIGZyb20gXCJAdml0ZWpzL3BsdWdpbi12dWVcIjtcbmltcG9ydCB2dWVEZXZUb29scyBmcm9tIFwidml0ZS1wbHVnaW4tdnVlLWRldnRvb2xzXCI7XG5pbXBvcnQgQXV0b0ltcG9ydCBmcm9tIFwidW5wbHVnaW4tYXV0by1pbXBvcnQvdml0ZVwiO1xuaW1wb3J0IENvbXBvbmVudHMgZnJvbSBcInVucGx1Z2luLXZ1ZS1jb21wb25lbnRzL3ZpdGVcIjtcbmltcG9ydCB7IEVsZW1lbnRQbHVzUmVzb2x2ZXIgfSBmcm9tIFwidW5wbHVnaW4tdnVlLWNvbXBvbmVudHMvcmVzb2x2ZXJzXCI7XG5cbmltcG9ydCBJY29ucyBmcm9tIFwidW5wbHVnaW4taWNvbnMvdml0ZVwiO1xuaW1wb3J0IEljb25zUmVzb2x2ZXIgZnJvbSBcInVucGx1Z2luLWljb25zL3Jlc29sdmVyXCI7XG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZygoeyBtb2RlIH0pID0+IHtcbiAgLy8gXHU0RjdGXHU3NTI4IG1vZGUgXHU1M0MyXHU2NTcwXG4gIGNvbnN0IGVudiA9IGxvYWRFbnYobW9kZSwgcHJvY2Vzcy5jd2QoKSwgXCJcIik7IC8vIFx1NTJBMFx1OEY3RFx1NzNBRlx1NTg4M1x1NTNEOFx1OTFDRlxuICAvLyBUaGUgUHl0aG9uIGJhY2tlbmQgYmluZHMgSVB2NCBleHBsaWNpdGx5LiBVc2luZyBsb2NhbGhvc3QgbWF5IHJlc29sdmUgdG9cbiAgLy8gOjoxIGZpcnN0IG9uIFdpbmRvd3MvTm9kZSBhbmQgbWFrZXMgZXZlcnkgcHJveGllZCByZXF1ZXN0IGZhaWwuXG4gIGNvbnN0IGJhY2tlbmRUYXJnZXQgPSBlbnYuVklURV9CQUNLRU5EX1VSTCB8fCBcImh0dHA6Ly8xMjcuMC4wLjE6ODk5MVwiO1xuXG4gIHJldHVybiB7XG4gICAgYnVpbGQ6IHtcbiAgICAgIHRhcmdldDogXCJlc25leHRcIiwgLy8gXHU2NTJGXHU2MzAxXHU2NzAwXHU2NUIwIEVTIFx1NzI3OVx1NjAyN1xuICAgICAgb3V0RGlyOiBcIi4uL3d3d1wiLFxuICAgICAgZW1wdHlPdXREaXI6IHRydWUsXG4gICAgICBjaHVua1NpemVXYXJuaW5nTGltaXQ6IDE1MDAsXG4gICAgICByb2xsdXBPcHRpb25zOiB7XG4gICAgICAgIG91dHB1dDoge1xuICAgICAgICAgIG1hbnVhbENodW5rcyhpZCkge1xuICAgICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKFwibm9kZV9tb2R1bGVzXCIpKSB7XG4gICAgICAgICAgICAgIC8vIFNwbGl0IEVsZW1lbnQgUGx1cyBpbnRvIGl0cyBvd24gY2h1bmtcbiAgICAgICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKFwiZWxlbWVudC1wbHVzXCIpKSB7XG4gICAgICAgICAgICAgICAgcmV0dXJuIFwiZWxlbWVudC1wbHVzXCI7XG4gICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgLy8gR3JvdXAgb3RoZXIgZGVwZW5kZW5jaWVzIGludG8gYSB2ZW5kb3IgY2h1bmtcbiAgICAgICAgICAgICAgcmV0dXJuIFwidmVuZG9yXCI7XG4gICAgICAgICAgICB9XG4gICAgICAgICAgfSxcbiAgICAgICAgfSxcbiAgICAgIH0sXG4gICAgfSxcbiAgICBzZXJ2ZXI6IHtcbiAgICAgIGhvc3Q6IFwiMC4wLjAuMFwiLFxuICAgICAgcG9ydDogODA4MCxcbiAgICAgIHByb3h5OiB7XG4gICAgICAgIFwiL2FwaVwiOiB7XG4gICAgICAgICAgdGFyZ2V0OiBiYWNrZW5kVGFyZ2V0LFxuICAgICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcbiAgICAgICAgfSxcbiAgICAgICAgXCIvZGV2aWNlXCI6IHtcbiAgICAgICAgICB0YXJnZXQ6IGJhY2tlbmRUYXJnZXQsXG4gICAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgICBcIi9jaGFubmVsXCI6IHtcbiAgICAgICAgICB0YXJnZXQ6IGJhY2tlbmRUYXJnZXQsXG4gICAgICAgICAgY2hhbmdlT3JpZ2luOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgfSxcbiAgICB9LFxuICAgIGJhc2U6IFwiLi9cIiwgLy8gXHU0RkVFXHU2NTM5XHU4RkQ5XHU5MUNDXHU3Njg0XHU1MDNDXHU0RTNBXHU2MEE4XHU2MEYzXHU4OTgxXHU4QkJFXHU3RjZFXHU3Njg0XHU2NUIwXHU4REVGXHU1Rjg0XG4gICAgcGx1Z2luczogW1xuICAgICAgdnVlKCksXG4gICAgICBtb2RlICE9PSBcInByb2R1Y3Rpb25cIiAmJiB2dWVEZXZUb29scygpLFxuICAgICAgQXV0b0ltcG9ydCh7XG4gICAgICAgIHJlc29sdmVyczogW0VsZW1lbnRQbHVzUmVzb2x2ZXIoKSwgSWNvbnNSZXNvbHZlcigpXSxcbiAgICAgIH0pLFxuICAgICAgQ29tcG9uZW50cyh7XG4gICAgICAgIHJlc29sdmVyczogW1xuICAgICAgICAgIEVsZW1lbnRQbHVzUmVzb2x2ZXIoKSxcbiAgICAgICAgICBJY29uc1Jlc29sdmVyKHtcbiAgICAgICAgICAgIHByZWZpeDogZmFsc2UsIC8vIDwtLVxuICAgICAgICAgICAgZW5hYmxlZENvbGxlY3Rpb25zOiBbXCJtZGlcIl0sXG4gICAgICAgICAgfSksXG4gICAgICAgIF0sXG4gICAgICB9KSxcbiAgICAgIEljb25zKHtcbiAgICAgICAgYXV0b0luc3RhbGw6IHRydWUsXG4gICAgICB9KSxcbiAgICBdLFxuICAgIGVudlByZWZpeDogW1wiVklURVwiLCBcIlZVRVwiXSwgLy8gXHU3M0FGXHU1ODgzXHU1M0Q4XHU5MUNGXHU1MjREXHU3RjAwXG4gICAgZGVmaW5lOiB7XG4gICAgICBcInByb2Nlc3MuZW52LlZJVEVfQVBQX0JBU0VfQVBJXCI6IEpTT04uc3RyaW5naWZ5KFxuICAgICAgICBlbnYuVklURV9BUFBfQkFTRV9BUEkgfHwgXCJcIixcbiAgICAgICksIC8vIFx1Nzg2RVx1NEZERFx1NjcwOVx1OUVEOFx1OEJBNFx1NTAzQ1xuICAgIH0sXG4gICAgcmVzb2x2ZToge1xuICAgICAgYWxpYXM6IHtcbiAgICAgICAgXCJAXCI6IGZpbGVVUkxUb1BhdGgobmV3IFVSTChcIi4vc3JjXCIsIGltcG9ydC5tZXRhLnVybCkpLFxuICAgICAgfSxcbiAgICB9LFxuICAgIGNzczoge1xuICAgICAgcHJlcHJvY2Vzc29yT3B0aW9uczoge1xuICAgICAgICBzY3NzOiB7XG4gICAgICAgICAgYXBpOiBcIm1vZGVyblwiLFxuICAgICAgICAgIGFkZGl0aW9uYWxEYXRhOiBgQHVzZSBcIkAvc3R5bGVzL2JyZWFrcG9pbnRzLnNjc3NcIiBhcyBicDtcXG5gLFxuICAgICAgICB9LFxuICAgICAgfSxcbiAgICB9LFxuICB9O1xufSk7XG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQXNTLFNBQVMsZUFBZSxXQUFXO0FBRXpVLFNBQVMsY0FBYyxlQUFlO0FBQ3RDLE9BQU8sU0FBUztBQUNoQixPQUFPLGlCQUFpQjtBQUN4QixPQUFPLGdCQUFnQjtBQUN2QixPQUFPLGdCQUFnQjtBQUN2QixTQUFTLDJCQUEyQjtBQUVwQyxPQUFPLFdBQVc7QUFDbEIsT0FBTyxtQkFBbUI7QUFWNkosSUFBTSwyQ0FBMkM7QUFZeE8sSUFBTyxzQkFBUSxhQUFhLENBQUMsRUFBRSxLQUFLLE1BQU07QUFFeEMsUUFBTSxNQUFNLFFBQVEsTUFBTSxRQUFRLElBQUksR0FBRyxFQUFFO0FBRzNDLFFBQU0sZ0JBQWdCLElBQUksb0JBQW9CO0FBRTlDLFNBQU87QUFBQSxJQUNMLE9BQU87QUFBQSxNQUNMLFFBQVE7QUFBQTtBQUFBLE1BQ1IsUUFBUTtBQUFBLE1BQ1IsYUFBYTtBQUFBLE1BQ2IsdUJBQXVCO0FBQUEsTUFDdkIsZUFBZTtBQUFBLFFBQ2IsUUFBUTtBQUFBLFVBQ04sYUFBYSxJQUFJO0FBQ2YsZ0JBQUksR0FBRyxTQUFTLGNBQWMsR0FBRztBQUUvQixrQkFBSSxHQUFHLFNBQVMsY0FBYyxHQUFHO0FBQy9CLHVCQUFPO0FBQUEsY0FDVDtBQUVBLHFCQUFPO0FBQUEsWUFDVDtBQUFBLFVBQ0Y7QUFBQSxRQUNGO0FBQUEsTUFDRjtBQUFBLElBQ0Y7QUFBQSxJQUNBLFFBQVE7QUFBQSxNQUNOLE1BQU07QUFBQSxNQUNOLE1BQU07QUFBQSxNQUNOLE9BQU87QUFBQSxRQUNMLFFBQVE7QUFBQSxVQUNOLFFBQVE7QUFBQSxVQUNSLGNBQWM7QUFBQSxRQUNoQjtBQUFBLFFBQ0EsV0FBVztBQUFBLFVBQ1QsUUFBUTtBQUFBLFVBQ1IsY0FBYztBQUFBLFFBQ2hCO0FBQUEsUUFDQSxZQUFZO0FBQUEsVUFDVixRQUFRO0FBQUEsVUFDUixjQUFjO0FBQUEsUUFDaEI7QUFBQSxNQUNGO0FBQUEsSUFDRjtBQUFBLElBQ0EsTUFBTTtBQUFBO0FBQUEsSUFDTixTQUFTO0FBQUEsTUFDUCxJQUFJO0FBQUEsTUFDSixTQUFTLGdCQUFnQixZQUFZO0FBQUEsTUFDckMsV0FBVztBQUFBLFFBQ1QsV0FBVyxDQUFDLG9CQUFvQixHQUFHLGNBQWMsQ0FBQztBQUFBLE1BQ3BELENBQUM7QUFBQSxNQUNELFdBQVc7QUFBQSxRQUNULFdBQVc7QUFBQSxVQUNULG9CQUFvQjtBQUFBLFVBQ3BCLGNBQWM7QUFBQSxZQUNaLFFBQVE7QUFBQTtBQUFBLFlBQ1Isb0JBQW9CLENBQUMsS0FBSztBQUFBLFVBQzVCLENBQUM7QUFBQSxRQUNIO0FBQUEsTUFDRixDQUFDO0FBQUEsTUFDRCxNQUFNO0FBQUEsUUFDSixhQUFhO0FBQUEsTUFDZixDQUFDO0FBQUEsSUFDSDtBQUFBLElBQ0EsV0FBVyxDQUFDLFFBQVEsS0FBSztBQUFBO0FBQUEsSUFDekIsUUFBUTtBQUFBLE1BQ04saUNBQWlDLEtBQUs7QUFBQSxRQUNwQyxJQUFJLHFCQUFxQjtBQUFBLE1BQzNCO0FBQUE7QUFBQSxJQUNGO0FBQUEsSUFDQSxTQUFTO0FBQUEsTUFDUCxPQUFPO0FBQUEsUUFDTCxLQUFLLGNBQWMsSUFBSSxJQUFJLFNBQVMsd0NBQWUsQ0FBQztBQUFBLE1BQ3REO0FBQUEsSUFDRjtBQUFBLElBQ0EsS0FBSztBQUFBLE1BQ0gscUJBQXFCO0FBQUEsUUFDbkIsTUFBTTtBQUFBLFVBQ0osS0FBSztBQUFBLFVBQ0wsZ0JBQWdCO0FBQUE7QUFBQSxRQUNsQjtBQUFBLE1BQ0Y7QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
