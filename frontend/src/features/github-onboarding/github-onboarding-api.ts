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

const subscriptionSchema = v.object({
  id: v.string(),
  plan_code: v.string(),
  currency: v.string(),
  base_price_cents: v.number(),
  autonomous_pr_add_on_enabled: v.boolean(),
  autonomous_pr_add_on_price_cents: v.number(),
  created_at: v.string(),
  updated_at: v.string(),
})

const billingTotalsSchema = v.object({
  active_managed_repository_count: v.number(),
  billable_repository_units: v.number(),
  base_subtotal_cents: v.number(),
  autonomous_pr_add_on_subtotal_cents: v.number(),
  monthly_estimate_cents: v.number(),
})

const billingRepositorySchema = v.object({
  id: v.string(),
  full_name: v.string(),
  billable_units: v.number(),
  base_monthly_cents: v.number(),
  complexity: repositoryComplexitySchema,
})

const billingPermissionsSchema = v.object({
  can_edit_add_on: v.boolean(),
  can_edit_plan_and_prices: v.boolean(),
})

const billingResponseSchema = v.object({
  organization: organizationSchema,
  subscription: subscriptionSchema,
  billing: billingTotalsSchema,
  repositories: v.array(billingRepositorySchema),
  permissions: billingPermissionsSchema,
})

type FetchOptions = {
  apiBaseUrl?: string
  fetcher?: typeof fetch
}

type RepositoryFetchOptions = FetchOptions & {
  refresh?: boolean
}

type BillingUpdatePayload = {
  autonomous_pr_add_on_enabled?: boolean
  plan_code?: string
  base_price_cents?: number
  autonomous_pr_add_on_price_cents?: number
}

const CSRF_COOKIE_NAME = "csrftoken"

export class GithubOnboardingRequestError extends Error {
  readonly status: number
  readonly code?: string

  constructor(status: number, statusText: string, code?: string) {
    super(`GitHub onboarding request failed with ${status} ${statusText}.`)
    this.name = "GithubOnboardingRequestError"
    this.status = status
    this.code = code
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

export function isGithubOnboardingAuthenticationRequired(error: unknown) {
  return (
    error instanceof GithubOnboardingRequestError &&
    error.status === 403 &&
    error.code === "not_authenticated"
  )
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

export function parseBillingResponse(input: unknown) {
  return v.parse(billingResponseSchema, input)
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
  { apiBaseUrl, fetcher = fetch, refresh = false }: RepositoryFetchOptions = {}
) {
  const refreshQuery = refresh ? "?refresh=1" : ""
  return requestJson(
    `/organizations/${organizationId}/repositories/${refreshQuery}`,
    parseRepositoriesResponse,
    { apiBaseUrl, fetcher }
  )
}

export async function deleteManagedRepository(
  organizationId: string,
  repositoryId: string,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
) {
  return requestNoContent(
    `/organizations/${organizationId}/repositories/${repositoryId}/`,
    { apiBaseUrl, fetcher, method: "DELETE" }
  )
}

export async function fetchOrganizationBilling(
  organizationId: string,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
) {
  return requestJson(
    `/organizations/${organizationId}/billing/`,
    parseBillingResponse,
    { apiBaseUrl, fetcher }
  )
}

export async function updateOrganizationBilling(
  organizationId: string,
  payload: BillingUpdatePayload,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
) {
  return requestJson(
    `/organizations/${organizationId}/billing/`,
    parseBillingResponse,
    {
      apiBaseUrl,
      body: payload,
      fetcher,
      method: "PATCH",
    }
  )
}

async function requestJson<T>(
  path: string,
  parsePayload: (input: unknown) => T,
  {
    apiBaseUrl,
    body,
    fetcher = fetch,
    method = "GET",
  }: FetchOptions & {
    body?: unknown
    method?: "GET" | "PATCH"
  } = {}
): Promise<T> {
  const headers = requestHeaders(body, method)
  const response = await fetcher(
    buildGithubOnboardingApiUrl(path, apiBaseUrl),
    {
      body: body == null ? undefined : JSON.stringify(body),
      credentials: "include",
      headers,
      method,
    }
  )

  if (!response.ok) {
    throw new GithubOnboardingRequestError(
      response.status,
      response.statusText,
      await readErrorCode(response)
    )
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

async function requestNoContent(
  path: string,
  {
    apiBaseUrl,
    fetcher = fetch,
    method,
  }: FetchOptions & {
    method: "DELETE"
  }
): Promise<void> {
  const response = await fetcher(
    buildGithubOnboardingApiUrl(path, apiBaseUrl),
    {
      credentials: "include",
      headers: requestHeaders(undefined, method),
      method,
    }
  )

  if (!response.ok) {
    throw new GithubOnboardingRequestError(
      response.status,
      response.statusText,
      await readErrorCode(response)
    )
  }
}

async function readErrorCode(response: Response) {
  try {
    const payload: unknown = await response.clone().json()
    if (
      payload &&
      typeof payload === "object" &&
      "code" in payload &&
      typeof payload.code === "string"
    ) {
      return payload.code
    }
  } catch {
    return undefined
  }

  return undefined
}

function requestHeaders(body: unknown, method: "DELETE" | "GET" | "PATCH") {
  const headers: Record<string, string> = {
    Accept: "application/json",
  }
  if (body != null) {
    headers["Content-Type"] = "application/json"
  }
  if (method !== "GET") {
    const csrfToken = readCookie(CSRF_COOKIE_NAME)
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken
    }
  }
  return headers
}

function readCookie(name: string) {
  if (typeof document === "undefined") {
    return undefined
  }
  const cookiePrefix = `${name}=`
  return document.cookie
    .split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(cookiePrefix))
    ?.slice(cookiePrefix.length)
}

export type InstallationStart = v.InferOutput<typeof installationStartSchema>
export type Organization = v.InferOutput<typeof organizationSchema>
export type ManagedRepository = v.InferOutput<typeof managedRepositorySchema>
export type BillingResponse = v.InferOutput<typeof billingResponseSchema>
export type OrganizationsResponse = v.InferOutput<
  typeof organizationsResponseSchema
>
export type RepositoriesResponse = v.InferOutput<
  typeof repositoriesResponseSchema
>
