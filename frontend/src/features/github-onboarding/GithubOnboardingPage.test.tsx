import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
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
  organizations = organizationsPayload(),
  repositories = repositoriesPayload(),
}: {
  installStart?: Response | unknown
  organizations?: Response | unknown
  repositories?: Response | unknown
} = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
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
    expect(
      screen.getByRole("link", { name: /Edit repository access in GitHub/ })
    ).toHaveAttribute(
      "href",
      "https://github.com/organizations/acme/settings/installations/2001"
    )
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
  }
}
