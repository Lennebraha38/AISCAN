import { defineConfig, devices } from "@playwright/test";

// Uçtan uca (E2E) test yapılandırması.
//
// Servisler (ai-core:8001, backend:8000, web:3000) testlerden ÖNCE ayakta
// olmalıdır; CI'da .github/workflows/e2e.yml bunları başlatıp demo verisini
// seed eder. Yerelde docker compose up sonrası veya README'deki adımlarla
// servisleri kaldırıp `npm run test:e2e` çalıştırın.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  timeout: 60_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    // Yerel hata ayiklamasi icin sistem tarayicisi: PLAYWRIGHT_CHANNEL=msedge
    // (CI'da set edilmez; CI indirilmis chromium kullanir).
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
