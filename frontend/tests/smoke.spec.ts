import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"

const apiBaseUrl = (
  process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/+$/, "")
const firstReportApi = `${apiBaseUrl}/reports/first/`
const githubInstallStartApi = `${apiBaseUrl}/github-app/installations/start/`
const organizationsApi = `${apiBaseUrl}/organizations/`
const repositoriesApi = `${apiBaseUrl}/organizations/org-1/repositories/`
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
const credentialCorsHeaders = {
  "access-control-allow-credentials": "true",
  "access-control-allow-origin": "http://127.0.0.1:5174",
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

test("loads GitHub onboarding with selected repositories", async ({ page }) => {
  const installUrl =
    "https://github.com/apps/codebase-gardener/installations/new?state=signed"
  const settingsUrl =
    "https://github.com/organizations/acme/settings/installations/2001"

  await page.route(githubInstallStartApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: {
        install_url: installUrl,
      },
    })
  })
  await page.route(organizationsApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: {
        organizations: [
          {
            id: "org-1",
            name: "Acme",
            github_login: "acme",
            github_account_type: "organization",
          },
        ],
      },
    })
  })
  await page.route(repositoriesApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: {
        organization: {
          id: "org-1",
          name: "Acme",
          github_login: "acme",
          github_account_type: "organization",
        },
        installation: {
          id: "inst-1",
          github_installation_id: 2001,
          repository_selection: "selected",
          html_url: settingsUrl,
        },
        repositories: [
          {
            id: "repo-1",
            github_repository_id: 3001,
            name: "api",
            full_name: "acme/api",
            owner_login: "acme",
            private: true,
            default_branch: "main",
            html_url: "https://github.com/acme/api",
            selected_at: "2026-06-06T08:00:00Z",
          },
          {
            id: "repo-2",
            github_repository_id: 3002,
            name: "web",
            full_name: "acme/web",
            owner_login: "acme",
            private: true,
            default_branch: "main",
            html_url: "https://github.com/acme/web",
            selected_at: "2026-06-06T08:00:00Z",
          },
        ],
      },
    })
  })

  await page.goto("/onboarding/github?status=installed&organization_id=org-1")

  await expect(
    page.getByRole("link", { name: "Install GitHub App" })
  ).toHaveAttribute("href", installUrl)
  await expect(page.getByText("GitHub App installed")).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Selected repositories" })
  ).toBeVisible()
  await expect(page.getByRole("link", { name: "acme/api" })).toBeVisible()
  await expect(page.getByRole("link", { name: "acme/web" })).toBeVisible()
  await expect(
    page.getByRole("link", { name: /Edit repository access in GitHub/ })
  ).toHaveAttribute("href", settingsUrl)
})
