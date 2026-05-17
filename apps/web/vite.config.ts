import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// chisha web - Vite config
// - 5173 dev / build into dist/
// - /api proxied to FastAPI server (8765) for real-API mode (D-051 backend)
// - Use VITE_USE_MOCK=1 to bypass network and use src/lib/mockApi.ts
// - D-085: @chisha/contracts alias to packages/contracts/src (shared types)
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@chisha/contracts": path.resolve(__dirname, "../../packages/contracts/src/index.ts"),
      "@chisha/contracts/living": path.resolve(__dirname, "../../packages/contracts/src/living.ts"),
      "@chisha/contracts/trace": path.resolve(__dirname, "../../packages/contracts/src/trace.ts"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});
