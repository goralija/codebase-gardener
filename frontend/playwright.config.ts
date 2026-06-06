import { defineConfig, devices } from "@playwright/test"

const apiBaseUrl =
  process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "on-first-retry",
  },
  webServer: {
    command: `VITE_API_BASE_URL=${apiBaseUrl} pnpm dev --host 127.0.0.1 --port 5174 --strictPort`,
    url: "http://127.0.0.1:5174",
    reuseExistingServer: false,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
})
