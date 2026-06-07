import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

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

function mockAutomationFetch() {
  let automationState = automationPayload()
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost")
      if (url.pathname === "/api/v1/organizations/") {
        return jsonResponse(organizationsPayload())
      }
      if (url.pathname === "/api/v1/organizations/org-1/repositories/") {
        return jsonResponse(repositoriesPayload())
      }
      if (url.pathname === "/api/v1/organizations/org-1/billing/") {
        return jsonResponse(billingPayload())
      }
      if (
        url.pathname ===
        "/api/v1/organizations/org-1/repositories/repo-1/automation/"
      ) {
        if (init?.method === "PATCH" && init.body) {
          const patch = JSON.parse(String(init.body))
          automationState = {
            ...automationState,
            policy: {
              ...automationState.policy,
              ...patch,
              updated_at: "2026-06-06T08:05:00Z",
            },
          }
        }
        return jsonResponse(automationState)
      }
      if (
        url.pathname ===
        "/api/v1/organizations/org-1/repositories/repo-1/automation/trigger/"
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
  afterEach(() => {
    vi.unstubAllGlobals()
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
    expect(screen.getByLabelText("Commit threshold")).toHaveValue(10)
    expect(screen.getByText("Refresh docs")).toBeInTheDocument()

    await user.click(screen.getByLabelText(/Schedule/))
    fireEvent.change(screen.getByLabelText("Commit threshold"), {
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

function repositoriesPayload() {
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
        complexity: completeComplexity(),
      },
    ],
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

function automationPayload() {
  return {
    schema_version: "1.0",
    repository: {
      id: "repo-1",
      full_name: "acme/api",
      default_branch: "main",
      html_url: "https://github.com/acme/api",
    },
    baseline: {
      analysis_id: "analysis-1",
      commit_sha: "abc123baseline",
      source: "first_scan",
      promoted_at: "2026-06-06T08:00:00Z",
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
