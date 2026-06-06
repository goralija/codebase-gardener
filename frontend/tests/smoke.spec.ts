import { readFileSync } from "node:fs"
import { expect, test } from "@playwright/test"

const apiBaseUrl = (
  process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/+$/, "")
const firstReportApi = `${apiBaseUrl}/reports/first/`
const githubInstallStartApi = `${apiBaseUrl}/github-app/installations/start/`
const organizationsApi = `${apiBaseUrl}/organizations/`
const repositoriesApi = `${apiBaseUrl}/organizations/org-1/repositories/`
const billingApi = `${apiBaseUrl}/organizations/org-1/billing/`
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
const completeComplexity = {
  input_status: "complete",
  loc: 120000,
  module_count: 9,
  contributor_count: 6,
  loc_score: 0.66,
  module_score: 0.66,
  contributor_score: 0.33,
  weighted_score: 0.55,
  multiplier: 2.1,
  calculation_version: "complexity.v1.equal_thirds",
  source_analysis_id: "analysis-1",
  source_commit_sha: "abc123",
  missing_inputs: [],
  calculated_at: "2026-06-06T08:10:00Z",
}
const pendingComplexity = {
  input_status: "pending",
  loc: null,
  module_count: null,
  contributor_count: null,
  loc_score: 0,
  module_score: 0,
  contributor_score: 0,
  weighted_score: 0,
  multiplier: 1,
  calculation_version: "complexity.v1.equal_thirds",
  source_analysis_id: null,
  source_commit_sha: null,
  missing_inputs: ["loc", "module_count", "contributor_count"],
  calculated_at: null,
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

  await page.goto("/report")

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

  await page.goto("/report")

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

  await page.goto("/report")

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

  await page.goto("/report")

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
  await page.route(`${repositoriesApi}**`, async (route) => {
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
            complexity: completeComplexity,
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
            complexity: pendingComplexity,
          },
        ],
      },
    })
  })
  await page.route(billingApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: {
        organization: {
          id: "org-1",
          name: "Acme",
          github_login: "acme",
          github_account_type: "organization",
        },
        subscription: {
          id: "subscription-1",
          plan_code: "managed_repository_base",
          currency: "USD",
          base_price_cents: 2000,
          autonomous_pr_add_on_enabled: true,
          autonomous_pr_add_on_price_cents: 200,
          created_at: "2026-06-06T08:00:00Z",
          updated_at: "2026-06-06T08:00:00Z",
        },
        billing: {
          active_managed_repository_count: 2,
          billable_repository_units: 3.1,
          base_subtotal_cents: 6200,
          autonomous_pr_add_on_subtotal_cents: 200,
          monthly_estimate_cents: 6400,
        },
        repositories: [
          {
            id: "repo-1",
            full_name: "acme/api",
            billable_units: 2.1,
            base_monthly_cents: 4200,
            complexity: completeComplexity,
          },
          {
            id: "repo-2",
            full_name: "acme/web",
            billable_units: 1,
            base_monthly_cents: 2000,
            complexity: pendingComplexity,
          },
        ],
        permissions: {
          can_edit_add_on: true,
          can_edit_plan_and_prices: false,
        },
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
  await expect(page.getByText("2.10x")).toBeVisible()
  await expect(page.getByText("Unknown / 1.0x")).toBeVisible()
  await expect(
    page.getByRole("link", { name: /Edit repository access in GitHub/ })
  ).toHaveAttribute("href", settingsUrl)
  await expect(
    page.getByRole("heading", { name: "Billing plan" })
  ).toBeVisible()
  await expect(page.getByText("$64.00")).toBeVisible()
})
