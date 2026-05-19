import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const DEFAULT_PORT = 5175;
const port = Number(process.env.VITE_PORT) || DEFAULT_PORT;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:8765",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
