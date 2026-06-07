import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import App from "@/App.tsx"

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
    },
    status: 200,
    ...init,
  })
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  )
}

function mockOverviewFetch({
  organizations = organizationsPayload(),
  repositories = repositoriesPayload(),
  automations = {
    "repo-1": automationPayload({
      fullName: "acme/api",
      repositoryId: "repo-1",
      stats: {
        blocked_pr_count: 1,
        completed_session_count: 1,
        created_pr_count: 2,
        latest_report_at: "2026-06-06T08:02:00Z",
        merged_pr_count: 1,
        pr_plan_count: 3,
        report_count: 2,
        session_count: 2,
      },
    }),
    "repo-2": automationPayload({
      fullName: "acme/web",
      hasBaseline: false,
      repositoryId: "repo-2",
      stats: {
        blocked_pr_count: 0,
        completed_session_count: 1,
        created_pr_count: 0,
        latest_report_at: "2026-06-05T08:02:00Z",
        merged_pr_count: 0,
        pr_plan_count: 0,
        report_count: 1,
        session_count: 1,
      },
    }),
  },
}: {
  organizations?: Response | unknown
  repositories?: Response | unknown
  automations?: Record<string, Response | unknown>
} = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost")
      if (url.pathname === "/api/v1/organizations/") {
        return organizations instanceof Response
          ? organizations
          : jsonResponse(organizations)
      }
      if (url.pathname === "/api/v1/organizations/org-1/repositories/") {
        return repositories instanceof Response
          ? repositories
          : jsonResponse(repositories)
      }
      const automationMatch = url.pathname.match(
        /^\/api\/v1\/organizations\/org-1\/repositories\/([^/]+)\/automation\/$/
      )
      if (automationMatch) {
        const automation = automations[automationMatch[1]]
        return automation instanceof Response
          ? automation
          : jsonResponse(automation)
      }
      return new Response(null, { status: 404 })
    })
  )
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders the operations overview with primary app destinations", async () => {
    mockOverviewFetch()

    renderApp()

    expect(
      await screen.findByRole("heading", { name: "Gardener operations" })
    ).toBeInTheDocument()
    expect(screen.getByText("acme")).toBeInTheDocument()
    expect(screen.getAllByText("Managed repositories")).toHaveLength(2)
    expect(screen.getByText("Automation")).toBeInTheDocument()
    expect(screen.getByText("Reports generated")).toBeInTheDocument()
    expect(await screen.findByText("3 reports")).toBeInTheDocument()
    expect(await screen.findAllByText("2 PRs")).toHaveLength(2)
    expect(await screen.findByText("acme/api")).toBeInTheDocument()
    expect(await screen.findByText("acme/web")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "Reports generated3 reports" })
    ).toHaveAttribute("href", "/report?repositoryId=repo-1&baseline=1")
    expect(screen.getByRole("link", { name: "acme/api" })).toHaveAttribute(
      "href",
      "/report?repositoryId=repo-1&baseline=1"
    )
    expect(screen.getByRole("link", { name: "acme/web" })).toHaveAttribute(
      "href",
      "/report?repositoryId=repo-2"
    )
    expect(screen.getByText("2 sessions")).toBeInTheDocument()
    expect(screen.getByText("1 merged, 1 blocked")).toBeInTheDocument()
    expect(screen.getByText("Baseline ready")).toBeInTheDocument()
    expect(screen.getByText("No baseline")).toBeInTheDocument()
    expect(
      screen.queryByRole("img", { name: "Codebase Gardener mascot" })
    ).not.toBeInTheDocument()
  })

  it("shows the setup state before a GitHub installation is available", async () => {
    mockOverviewFetch({
      organizations: jsonResponse(
        {
          code: "not_authenticated",
          message: "Authentication credentials were not provided.",
          details: {},
        },
        { status: 403 }
      ),
    })

    renderApp()

    expect(
      await screen.findByRole("heading", { name: "GitHub session required" })
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "GitHub setup" })).toHaveAttribute(
      "href",
      "/onboarding/github"
    )
  })

  it("shows the empty installation state for authenticated users without organizations", async () => {
    mockOverviewFetch({
      organizations: { organizations: [] },
    })

    renderApp()

    expect(
      await screen.findByRole("heading", { name: "No GitHub installation" })
    ).toBeInTheDocument()
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
        complexity: completeComplexity(),
      },
    ],
  }
}

function automationPayload({
  fullName,
  hasBaseline = true,
  repositoryId,
  stats,
}: {
  fullName: string
  hasBaseline?: boolean
  repositoryId: string
  stats: {
    blocked_pr_count: number
    completed_session_count: number
    created_pr_count: number
    latest_report_at: string | null
    merged_pr_count: number
    pr_plan_count: number
    report_count: number
    session_count: number
  }
}) {
  return {
    schema_version: "1.0",
    repository: {
      id: repositoryId,
      full_name: fullName,
      default_branch: "main",
      html_url: `https://github.com/${fullName}`,
    },
    baseline: {
      analysis_id: hasBaseline ? "analysis-1" : null,
      commit_sha: hasBaseline ? "abc123baseline" : null,
      source: hasBaseline ? "first_scan" : null,
      promoted_at: hasBaseline ? "2026-06-06T08:00:00Z" : null,
    },
    stats,
    policy: {
      id: `policy-${repositoryId}`,
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
    recent_sessions: [],
    recent_pr_plans: [],
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
