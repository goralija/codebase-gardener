/* ============================================================
   Cockpit domain model — normalises real API payloads into the
   shapes the ported design components consume. No mock data.
   ============================================================ */
import type { FirstReport } from "@/features/first-report/first-report-contract"
import type {
  ManagedRepository,
  Organization,
} from "@/features/github-onboarding/github-onboarding-api"
import type { RepositoryAutomationResponse } from "@/features/automation/automation-api"
import { pct, riskFromTier } from "@/cockpit/format"

export type AutonomyMode = "conservative" | "assisted" | "autonomous"

export const AUTONOMY: Record<
  AutonomyMode,
  { label: string; desc: string; impact: string; color: string }
> = {
  assisted: {
    color: "blue",
    desc: "Human-led PRs",
    impact:
      "Drafts focused PR plans for maintainer review. Opens nothing automatically.",
    label: "Assisted",
  },
  autonomous: {
    color: "teal",
    desc: "Focused PRs",
    impact:
      "Opens focused, verified PRs above the confidence floor for allowed fixes only.",
    label: "Autonomous",
  },
  conservative: {
    color: "slate",
    desc: "Reports only",
    impact: "Analyzes and reports. Never opens pull requests.",
    label: "Conservative",
  },
}

export type EntropyComponentKey =
  | "testing"
  | "knowledge"
  | "dependency"
  | "operational"
  | "architecture"
  | "maintainability"

export const COMPONENTS: {
  key: EntropyComponentKey
  label: string
  icon: string
  desc: string
}[] = [
  {
    desc: "Coverage, flaky tests, untested critical paths",
    icon: "FlaskConical",
    key: "testing",
    label: "Testing",
  },
  {
    desc: "Docs coverage, bus factor, stale ADRs",
    icon: "BookOpen",
    key: "knowledge",
    label: "Knowledge",
  },
  {
    desc: "Outdated, vulnerable, or duplicated deps",
    icon: "Boxes",
    key: "dependency",
    label: "Dependency",
  },
  {
    desc: "CI health, build flakiness, deploy friction",
    icon: "Activity",
    key: "operational",
    label: "Operational",
  },
  {
    desc: "Coupling, cyclic deps, boundary erosion",
    icon: "Network",
    key: "architecture",
    label: "Architecture",
  },
  {
    desc: "Complexity, churn hotspots, dead code",
    icon: "Wrench",
    key: "maintainability",
    label: "Maintainability",
  },
]

export const TRIGGERS: {
  key: string
  label: string
  icon: string
  desc: string
  field: keyof RepositoryAutomationResponse["policy"]
}[] = [
  {
    desc: "On-demand sessions",
    field: "manual_trigger_enabled",
    icon: "Play",
    key: "manual",
    label: "Manual run",
  },
  {
    desc: "Periodic repository pass",
    field: "scheduled_trigger_enabled",
    icon: "CalendarClock",
    key: "scheduled",
    label: "Scheduled",
  },
  {
    desc: "After N commits",
    field: "commit_trigger_enabled",
    icon: "GitCommitHorizontal",
    key: "after-commits",
    label: "Commit threshold",
  },
  {
    desc: "Protected-area changes",
    field: "risky_module_trigger_enabled",
    icon: "ShieldAlert",
    key: "risky-module",
    label: "Risky module",
  },
  {
    desc: "Pull request activity",
    field: "pr_opened_trigger_enabled",
    icon: "GitPullRequest",
    key: "pr-opened",
    label: "PR opened",
  },
  {
    desc: "Failed workflow activity",
    field: "ci_failure_trigger_enabled",
    icon: "TriangleAlert",
    key: "ci-failure",
    label: "CI failure",
  },
]

export const CAT_ICON: Record<string, string> = {
  architecture: "Network",
  dependency: "Boxes",
  dependency_patch: "Boxes",
  docs: "BookOpen",
  generated_refresh: "RefreshCw",
  knowledge: "BookOpen",
  lint_format: "Wrench",
  maintainability: "Wrench",
  operational: "Activity",
  refactoring: "Wrench",
  testing: "FlaskConical",
  tests: "FlaskConical",
}

export const STATUS_TONE: Record<string, string> = {
  blocked: "amber",
  closed: "slate",
  completed: "green",
  draft: "slate",
  failed: "red",
  merged: "green",
  never: "slate",
  open: "blue",
  pending: "slate",
  queued: "slate",
  ready: "teal",
  reverted: "red",
  running: "teal",
}

