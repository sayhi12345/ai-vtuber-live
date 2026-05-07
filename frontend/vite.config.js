import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    conditions: ["import", "module", "browser", "default"],
  },
  server: {
    port: 5173,
  },
});
