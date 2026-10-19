import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: "https://localhost:18002",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});