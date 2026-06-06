import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GithubOnboardingPage } from "./GithubOnboardingPage"

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
    },
    status: 200,
    ...init,
  })
}

function renderPage(search = "") {
  window.history.pushState({}, "", `/onboarding/github${search}`)

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <GithubOnboardingPage />
    </QueryClientProvider>
  )
}

function mockOnboardingFetch({
  installStart = installStartPayload(),
  billing = billingPayload(),
  organizations = organizationsPayload(),
  repositories = repositoriesPayload(),
}: {
  installStart?: Response | unknown
  billing?: Response | ReturnType<typeof billingPayload>
  organizations?: Response | unknown
  repositories?: Response | unknown
} = {}) {
  let billingState = billing
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost")
      if (url.pathname === "/api/v1/github-app/installations/start/") {
        return installStart instanceof Response
          ? installStart
          : jsonResponse(installStart)
      }
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
        if (billingState instanceof Response) {
          return billingState
        }
        if (init?.method === "PATCH" && init.body) {
          const patch = JSON.parse(String(init.body))
          billingState = {
            ...billingState,
            subscription: {
              ...billingState.subscription,
              ...patch,
            },
            billing: {
              ...billingState.billing,
              autonomous_pr_add_on_subtotal_cents:
                patch.autonomous_pr_add_on_enabled === false
                  ? 0
                  : billingState.subscription.autonomous_pr_add_on_price_cents,
              monthly_estimate_cents:
                billingState.billing.base_subtotal_cents +
                (patch.autonomous_pr_add_on_enabled === false
                  ? 0
                  : billingState.subscription.autonomous_pr_add_on_price_cents),
            },
          }
        }
        return jsonResponse(billingState)
      }
      return new Response(null, { status: 404 })
    })
  )
}

describe("GithubOnboardingPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.pushState({}, "", "/")
  })

  it("shows a loading state while install start is requested", () => {
    let resolveResponse: (response: Response) => void
    const pendingInstallStart = new Promise<Response>((resolve) => {
      resolveResponse = resolve
    })
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input), "http://localhost")
        if (url.pathname === "/api/v1/github-app/installations/start/") {
          return pendingInstallStart
        }
        return new Response(null, { status: 403 })
      })
    )

    renderPage()

    expect(
      screen.getByRole("heading", { name: "Loading GitHub onboarding" })
    ).toBeInTheDocument()
    resolveResponse!(jsonResponse(installStartPayload()))
  })

  it("shows the pre-install empty state with the install CTA", async () => {
    mockOnboardingFetch({
      organizations: new Response(null, { status: 403 }),
    })

    renderPage()

    expect(
      await screen.findByRole("heading", { name: "No GitHub installation" })
    ).toBeInTheDocument()
    expect(
      screen.getAllByRole("link", { name: "Install GitHub App" })[0]
    ).toHaveAttribute(
      "href",
      "https://github.com/apps/codebase-gardener/installations/new?state=signed"
    )
  })

  it("shows an error state when onboarding APIs fail", async () => {
    mockOnboardingFetch({
      installStart: new Response(null, { status: 500 }),
      organizations: new Response(null, { status: 403 }),
    })

    renderPage()

    expect(
      await screen.findByRole("heading", {
        name: "Could not load GitHub onboarding",
      })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Retry GitHub onboarding" })
    ).toBeInTheDocument()
  })

  it("renders callback success and selected repositories", async () => {
    mockOnboardingFetch()

    renderPage("?status=installed&organization_id=org-1")

    expect(await screen.findByText("GitHub App installed")).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Selected repositories" })
    ).toBeInTheDocument()
    expect(await screen.findByText("acme/api")).toBeInTheDocument()
    expect(screen.getByText("acme/web")).toBeInTheDocument()
    expect(screen.getByText("2.10x")).toBeInTheDocument()
    expect(
      screen.getByText("120,000 LOC · 9 modules · 6 contributors")
    ).toBeInTheDocument()
    expect(screen.getByText("Partial / 1.0x")).toBeInTheDocument()
    expect(
      screen.getByText("42,000 LOC · 4 modules · Unknown contributors")
    ).toBeInTheDocument()
    expect(screen.getByText("Restricted")).toBeInTheDocument()
    expect(
      screen.getByText("Owner or admin can view billing inputs")
    ).toBeInTheDocument()
    expect(screen.getByText("Unknown / 1.0x")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /Edit repository access in GitHub/ })
    ).toHaveAttribute(
      "href",
      "https://github.com/organizations/acme/settings/installations/2001"
    )
    expect(
      screen.getByRole("heading", { name: "Billing plan" })
    ).toBeInTheDocument()
    expect(screen.getByText("Managed Repository Base")).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument()
    expect(screen.getByText("5.10")).toBeInTheDocument()
    expect(screen.getByText("$104.00")).toBeInTheDocument()
    expect(screen.getByText("$106.00")).toBeInTheDocument()
    expect(screen.getByLabelText("Autonomous PR add-on")).toBeChecked()
  })

  it("toggles the autonomous PR add-on from billing inputs", async () => {
    const user = userEvent.setup()
    mockOnboardingFetch()

    renderPage("?status=installed&organization_id=org-1")

    const toggle = await screen.findByLabelText("Autonomous PR add-on")
    await user.click(toggle)

    await waitFor(() => {
      expect(toggle).not.toBeChecked()
    })
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/organizations/org-1/billing/",
      expect.objectContaining({
        body: JSON.stringify({ autonomous_pr_add_on_enabled: false }),
        method: "PATCH",
      })
    )
    expect(screen.getAllByText("$104.00")).toHaveLength(2)
  })

  it("renders an empty selected-repositories state", async () => {
    mockOnboardingFetch({
      repositories: {
        ...repositoriesPayload(),
        repositories: [],
      },
    })

    renderPage("?status=installed&organization_id=org-1")

    expect(
      await screen.findByText("No selected repositories")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /Edit repository access in GitHub/ })
    ).toBeInTheDocument()
  })
})

