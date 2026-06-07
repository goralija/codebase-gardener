import * as v from "valibot"

import { buildGithubOnboardingApiUrl } from "@/features/github-onboarding/github-onboarding-api"

const CSRF_COOKIE_NAME = "csrftoken"

const autonomyModeSchema = v.picklist([
  "conservative",
  "assisted",
  "autonomous",
])

const repositoryAutomationPolicySchema = v.object({
  id: v.string(),
  autonomy_mode: autonomyModeSchema,
  manual_trigger_enabled: v.boolean(),
  scheduled_trigger_enabled: v.boolean(),
  commit_trigger_enabled: v.boolean(),
  risky_module_trigger_enabled: v.boolean(),
  pr_opened_trigger_enabled: v.boolean(),
  ci_failure_trigger_enabled: v.boolean(),
  commit_threshold: v.number(),
  created_at: v.string(),
  updated_at: v.string(),
})

const automationRepositorySchema = v.object({
  id: v.string(),
  full_name: v.string(),
  default_branch: v.string(),
  html_url: v.string(),
})

const automationBaselineSchema = v.object({
  analysis_id: v.nullable(v.string()),
  commit_sha: v.nullable(v.string()),
  source: v.nullable(v.string()),
  promoted_at: v.nullable(v.string()),
})

const automationStatsSchema = v.object({
  report_count: v.number(),
  session_count: v.number(),
  completed_session_count: v.number(),
  pr_plan_count: v.number(),
  created_pr_count: v.number(),
  merged_pr_count: v.number(),
  blocked_pr_count: v.number(),
  latest_report_at: v.nullable(v.string()),
})

const automationEffectiveSchema = v.object({
  autonomous_pr_add_on_enabled: v.boolean(),
  can_create_autonomous_prs: v.boolean(),
  pr_creation_status: v.string(),
  default_commit_threshold: v.number(),
  confidence_threshold: v.number(),
})

const automationPermissionsSchema = v.object({
  can_edit: v.boolean(),
  can_trigger_manual_session: v.boolean(),
})

const recentSessionSchema = v.object({
  id: v.string(),
  status: v.string(),
  trigger: v.record(v.string(), v.unknown()),
  baseline_analysis_id: v.nullable(v.string()),
  current_analysis_id: v.nullable(v.string()),
  current_commit_sha: v.nullable(v.string()),
  has_drift_report: v.boolean(),
  created_at: v.string(),
  started_at: v.nullable(v.string()),
  finished_at: v.nullable(v.string()),
  last_error: v.string(),
})

const recentPrPlanSchema = v.object({
  id: v.string(),
  title: v.string(),
  blocked: v.boolean(),
  block_reason: v.nullable(v.string()),
  approval_status: v.string(),
  execution_status: v.string(),
  created_pr_url: v.nullable(v.string()),
  terminal_outcome: v.nullable(v.string()),
  terminal_outcome_at: v.nullable(v.string()),
  confidence: v.number(),
  confidence_threshold: v.number(),
  created_at: v.string(),
})

const repositoryAutomationResponseSchema = v.object({
  schema_version: v.literal("1.0"),
  repository: automationRepositorySchema,
  baseline: automationBaselineSchema,
  stats: automationStatsSchema,
  policy: repositoryAutomationPolicySchema,
  effective: automationEffectiveSchema,
  permissions: automationPermissionsSchema,
  recent_sessions: v.array(recentSessionSchema),
  recent_pr_plans: v.array(recentPrPlanSchema),
})

const triggerResponseSchema = v.object({
  trigger: v.object({
    gardening_session_id: v.string(),
    status: v.string(),
    deduped: v.boolean(),
  }),
})

type FetchOptions = {
  apiBaseUrl?: string
  fetcher?: typeof fetch
}

export type RepositoryAutomationUpdatePayload = Partial<
  Pick<
    RepositoryAutomationPolicy,
    | "autonomy_mode"
    | "manual_trigger_enabled"
    | "scheduled_trigger_enabled"
    | "commit_trigger_enabled"
    | "risky_module_trigger_enabled"
    | "pr_opened_trigger_enabled"
    | "ci_failure_trigger_enabled"
    | "commit_threshold"
  >
>

export class AutomationRequestError extends Error {
  readonly status: number

  constructor(status: number, statusText: string) {
    super(`Automation request failed with ${status} ${statusText}.`)
    this.name = "AutomationRequestError"
    this.status = status
  }
}

export class AutomationContractError extends Error {
  constructor() {
    super("Automation response did not match the expected contract.")
    this.name = "AutomationContractError"
  }
}

export function parseRepositoryAutomationResponse(input: unknown) {
  return v.parse(repositoryAutomationResponseSchema, input)
}

export async function fetchRepositoryAutomation(
  organizationId: string,
  repositoryId: string,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
) {
  return requestJson(
    `/organizations/${organizationId}/repositories/${repositoryId}/automation/`,
    parseRepositoryAutomationResponse,
    { apiBaseUrl, fetcher }
  )
}

export async function updateRepositoryAutomation(
  organizationId: string,
  repositoryId: string,
  payload: RepositoryAutomationUpdatePayload,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
) {
  return requestJson(
    `/organizations/${organizationId}/repositories/${repositoryId}/automation/`,
    parseRepositoryAutomationResponse,
    {
      apiBaseUrl,
      body: payload,
      fetcher,
      method: "PATCH",
    }
  )
}

export async function triggerRepositorySession(
  organizationId: string,
  repositoryId: string,
  { apiBaseUrl, fetcher = fetch }: FetchOptions = {}
) {
  return requestJson(
    `/organizations/${organizationId}/repositories/${repositoryId}/automation/trigger/`,
    (input) => v.parse(triggerResponseSchema, input),
    {
      apiBaseUrl,
      body: {},
      fetcher,
      method: "POST",
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
    method?: "GET" | "PATCH" | "POST"
  } = {}
): Promise<T> {
  const response = await fetcher(
    buildGithubOnboardingApiUrl(path, apiBaseUrl),
    {
      body: body == null ? undefined : JSON.stringify(body),
      credentials: "include",
      headers: requestHeaders(body),
      method,
    }
  )

  if (!response.ok) {
    throw new AutomationRequestError(response.status, response.statusText)
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new AutomationContractError()
  }

  try {
    return parsePayload(payload)
  } catch {
    throw new AutomationContractError()
  }
}

function requestHeaders(body: unknown) {
  const headers: Record<string, string> = {
    Accept: "application/json",
  }
  if (body != null) {
    headers["Content-Type"] = "application/json"
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

export type AutonomyMode = v.InferOutput<typeof autonomyModeSchema>
export type RepositoryAutomationPolicy = v.InferOutput<
  typeof repositoryAutomationPolicySchema
>
export type RepositoryAutomationResponse = v.InferOutput<
  typeof repositoryAutomationResponseSchema
>
