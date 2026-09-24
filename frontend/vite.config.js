import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api and /uploads are forwarded to the FastAPI server, so the
// browser never deals with CORS. For a separately deployed API, set VITE_API_URL.
const backend = process.env.API_URL || "http://localhost:8000";
const proxy = { "/api": backend, "/uploads": backend };

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
});
