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
      repositories: [
        {
          full_name: "acme/api",
          complexity: {
            input_status: "complete",
            multiplier: 2.1,
          },
        },
      ],
    })
  })

  it("parses pending repository complexity", () => {
    const payload = repositoryListPayload()
    payload.repositories[0].complexity = pendingComplexity()

    expect(parseRepositoriesResponse(payload).repositories[0].complexity).toEqual(
      pendingComplexity()
    )
  })

  it("parses partial and restricted repository complexity", () => {
    const payload = repositoryListPayload()
    payload.repositories = [
      { ...payload.repositories[0], complexity: partialComplexity() },
      {
        ...payload.repositories[0],
        id: "repo-2",
        github_repository_id: 3002,
        complexity: restrictedComplexity(),
      },
    ]

    expect(parseRepositoriesResponse(payload).repositories[0].complexity).toEqual(
      partialComplexity()
    )
    expect(parseRepositoriesResponse(payload).repositories[1].complexity).toEqual(
      restrictedComplexity()
    )
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
        complexity: completeComplexity(),
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
