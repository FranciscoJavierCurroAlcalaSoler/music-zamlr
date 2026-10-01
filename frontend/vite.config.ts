import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      // Rust's build directory is not source, and watching it kills the dev
      // server: the watcher opens every file it finds, and cargo rewrites
      // DLLs under it while the window is running, so Vite stops with
      // "EBUSY: resource busy or locked, watch ... app_lib.dll".
      ignored: ["**/src-tauri/**"],
    },
  },
});
