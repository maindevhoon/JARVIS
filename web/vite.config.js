import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND = "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  base: "/",
  server: {
    proxy: {
      "/ws": { target: BACKEND, ws: true, changeOrigin: true },
      "/listen": { target: BACKEND, ws: true, changeOrigin: true },
      "/meeting": { target: BACKEND, changeOrigin: true },
      "/meetings": { target: BACKEND, changeOrigin: true },
      "/research": { target: BACKEND, changeOrigin: true },
      "/memory": { target: BACKEND, changeOrigin: true },
      "/supermemory": { target: "http://127.0.0.1:6767", changeOrigin: true, rewrite: (path) => path.replace(/^\/supermemory/, "") },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
