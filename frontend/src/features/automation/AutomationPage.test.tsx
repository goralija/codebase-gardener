import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AutomationPage } from "./AutomationPage"

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
    },
    status: 200,
    ...init,
  })
}

function installLocalStorage() {
  const entries = new Map<string, string>()
  const storage = {
    clear: () => entries.clear(),
    getItem: (key: string) => entries.get(key) ?? null,
    key: (index: number) => Array.from(entries.keys())[index] ?? null,
    get length() {
      return entries.size
    },
    removeItem: (key: string) => {
      entries.delete(key)
    },
    setItem: (key: string, value: string) => {
      entries.set(key, value)
    },
  } satisfies Storage

  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: storage,
  })
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <AutomationPage />
    </QueryClientProvider>
  )
}

function mockAutomationFetch(repositories = [repositoryPayload()]) {
  const automationStates = new Map(
    repositories.map((repository) => [
      repository.id,
      automationPayload(repository),
    ])
  )
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost")
      if (url.pathname === "/api/v1/organizations/") {
        return jsonResponse(organizationsPayload())
      }
      if (url.pathname === "/api/v1/organizations/org-1/repositories/") {
        return jsonResponse(repositoriesPayload(repositories))
      }
      if (url.pathname === "/api/v1/organizations/org-1/billing/") {
        return jsonResponse(billingPayload())
      }
      const automationMatch = url.pathname.match(
        /^\/api\/v1\/organizations\/org-1\/repositories\/([^/]+)\/automation\/$/
      )
      if (automationMatch) {
        const repositoryId = automationMatch[1]
        const automationState = automationStates.get(repositoryId)
        if (!automationState) {
          return new Response(null, { status: 404 })
        }

        if (init?.method === "PATCH" && init.body) {
          const patch = JSON.parse(String(init.body))
          const nextAutomationState = {
            ...automationState,
            policy: {
              ...automationState.policy,
              ...patch,
              updated_at: "2026-06-06T08:05:00Z",
            },
          }
          automationStates.set(repositoryId, nextAutomationState)
          return jsonResponse(nextAutomationState)
        }
        return jsonResponse(automationState)
      }
      if (
        /^\/api\/v1\/organizations\/org-1\/repositories\/[^/]+\/automation\/trigger\/$/.test(
          url.pathname
        )
      ) {
        return jsonResponse({
          trigger: {
            gardening_session_id: "session-2",
            status: "queued",
            deduped: false,
          },
        })
      }
      return new Response(null, { status: 404 })
    })
  )
}

describe("AutomationPage", () => {
  beforeEach(() => {
    installLocalStorage()
  })

  afterEach(() => {
    window.localStorage.clear()
    vi.unstubAllGlobals()
  })

  it("shows an auth state when the session is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://localhost")
        if (url.pathname === "/api/v1/organizations/") {
          return jsonResponse(
            {
              code: "not_authenticated",
              message: "Authentication credentials were not provided.",
              details: {},
            },
            { status: 403 }
          )
        }
        return new Response(null, { status: 404 })
      })
    )

    renderPage()

    expect(
      await screen.findByRole("heading", { name: "GitHub session required" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "Open GitHub setup" })
    ).toHaveAttribute("href", "/onboarding/github")
  })

  it("renders automation controls and saves trigger settings", async () => {
    const user = userEvent.setup()
    mockAutomationFetch()

    renderPage()

    expect(
      await screen.findByRole("heading", {
        name: "Session triggers and PR policy",
      })
    ).toBeInTheDocument()
    expect(await screen.findByText("acme/api")).toBeInTheDocument()
    expect(await screen.findByText("Autonomous PR gate")).toBeInTheDocument()
    expect(screen.getByLabelText("Autonomous PR add-on")).toBeChecked()
    const commitThresholdTrigger = screen
      .getByLabelText("Commit threshold trigger")
      .closest("div")
    expect(commitThresholdTrigger).not.toBeNull()
    const commitThresholdInput = within(commitThresholdTrigger!).getByRole(
      "spinbutton",
      { name: "Commit threshold" }
    )
    expect(commitThresholdInput).toHaveValue(10)
    expect(
      screen.getByRole("link", { name: /First scan report/ })
    ).toHaveAttribute("href", "/report?repositoryId=repo-1&baseline=1")
    expect(
      screen.queryByRole("link", { name: "abc123baseli" })
    ).not.toBeInTheDocument()
    expect(screen.getByText("Refresh docs")).toBeInTheDocument()

    await user.click(screen.getByLabelText(/Schedule/))
    fireEvent.change(commitThresholdInput, {
      target: { value: "3" },
    })
    await user.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining(
          "/api/v1/organizations/org-1/repositories/repo-1/automation/"
        ),
        expect.objectContaining({
          body: expect.stringContaining('"scheduled_trigger_enabled":true'),
          method: "PATCH",
        })
      )
    })
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(
        "/api/v1/organizations/org-1/repositories/repo-1/automation/"
      ),
      expect.objectContaining({
        body: expect.stringContaining('"commit_threshold":3'),
      })
    )
  })

  it("preserves the selected repository across remounts", async () => {
    const user = userEvent.setup()
    mockAutomationFetch([
      repositoryPayload(),
      repositoryPayload({
        id: "repo-2",
        github_repository_id: 3002,
        name: "worker",
        full_name: "acme/worker",
        html_url: "https://github.com/acme/worker",
      }),
    ])

    const { unmount } = renderPage()

    await screen.findByRole("heading", { name: "acme/api" })
    await user.selectOptions(screen.getByLabelText("Repository"), "repo-2")

    expect(screen.getByLabelText("Repository")).toHaveValue("repo-2")
    expect(
      await screen.findByRole("heading", { name: "acme/worker" })
    ).toBeInTheDocument()

    unmount()
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "acme/worker" })
    ).toBeInTheDocument()
    expect(screen.getByLabelText("Repository")).toHaveValue("repo-2")
  })

  it("runs a manual session from the automation page", async () => {
    const user = userEvent.setup()
    mockAutomationFetch()

    renderPage()

    await screen.findByText("Manual run")
    await user.click(screen.getByRole("button", { name: "Run now" }))

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining(
          "/api/v1/organizations/org-1/repositories/repo-1/automation/trigger/"
        ),
        expect.objectContaining({
          method: "POST",
        })
      )
    })
  })
})

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

function repositoriesPayload(repositories = [repositoryPayload()]) {
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
    complexity: completeComplexity(),
    ...overrides,
  }
}

function billingPayload() {
  return {
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
      active_managed_repository_count: 1,
      billable_repository_units: 2.1,
      base_subtotal_cents: 4200,
      autonomous_pr_add_on_subtotal_cents: 200,
      monthly_estimate_cents: 4400,
    },
    repositories: [
      {
        id: "repo-1",
        full_name: "acme/api",
        billable_units: 2.1,
        base_monthly_cents: 4200,
        complexity: completeComplexity(),
      },
    ],
    permissions: {
      can_edit_add_on: true,
      can_edit_plan_and_prices: false,
    },
  }
}

function automationPayload(repository = repositoryPayload()) {
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
      id: "policy-1",
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
        id: "session-1",
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
        id: "plan-1",
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

function completeComplexity() {
  return {
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
}
