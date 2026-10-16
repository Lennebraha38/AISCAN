import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // jsdom: DOM/localStorage/crypto gibi tarayıcı API'leri için.
    environment: "jsdom",
    include: ["lib/**/*.test.ts", "app/**/*.test.ts"],
    setupFiles: ["./vitest.setup.ts"],
  },
});
