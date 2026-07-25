import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// base matches the GitHub Pages repo name: https://<user>.github.io/docuchat/
export default defineConfig({
  base: "/docuchat/",
  plugins: [react()],
});
