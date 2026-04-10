import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const PROXY_PATHS = [
  "/api",
  "/dashboard",
  "/inject",
  "/quarantine",
  "/reset",
  "/vaccine",
  "/status",
  "/events",
  "/logs"
];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    optimizeDeps: {
      include: ["recharts"]
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
    server: {
      port: 5173,
      host: "0.0.0.0",
      proxy: Object.fromEntries(
        PROXY_PATHS.map((path) => [
          path,
          {
            target: proxyTarget,
            changeOrigin: true,
          },
        ])
      ),
    }
  };
});
