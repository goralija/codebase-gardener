import { readFileSync } from "node:fs"
import { expect, type Page, test } from "@playwright/test"

const apiBaseUrl = (
  process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/+$/, "")
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

type RepositoryPayload = ReturnType<typeof repositoryPayload>

test("loads the API-backed dashboard shell", async ({ page }) => {
  let requestedReportUrl: string | undefined
  await mockCockpitApi(page, {
    onReportRequest: (url) => {
      requestedReportUrl = url
    },
  })

  await page.goto("/")

  await expect(
    page.getByRole("heading", { name: "Gardener operations" })
  ).toBeVisible()
  await expect(page.getByText("Codebase Gardener")).toBeVisible()
  await expect(page.getByText("Active repositories")).toBeVisible()
  await expect(page.getByText("Avg entropy", { exact: true })).toBeVisible()
  await expect(page.getByText("api").first()).toBeVisible()
  expect(requestedReportUrl).toBe(`${apiBaseUrl}/reports/repository/repo-1/`)
})

test("shows the GitHub auth-required state", async ({ page }) => {
  await page.route(organizationsApi, async (route) => {
    await route.fulfill({
      body: JSON.stringify({
        code: "not_authenticated",
        details: {},
        message: "Authentication credentials were not provided.",
      }),
      contentType: "application/json",
      headers: credentialCorsHeaders,
      status: 403,
    })
  })

  await page.goto("/")

  await expect(page.getByText("GitHub session required")).toBeVisible()
  await expect(page.getByRole("button", { name: "GitHub setup" })).toBeVisible()
})

test("shows the empty installation state", async ({ page }) => {
  await page.route(organizationsApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: { organizations: [] },
    })
  })

  await page.goto("/")

  await expect(page.getByText("No GitHub installation")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Install GitHub App" })
  ).toBeVisible()
})

test("shows the repository operations error state", async ({ page }) => {
  await mockCockpitApi(page, { repositoriesStatus: 500 })

  await page.goto("/")

  await expect(page.getByText("Could not load repository operations")).toBeVisible()
})

test("loads GitHub onboarding with selected repositories", async ({ page }) => {
  const installUrl =
    "https://github.com/apps/codebase-gardener/installations/new?state=signed"

  await mockCockpitApi(page, {
    installUrl,
    repositories: [
      repositoryPayload(),
      repositoryPayload({
        complexity: pendingComplexity,
        full_name: "acme/web",
        github_repository_id: 3002,
        html_url: "https://github.com/acme/web",
        id: "repo-2",
        name: "web",
      }),
    ],
  })

  await page.goto("/onboarding/github?status=installed&organization_id=org-1")

  await expect(
    page.getByRole("heading", { name: "GitHub onboarding" })
  ).toBeVisible()
  await expect(page.getByText("App installed")).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Selected repositories" })
  ).toBeVisible()
  await expect(page.getByText("api").first()).toBeVisible()
  await expect(page.getByText("web").first()).toBeVisible()
  await expect(page.getByText("2.10×")).toBeVisible()
  await expect(page.getByText("1.00×")).toBeVisible()
  await expect(
    page.getByRole("heading", { name: "Billing plan" })
  ).toBeVisible()
  await expect(page.getByText("$64.00")).toBeVisible()
})

async function mockCockpitApi(
  page: Page,
  {
    installUrl = "https://github.com/apps/codebase-gardener/installations/new?state=signed",
    onReportRequest,
    repositories = [repositoryPayload()],
    repositoriesDelayMs = 0,
    repositoriesStatus = 200,
  }: {
    installUrl?: string
    onReportRequest?: (url: string) => void
    repositories?: RepositoryPayload[]
    repositoriesDelayMs?: number
    repositoriesStatus?: number
  } = {}
) {
  await page.route(githubInstallStartApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: { install_url: installUrl },
    })
  })
  await page.route(organizationsApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: organizationsPayload(),
    })
  })
  await page.route(`${repositoriesApi}**`, async (route) => {
    if (repositoriesDelayMs) {
      await new Promise((resolve) => setTimeout(resolve, repositoriesDelayMs))
    }
    if (repositoriesStatus !== 200) {
      await route.fulfill({
        body: JSON.stringify({
          code: "server_error",
          details: {},
          message: "Repository request failed.",
        }),
        contentType: "application/json",
        headers: credentialCorsHeaders,
        status: repositoriesStatus,
      })
      return
    }
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: repositoriesPayload(repositories),
    })
  })
  await page.route(billingApi, async (route) => {
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: billingPayload(repositories),
    })
  })
  await page.route(`${apiBaseUrl}/reports/repository/*/`, async (route) => {
    onReportRequest?.(route.request().url())
    await route.fulfill({
      headers: credentialCorsHeaders,
      json: firstReportFixture,
    })
  })
  await page.route(
    `${apiBaseUrl}/organizations/org-1/repositories/*/automation/`,
    async (route) => {
      const repositoryId = route.request().url().match(/repositories\/([^/]+)/)?.[1]
      const repository =
        repositories.find((repo) => repo.id === repositoryId) ?? repositories[0]
      await route.fulfill({
        headers: credentialCorsHeaders,
        json: automationPayload(repository),
      })
    }
  )
}

