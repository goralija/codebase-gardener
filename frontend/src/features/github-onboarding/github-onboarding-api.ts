import * as v from "valibot"

const DEFAULT_API_BASE_URL = "/api/v1"

const installationStartSchema = v.object({
  install_url: v.string(),
})

const organizationSchema = v.object({
  id: v.string(),
  name: v.string(),
  github_login: v.string(),
  github_account_type: v.string(),
})

const organizationsResponseSchema = v.object({
  organizations: v.array(organizationSchema),
})

const installationSchema = v.object({
  id: v.string(),
  github_installation_id: v.number(),
  repository_selection: v.string(),
  html_url: v.string(),
})

const repositoryComplexitySchema = v.object({
  input_status: v.string(),
  loc: v.nullable(v.number()),
  module_count: v.nullable(v.number()),
  contributor_count: v.nullable(v.number()),
  loc_score: v.number(),
  module_score: v.number(),
  contributor_score: v.number(),
  weighted_score: v.number(),
  multiplier: v.number(),
  calculation_version: v.string(),
  source_analysis_id: v.nullable(v.string()),
  source_commit_sha: v.nullable(v.string()),
  missing_inputs: v.array(v.string()),
  calculated_at: v.nullable(v.string()),
})

const managedRepositorySchema = v.object({
  id: v.string(),
  github_repository_id: v.number(),
  name: v.string(),
  full_name: v.string(),
  owner_login: v.string(),
  private: v.boolean(),
  default_branch: v.string(),
  html_url: v.string(),
  selected_at: v.string(),
  complexity: repositoryComplexitySchema,
})

const repositoriesResponseSchema = v.object({
  organization: organizationSchema,
  installation: installationSchema,
  repositories: v.array(managedRepositorySchema),
})

type FetchOptions = {
  apiBaseUrl?: string
  fetcher?: typeof fetch
}

export class GithubOnboardingRequestError extends Error {
  readonly status: number

  constructor(status: number, statusText: string) {
    super(`GitHub onboarding request failed with ${status} ${statusText}.`)
    this.name = "GithubOnboardingRequestError"
    this.status = status
  }
}

export class GithubOnboardingContractError extends Error {
  constructor() {
    super("GitHub onboarding response did not match the expected contract.")
    this.name = "GithubOnboardingContractError"
  }
}

export function getGithubOnboardingApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL
}

export function buildGithubOnboardingApiUrl(
  path: string,
  apiBaseUrl = getGithubOnboardingApiBaseUrl()
) {
  const normalizedBase = apiBaseUrl.replace(/\/+$/, "")
  const normalizedPath = path.startsWith("/") ? path : `/${path}`

  return `${normalizedBase}${normalizedPath}`
}

export function parseInstallationStart(input: unknown) {
  return v.parse(installationStartSchema, input)
}

export function parseOrganizationsResponse(input: unknown) {
  return v.parse(organizationsResponseSchema, input)
}

export function parseRepositoriesResponse(input: unknown) {
  return v.parse(repositoriesResponseSchema, input)
}

export async function fetchInstallationStart({
  apiBaseUrl,
  fetcher = fetch,
}: FetchOptions = {}) {
  return requestJson(
    "/github-app/installations/start/",
    parseInstallationStart,
    { apiBaseUrl, fetcher }
  )
}

export async function fetchOrganizations({
  apiBaseUrl,
  fetcher = fetch,
}: FetchOptions = {}) {
  return requestJson("/organizations/", parseOrganizationsResponse, {
    apiBaseUrl,
    fetcher,
  })
}

export async function fetchOrganizationRepositories(
  organizationId: string,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
) {
  return requestJson(
    `/organizations/${organizationId}/repositories/`,
    parseRepositoriesResponse,
    { apiBaseUrl, fetcher }
  )
}

async function requestJson<T>(
  path: string,
  parsePayload: (input: unknown) => T,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
): Promise<T> {
  const response = await fetcher(
    buildGithubOnboardingApiUrl(path, apiBaseUrl),
    {
      credentials: "include",
      headers: {
        Accept: "application/json",
      },
    }
  )

  if (!response.ok) {
    throw new GithubOnboardingRequestError(response.status, response.statusText)
  }

  let payload: unknown

  try {
    payload = await response.json()
  } catch {
    throw new GithubOnboardingContractError()
  }

  try {
    return parsePayload(payload)
  } catch {
    throw new GithubOnboardingContractError()
  }
}

export type InstallationStart = v.InferOutput<typeof installationStartSchema>
export type Organization = v.InferOutput<typeof organizationSchema>
export type ManagedRepository = v.InferOutput<typeof managedRepositorySchema>
export type OrganizationsResponse = v.InferOutput<
  typeof organizationsResponseSchema
>
export type RepositoriesResponse = v.InferOutput<
  typeof repositoriesResponseSchema
>
