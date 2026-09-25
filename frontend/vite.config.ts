import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Phase 1 故意不配置 server.proxy：
// 前端直连 http://localhost:8000，这样浏览器会真正发起跨域请求，
// 后端 CORS 配置是否生效能立刻被验证出来。
// 用 proxy 会把跨域"藏起来"，上线时反而容易踩坑。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '127.0.0.1',
  },
})
