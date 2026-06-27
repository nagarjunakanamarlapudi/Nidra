import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["__tests__/**/*.test.ts"],
  },
  resolve: {
    alias: {
      // Mirror the `@/*` import alias from tsconfig.json.
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
});
