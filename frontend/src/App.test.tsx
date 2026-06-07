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
  billing = billingPayload(),
}: {
  organizations?: Response | unknown
  repositories?: Response | unknown
  billing?: Response | unknown
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
      if (url.pathname === "/api/v1/organizations/org-1/billing/") {
        return billing instanceof Response ? billing : jsonResponse(billing)
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
    expect(screen.getByText("GitHub setup")).toBeInTheDocument()
    expect(screen.getAllByText("Automation")).toHaveLength(2)
    expect(screen.getByText("First report")).toBeInTheDocument()
    expect(await screen.findByText("PR add-on on")).toBeInTheDocument()
    expect(await screen.findByText("acme/api")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "First reportOpen report" })
    ).toHaveAttribute("href", "/report?repositoryId=repo-1&baseline=1")
    expect(screen.getByText("2.10x")).toBeInTheDocument()
    expect(
      screen.queryByRole("img", { name: "Codebase Gardener mascot" })
    ).not.toBeInTheDocument()
  })

  it("shows the setup state before a GitHub installation is available", async () => {
    mockOverviewFetch({
      organizations: new Response(null, { status: 403 }),
    })

    renderApp()

    expect(
      await screen.findByRole("heading", { name: "No GitHub installation" })
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "GitHub setup" })).toHaveAttribute(
      "href",
      "/onboarding/github"
    )
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