function installStartPayload() {
  return {
    install_url:
      "https://github.com/apps/codebase-gardener/installations/new?state=signed",
  }
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
        complexity: partialComplexity(),
      },
      {
        id: "repo-3",
        github_repository_id: 3003,
        name: "worker",
        full_name: "acme/worker",
        owner_login: "acme",
        private: true,
        default_branch: "main",
        html_url: "https://github.com/acme/worker",
        selected_at: "2026-06-06T08:00:00Z",
        complexity: restrictedComplexity(),
      },
      {
        id: "repo-4",
        github_repository_id: 3004,
        name: "docs",
        full_name: "acme/docs",
        owner_login: "acme",
        private: false,
        default_branch: "main",
        html_url: "https://github.com/acme/docs",
        selected_at: "2026-06-06T08:00:00Z",
        complexity: pendingComplexity(),
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
      active_managed_repository_count: 4,
      billable_repository_units: 5.1,
      base_subtotal_cents: 10400,
      autonomous_pr_add_on_subtotal_cents: 200,
      monthly_estimate_cents: 10600,
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

function partialComplexity() {
  return {
    input_status: "partial",
    loc: 42000,
    module_count: 4,
    contributor_count: null,
    loc_score: 0.33,
    module_score: 0.33,
    contributor_score: 0,
    weighted_score: 0,
    multiplier: 1,
    calculation_version: "complexity.v1.equal_thirds",
    source_analysis_id: "analysis-2",
    source_commit_sha: "def456",
    missing_inputs: ["contributor_count"],
    calculated_at: "2026-06-06T08:11:00Z",
  }
}

function restrictedComplexity() {
  return {
    input_status: "restricted",
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
    missing_inputs: [],
    calculated_at: null,
  }
}

function pendingComplexity() {
  return {
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
}
