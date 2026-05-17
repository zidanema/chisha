import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// D-085: @chisha/contracts alias → packages/contracts/src (shared types).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@chisha/contracts": path.resolve(__dirname, "../../packages/contracts/src/index.ts"),
      "@chisha/contracts/living": path.resolve(__dirname, "../../packages/contracts/src/living.ts"),
      "@chisha/contracts/trace": path.resolve(__dirname, "../../packages/contracts/src/trace.ts"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
