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
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
