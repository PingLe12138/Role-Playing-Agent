import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Plugin pages live outside the Vite root (<project root>/plugins/<id>/ui/), so
// bare package imports in those files would resolve against the project root
// (no node_modules there). The host app therefore exposes a white-list of its
// own dependencies via aliases to its node_modules; anything else must stay a
// relative import of the plugin's own files or come in via `@rpa/...`.
// / 插件页面位于 Vite 根目录之外（<项目根>/plugins/<id>/ui/），文件内的裸包导入会
//   从项目根查找 node_modules（不存在）。宿主应用因此通过别名暴露自身依赖白名单，
//   其余依赖只能是插件自身的相对导入或 @rpa/... 前缀。
const nodeModules = fileURLToPath(new URL('./node_modules', import.meta.url))
const hostedDeps = ['vue', 'element-plus', '@icon-park/vue-next', 'axios', 'pinia']

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // Allow plugin pages to import project helpers (e.g. api/request.js).
      // / 允许插件页面导入项目辅助模块（如 api/request.js）。
      '@rpa': fileURLToPath(new URL('./src', import.meta.url)),
      ...Object.fromEntries(hostedDeps.map((d) => [d, `${nodeModules}/${d}`])),
    },
  },
  server: {
    port: 5173,
    // Plugin pages live outside the Vite root, so the dev server needs fs
    // access to the next directory up.
    // / 插件页面位于 Vite 根目录之外，开发服务器需要 fs 访问其上一级目录。
    fs: {
      allow: ['..'],
    },
    proxy: {
      '/api/chat/stream': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Scene images are served by the FastAPI backend at /static.
      // / 场景插画由 FastAPI 后端在 /static 提供。
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
