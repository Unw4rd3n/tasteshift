import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "DEV_");
  return {
    build: {
      outDir: "dist/client",
    },
    optimizeDeps: {
      include: ["react", "react-dom/client"],
    },
    server: {
      host: "127.0.0.1",
      allowedHosts: ["terminal.local"],
      warmup: {
        clientFiles: ["./src/main.tsx"],
      },
      proxy: {
        "/api": {
          target: env.DEV_API_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
          configure(proxy) {
            proxy.on("proxyReq", (outgoing, request) => {
              // Adapt only a same-origin request on this loopback development server.
              // Foreign origins remain untouched so FastAPI's CSRF check rejects them.
              const host = request.headers.host;
              if (
                /^(localhost|127\.0\.0\.1):\d+$/.test(host || "") &&
                request.headers.origin === `http://${host}`
              ) {
                outgoing.setHeader(
                  "origin",
                  env.DEV_API_ORIGIN || "http://localhost:8000",
                );
              }
            });
          },
        },
      },
    },
    test: {
      include: ["src/**/*.test.{ts,tsx}"],
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      clearMocks: true,
    },
    plugins: [react()],
  };
});
