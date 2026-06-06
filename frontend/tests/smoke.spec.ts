import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"

const apiBaseUrl = (
  process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/+$/, "")
const firstReportApi = `${apiBaseUrl}/reports/first/`
const firstReportFixture = JSON.parse(
  readFileSync(
    new URL(
      "../../fixtures/contracts/first_report_fixture.json",
      import.meta.url
    ),
    "utf8"
  )
) as unknown

const corsHeaders = {
  "access-control-allow-origin": "*",
}

test("loads the API-backed dashboard shell", async ({ page }) => {
  let requestedFirstReportUrl: string | undefined

  await page.route(firstReportApi, async (route) => {
    requestedFirstReportUrl = route.request().url()
    await route.fulfill({
      headers: corsHeaders,
      json: firstReportFixture,
    })
  })

  await page.goto("/")

  await expect(
    page.getByRole("heading", { name: "First report" })
  ).toBeVisible()
  await expect(page.getByText("Repository Entropy Score")).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Architecture violations" })
  ).toBeVisible()
  await expect(page.getByText(/No architecture violations/)).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Constitution questions" })
  ).toBeVisible()
  await expect(
    page.getByText("No open constitution questions in this report.")
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Session status" })
  ).toBeVisible()
  await expect(
    page
      .getByRole("heading", { name: "Archive stale seed specification" })
      .first()
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Focused PR plans" })
  ).toBeVisible()
  expect(requestedFirstReportUrl).toBe(firstReportApi)
})

test("shows the first-report loading state", async ({ page }) => {
  await page.route(firstReportApi, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300))
    await route.fulfill({
      headers: corsHeaders,
      json: firstReportFixture,
    })
  })

  await page.goto("/")

  await expect(
    page.getByRole("heading", { name: "Loading first report" })
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "First report" })
  ).toBeVisible()
})

test("shows the first-report empty state", async ({ page }) => {
  await page.route(firstReportApi, async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        code: "not_found",
        message: "First report not found.",
        details: {},
      }),
      contentType: "application/json",
      headers: corsHeaders,
      status: 404,
    })
  })

  await page.goto("/")

  await expect(
    page.getByRole("heading", { name: "First report is not ready" })
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Retry first report" })
  ).toBeVisible()
})

test("shows the first-report error state", async ({ page }) => {
  await page.route(firstReportApi, async (route) => {
    await route.fulfill({
      body: JSON.stringify({ repository_constitution: {} }),
      contentType: "application/json",
      headers: corsHeaders,
      status: 200,
    })
  })

  await page.goto("/")

  await expect(
    page.getByRole("heading", { name: "Could not load first report" })
  ).toBeVisible()
  await expect(
    page.getByText(/does not match the shared contract/)
  ).toBeVisible()
})