export const STATUS_ICON: Record<string, string> = {
  blocked: "Ban",
  closed: "CircleX",
  completed: "CircleCheck",
  failed: "CircleX",
  merged: "GitMerge",
  open: "GitPullRequest",
  ready: "CircleDot",
  reverted: "RotateCcw",
  running: "Loader",
}

export type RepoModel = {
  id: string
  name: string
  fullName: string
  ownerLogin: string
  branch: string
  isPrivate: boolean
  htmlUrl: string
  loc: number | null
  modules: number | null
  contributors: number | null
  multiplier: number
  autonomy: AutonomyMode
  baseSha: string | null
  hasBaseline: boolean
  lastReportAt: string | null
  scanStatus: "ok" | "failed" | "never"
  stats: RepositoryAutomationResponse["stats"] | null
  effective: RepositoryAutomationResponse["effective"] | null
  policy: RepositoryAutomationResponse["policy"] | null
}

export function toRepoModel(
  repo: ManagedRepository,
  automation?: RepositoryAutomationResponse
): RepoModel {
  const sessions = automation?.recent_sessions ?? []
  const latestSession = sessions[0]
  const hasBaseline = Boolean(automation?.baseline.commit_sha)
  const lastReportAt = automation?.stats.latest_report_at ?? null
  const scanStatus: RepoModel["scanStatus"] =
    latestSession?.status === "failed"
      ? "failed"
      : lastReportAt
        ? "ok"
        : "never"

  return {
    autonomy: (automation?.policy.autonomy_mode as AutonomyMode) ?? "conservative",
    baseSha: automation?.baseline.commit_sha ?? null,
    branch: repo.default_branch || "—",
    contributors: repo.complexity.contributor_count,
    effective: automation?.effective ?? null,
    fullName: repo.full_name,
    hasBaseline,
    htmlUrl: repo.html_url,
    id: repo.id,
    isPrivate: repo.private,
    lastReportAt,
    loc: repo.complexity.loc,
    modules: repo.complexity.module_count,
    multiplier: repo.complexity.multiplier,
    name: repo.name,
    ownerLogin: repo.owner_login,
    policy: automation?.policy ?? null,
    scanStatus,
    stats: automation?.stats ?? null,
  }
}

export type EntropyModel = {
  overall: number
  classification: string
  components: Record<EntropyComponentKey, number>
  forecast: string
  commitSha: string
  scopes: FirstReport["entropy_report"]["scopes"]
}

export function entropyFromReport(report: FirstReport): EntropyModel {
  const score = report.entropy_report.score
  return {
    classification: score.classification,
    commitSha: report.entropy_report.commit_sha,
    components: score.components,
    forecast: report.entropy_report.forecast.summary,
    overall: Math.round(score.overall),
    scopes: report.entropy_report.scopes,
  }
}

export type SystemModel = {
  name: string
  files: number
  entropy: number | null
  protected: boolean
}

export function systemsFromReport(report: FirstReport): SystemModel[] {
  const scopeByName = new Map(
    report.entropy_report.scopes.map((s) => [s.name, s.overall])
  )
  const protectedPaths = report.repository_constitution.protected_modules.flatMap(
    (m) => m.paths
  )
  return report.analysis_snapshot.logical_systems.map((sys) => {
    const isProtected = sys.paths.some((p) =>
      protectedPaths.some((pp) => pp.startsWith(p) || p.startsWith(pp))
    )
    const entropy = scopeByName.get(sys.name)
    return {
      entropy: entropy == null ? null : Math.round(entropy),
      files: sys.paths.length,
      name: sys.name,
      protected: isProtected,
    }
  })
}

export type ConstitutionModel = {
  present: boolean
  coverage: number
  protected: { name: string; paths: string[]; reason: string }[]
  neverTouch: { path: string; reason: string }[]
  allowed: string[]
  questions: { id: string; question: string; severity: string }[]
}

export function constitutionFromReport(report: FirstReport): ConstitutionModel {
  const c = report.repository_constitution
  const allowed = [
    ...c.allowed_fixes.autonomous,
    ...c.allowed_fixes.assisted,
    ...c.allowed_fixes.advisory,
  ]
  const present =
    c.completeness_score > 0 ||
    c.protected_modules.length > 0 ||
    allowed.length > 0
  return {
    allowed,
    coverage: pct(c.completeness_score) ?? 0,
    neverTouch: c.never_touch,
    present,
    protected: c.protected_modules,
    questions: c.open_questions.map((q) => ({
      id: q.question_id,
      question: q.question,
      severity: q.severity,
    })),
  }
}

