import { describe, expect, it, vi } from "vitest"

import {
  buildGithubOnboardingApiUrl,
  fetchInstallationStart,
  fetchOrganizations,
  fetchOrganizationRepositories,
  GithubOnboardingContractError,
  GithubOnboardingRequestError,
  parseRepositoriesResponse,
} from "./github-onboarding-api"

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
    },
    status: 200,
    ...init,
  })
}

function fetcherReturning(response: Response) {
  return vi.fn(async () => response) as unknown as typeof fetch
}

describe("github onboarding API", () => {
  it("builds onboarding URLs from the configured API base", () => {
    expect(
      buildGithubOnboardingApiUrl(
        "/github-app/installations/start/",
        "http://localhost:8000/api/v1"
      )
    ).toBe("http://localhost:8000/api/v1/github-app/installations/start/")
    expect(buildGithubOnboardingApiUrl("organizations/", "/api/v1/")).toBe(
      "/api/v1/organizations/"
    )
  })

  it("fetches the install URL with credentials enabled", async () => {
    const fetcher = fetcherReturning(
      jsonResponse({
        install_url:
          "https://github.com/apps/codebase-gardener/installations/new?state=signed",
      })
    )

    await expect(
      fetchInstallationStart({
        apiBaseUrl: "http://localhost:8000/api/v1",
        fetcher,
      })
    ).resolves.toEqual({
      install_url:
        "https://github.com/apps/codebase-gardener/installations/new?state=signed",
    })
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/github-app/installations/start/",
      {
        credentials: "include",
        headers: { Accept: "application/json" },
      }
    )
  })

  it("fetches organization and repository lists", async () => {
    await expect(
      fetchOrganizations({
        fetcher: fetcherReturning(
          jsonResponse({
            organizations: [
              {
                id: "org-1",
                name: "Acme",
                github_login: "acme",
                github_account_type: "organization",
              },
            ],
          })
        ),
      })
    ).resolves.toMatchObject({
      organizations: [{ github_login: "acme" }],
    })

    await expect(
      fetchOrganizationRepositories("org-1", {
        fetcher: fetcherReturning(jsonResponse(repositoryListPayload())),
      })
    ).resolves.toMatchObject({
      repositories: [{ full_name: "acme/api" }],
    })
  })

  it("rejects request failures", async () => {
    await expect(
      fetchOrganizations({
        fetcher: fetcherReturning(new Response(null, { status: 403 })),
      })
    ).rejects.toBeInstanceOf(GithubOnboardingRequestError)
  })

  it("rejects repository payloads that drift from the onboarding contract", () => {
    expect(() => parseRepositoriesResponse({ repositories: [] })).toThrow()
  })

  it("rejects invalid JSON responses", async () => {
    await expect(
      fetchOrganizations({
        fetcher: fetcherReturning(
          new Response("not json", {
            headers: { "Content-Type": "application/json" },
            status: 200,
          })
        ),
      })
    ).rejects.toBeInstanceOf(GithubOnboardingContractError)
  })
})

function repositoryListPayload() {
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
    ],
  }
}
