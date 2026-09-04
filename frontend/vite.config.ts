import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built bundle is served by FastAPI from frontend/dist, so assets are relative.
// In dev, /api is proxied to `f1dc serve` so the frontend can run against real data.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8420", changeOrigin: true } },
  },
});
