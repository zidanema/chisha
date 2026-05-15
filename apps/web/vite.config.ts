import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// chisha web - Vite config
// - 5173 dev / build into dist/
// - /api proxied to FastAPI debug_server (8765) for real-API mode (D-051 backend)
// - Use VITE_USE_MOCK=1 to bypass network and use src/lib/mockApi.ts
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
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
