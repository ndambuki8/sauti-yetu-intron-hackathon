import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend on :8001,
// so no CORS configuration is needed during development.
// NOTE: port 8000 is used here by a Docker container (credit-api) that
// binds the IPv6 wildcard, so the triage backend runs on 8001 instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1 (not "localhost") so the proxy targets IPv4 explicitly
      // and never gets routed to a container listening on ::1.
      "/api": "http://127.0.0.1:8001",
    },
  },
});
