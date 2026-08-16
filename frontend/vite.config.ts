import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 前端 dev server 端口 18080；后端 FastAPI 在 127.0.0.1:13080（见 src/api.ts 的 VITE_API_BASE）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 18080,
    strictPort: true,
    host: true,
  },
});