export type OppModel = {
  id: string
  repoId: string
  title: string
  summary: string
  category: string
  risk: string
  confidence: number
  status: "ready" | "blocked"
  paths: string[]
  evidence: string
  verify: string[]
  blocked: string | null
  entropyDelta: number
}

export function oppsFromReport(report: FirstReport): OppModel[] {
  return report.maintenance_opportunities.map((o) => {
    const blocked = o.blocked_by.length > 0 ? o.blocked_by.join("; ") : null
    const evidence =
      o.evidence.map((e) => e.summary).filter(Boolean).join(" ") || o.summary
    return {
      blocked,
      category: o.category,
      confidence: pct(o.confidence) ?? 0,
      entropyDelta: o.expected_entropy_delta,
      evidence,
      id: o.maintenance_opportunity_id,
      paths: o.affected_paths,
      repoId: o.repository_id,
      risk: riskFromTier(o.risk_tier),
      status: blocked ? "blocked" : "ready",
      summary: o.summary,
      title: o.title,
      verify: o.required_checks,
    } as OppModel
  })
}

export type PlanModel = {
  id: string
  repoId: string
  title: string
  status: string
  confidence: number
  risk: string
  category: string
  paths: string[]
  checks: string[]
  blocked: string | null
  evidence: string
  branch: string
  prUrl: string | null
}

export function plansFromReport(report: FirstReport): PlanModel[] {
  const oppCategory = new Map(
    report.maintenance_opportunities.map((o) => [
      o.maintenance_opportunity_id,
      o.category,
    ])
  )
  return report.maintenance_pr_plans.map((p) => {
    const status = p.blocked
      ? "blocked"
      : p.terminal_outcome
        ? p.terminal_outcome
        : "ready"
    const category =
      p.maintenance_opportunity_ids
        .map((id) => oppCategory.get(id))
        .find(Boolean) ?? "maintainability"
    return {
      blocked: p.block_reason,
      branch: p.branch_name,
      category,
      checks: p.required_checks,
      confidence: pct(p.confidence) ?? 0,
      evidence: p.pr_body_sections.evidence,
      id: p.maintenance_pr_plan_id,
      paths: p.changed_paths,
      prUrl: null,
      repoId: p.repository_id,
      risk: riskFromTier(p.risk_tier),
      status,
      title: p.title,
    }
  })
}

export type SessionModel = {
  id: string
  repoId: string
  status: string
  trigger: string
  startedAt: string | null
  finishedAt: string | null
  commitSha: string | null
  lastError: string
}

export function sessionsFromAutomation(
  automation: RepositoryAutomationResponse
): SessionModel[] {
  return automation.recent_sessions.map((s) => {
    const triggerRecord = s.trigger as Record<string, unknown>
    const trigger =
      (triggerRecord.type as string) ||
      (triggerRecord.kind as string) ||
      (triggerRecord.source as string) ||
      "manual"
    return {
      commitSha: s.current_commit_sha,
      finishedAt: s.finished_at,
      id: s.id,
      lastError: s.last_error,
      repoId: automation.repository.id,
      startedAt: s.started_at ?? s.created_at,
      status: s.status,
      trigger,
    }
  })
}

export function plansFromAutomation(
  automation: RepositoryAutomationResponse
): PlanModel[] {
  return automation.recent_pr_plans.map((p) => {
    const status = p.blocked
      ? "blocked"
      : p.terminal_outcome
        ? p.terminal_outcome
        : p.created_pr_url
          ? "open"
          : "ready"
    return {
      blocked: p.block_reason,
      branch: "",
      category: "maintainability",
      checks: [],
      confidence: pct(p.confidence) ?? 0,
      evidence: "",
      id: p.id,
      paths: [],
      prUrl: p.created_pr_url,
      repoId: automation.repository.id,
      risk: "low",
      status,
      title: p.title,
    }
  })
}

export const TRIGGER_LABEL: Record<string, string> = {
  "after-commits": "Commit threshold",
  ci_failure: "CI failure",
  "ci-failure": "CI failure",
  commit_threshold: "Commit threshold",
  first_scan: "First scan",
  manual: "Manual",
  pr_opened: "PR opened",
  "pr-opened": "PR opened",
  "risky-module": "Risky module",
  risky_module: "Risky module",
  scheduled: "Scheduled",
}

export type OrgModel = Organization
