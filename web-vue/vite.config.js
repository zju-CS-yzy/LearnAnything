import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 配置 — 适配 PyQt5 WebView 嵌入
export default defineConfig({
  plugins: [vue()],
  base: './', // 相对路径，适合本地文件加载
  build: {
    outDir: '../web/dist',
    emptyOutDir: true,
    assetsInlineLimit: 4096, // 小资源内联，减少请求
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:5000'
    }
  }
})