function organizationsPayload() {
  return {
    organizations: [
      {
        id: "org-1",
        name: "Acme",
        github_login: "acme",
        github_account_type: "organization",
      },
    ],
  }
}

function repositoriesPayload(repositories: RepositoryPayload[]) {
  return {
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
      html_url:
        "https://github.com/organizations/acme/settings/installations/2001",
    },
    repositories,
  }
}

function repositoryPayload(overrides = {}) {
  return {
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
    ...overrides,
  }
}

function billingPayload(repositories: RepositoryPayload[]) {
  return {
    organization: organizationsPayload().organizations[0],
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
      active_managed_repository_count: repositories.length,
      billable_repository_units: 3.1,
      base_subtotal_cents: 6200,
      autonomous_pr_add_on_subtotal_cents: 200,
      monthly_estimate_cents: 6400,
    },
    repositories: repositories.map((repository) => ({
      id: repository.id,
      full_name: repository.full_name,
      billable_units: repository.complexity.multiplier,
      base_monthly_cents: Math.round(2000 * repository.complexity.multiplier),
      complexity: repository.complexity,
    })),
    permissions: {
      can_edit_add_on: true,
      can_edit_plan_and_prices: false,
    },
  }
}

function automationPayload(repository: RepositoryPayload) {
  return {
    schema_version: "1.0",
    repository: {
      id: repository.id,
      full_name: repository.full_name,
      default_branch: repository.default_branch,
      html_url: repository.html_url,
    },
    baseline: {
      analysis_id: "analysis-1",
      commit_sha: "abc123baseline",
      source: "first_scan",
      promoted_at: "2026-06-06T08:00:00Z",
    },
    stats: {
      report_count: 2,
      session_count: 1,
      completed_session_count: 1,
      pr_plan_count: 1,
      created_pr_count: 1,
      merged_pr_count: 1,
      blocked_pr_count: 0,
      latest_report_at: "2026-06-06T08:02:00Z",
    },
    policy: {
      id: `policy-${repository.id}`,
      autonomy_mode: "conservative",
      manual_trigger_enabled: true,
      scheduled_trigger_enabled: false,
      commit_trigger_enabled: false,
      risky_module_trigger_enabled: false,
      pr_opened_trigger_enabled: false,
      ci_failure_trigger_enabled: false,
      commit_threshold: 10,
      created_at: "2026-06-06T08:00:00Z",
      updated_at: "2026-06-06T08:00:00Z",
    },
    effective: {
      autonomous_pr_add_on_enabled: true,
      can_create_autonomous_prs: false,
      pr_creation_status:
        "Repository autonomy mode is Conservative; sessions report recommendations without PR creation.",
      default_commit_threshold: 10,
      confidence_threshold: 0.9,
    },
    permissions: {
      can_edit: true,
      can_trigger_manual_session: true,
    },
    recent_sessions: [
      {
        id: `session-${repository.id}`,
        status: "completed",
        trigger: { type: "schedule" },
        baseline_analysis_id: "analysis-1",
        current_analysis_id: "analysis-2",
        current_commit_sha: "def456current",
        has_drift_report: true,
        created_at: "2026-06-06T08:00:00Z",
        started_at: "2026-06-06T08:01:00Z",
        finished_at: "2026-06-06T08:02:00Z",
        last_error: "",
      },
    ],
    recent_pr_plans: [
      {
        id: `plan-${repository.id}`,
        title: "Refresh docs",
        blocked: false,
        block_reason: null,
        approval_status: "approved",
        execution_status: "succeeded",
        created_pr_url: "https://github.com/acme/api/pull/1",
        terminal_outcome: "merged",
        terminal_outcome_at: "2026-06-06T09:00:00Z",
        confidence: 0.94,
        confidence_threshold: 0.9,
        created_at: "2026-06-06T08:02:00Z",
      },
    ],
  }
}
