import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8082",
      "/live": "http://127.0.0.1:8082",
      "/recommendations": "http://127.0.0.1:8082",
    },
  },
});
