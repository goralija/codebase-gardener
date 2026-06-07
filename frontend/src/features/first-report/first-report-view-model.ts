import type { FirstReport } from "./first-report-contract"

export type FirstReportFixture = FirstReport

function titleCase(value: string) {
  return value
    .split(/[_-]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

function formatScore(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

export function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`
}

export function formatEntropyDelta(value: number) {
  if (value === 0) {
    return "0"
  }

  const absolute = Math.abs(value)
  const formatted = Number.isInteger(absolute)
    ? String(absolute)
    : absolute.toFixed(1)

  return `${value > 0 ? "+" : "-"}${formatted}`
}

export function formatDuration(startedAt: string, finishedAt: string) {
  const started = new Date(startedAt).getTime()
  const finished = new Date(finishedAt).getTime()

  if (!Number.isFinite(started) || !Number.isFinite(finished)) {
    return "Unknown duration"
  }

  const seconds = Math.max(0, Math.round((finished - started) / 1000))

  if (seconds < 60) {
    return `${seconds} sec`
  }

  const minutes = Math.round(seconds / 60)

  return `${minutes} min`
}

export function buildFirstReportViewModel(report: FirstReport) {
  const constitution = report.repository_constitution
  const snapshot = report.analysis_snapshot
  const entropy = report.entropy_report
  const session = report.gardening_session_result
  const dependencyCycles = snapshot.signals.dependency_cycles
  const architectureBoundaryRules = constitution.architecture_boundaries
  const architectureViolationCount = dependencyCycles.length

  return {
    repository: {
      id: entropy.repository_id,
      commitSha: entropy.commit_sha,
      shortCommitSha: entropy.commit_sha.slice(0, 12),
      analyzedAt: snapshot.created_at,
    },
    entropy: {
      overall: formatScore(entropy.score.overall),
      classification: titleCase(entropy.score.classification),
      components: Object.entries(entropy.score.components).map(
        ([name, value]) => ({
          name: titleCase(name),
          value: formatScore(value),
        })
      ),
      forecast: {
        horizonDays: entropy.forecast.horizon_days,
        predictedOverall: formatScore(entropy.forecast.predicted_overall),
        confidence: formatConfidence(entropy.forecast.confidence),
        summary: entropy.forecast.summary,
      },
      topContributorCount: entropy.top_contributors.length,
      topContributors: entropy.top_contributors.map((contributor, index) => ({
        id: `${contributor.kind}-${index}`,
        kind: titleCase(contributor.kind),
        summary: contributor.summary,
        impact: formatScore(contributor.impact),
        evidenceCount: contributor.evidence.length,
        evidence: contributor.evidence.map((evidence, evidenceIndex) => ({
          id: `${evidence.path}-${evidenceIndex}`,
          path: evidence.path,
          summary: evidence.summary,
        })),
      })),
    },
    logicalSystems: snapshot.logical_systems.map((system) => ({
      id: system.logical_system_id,
      name: system.name,
      paths: system.paths,
    })),
    architecture: {
      dependencyCycleCount: dependencyCycles.length,
      boundaryRuleCount: architectureBoundaryRules.length,
      violationCount: architectureViolationCount,
      hasViolations: architectureViolationCount > 0,
    },
    constitution: {
      completeness: formatConfidence(constitution.completeness_score),
      openQuestionCount: constitution.open_questions.length,
      hasOpenQuestions: constitution.open_questions.length > 0,
      openQuestions: constitution.open_questions.map((question) => ({
        id: question.question_id,
        severity: titleCase(question.severity),
        question: question.question,
        evidenceCount: question.evidence.length,
        evidence: question.evidence.map((evidence, evidenceIndex) => ({
          id: `${evidence.path}-${evidenceIndex}`,
          path: evidence.path,
          summary: evidence.summary,
        })),
      })),
      protectedModules: constitution.protected_modules,
      neverTouch: constitution.never_touch,
      ignoredPaths: constitution.ignored_paths,
      allowedFixes: constitution.allowed_fixes,
    },
    session: {
      id: session.gardening_session_id,
      status: titleCase(session.status),
      trigger: titleCase(session.trigger.type),
      actor: session.trigger.actor ?? "system",
      duration: formatDuration(session.started_at, session.finished_at),
      phaseResults: session.phase_results.map((phase) => ({
        phase: titleCase(phase.phase),
        status: titleCase(phase.status),
        summary: phase.summary,
      })),
      selectedCount: session.opportunities_selected.length,
      deferredCount: session.opportunities_deferred.length,
      prPlanCount: session.maintenance_pr_plans.length,
      errorCount: session.errors.length,
    },
    opportunities: report.maintenance_opportunities.map((opportunity) => ({
      id: opportunity.maintenance_opportunity_id,
      category: titleCase(opportunity.category),
      riskTier: titleCase(opportunity.risk_tier),
      confidence: formatConfidence(opportunity.confidence),
      title: opportunity.title,
      summary: opportunity.summary,
      affectedPaths: opportunity.affected_paths,
      blockedCount: opportunity.blocked_by.length,
      expectedEntropyDelta: formatEntropyDelta(
        opportunity.expected_entropy_delta
      ),
      requiredChecks: opportunity.required_checks,
      evidenceCount: opportunity.evidence.length,
    })),
    prPlans: report.maintenance_pr_plans.map((plan) => ({
      id: plan.maintenance_pr_plan_id,
      title: plan.title,
      branchName: plan.branch_name,
      riskTier: titleCase(plan.risk_tier),
      confidence: formatConfidence(plan.confidence),
      changedPaths: plan.changed_paths,
      bodySections: plan.pr_body_sections,
      requiredChecks: plan.required_checks,
      blocked: plan.blocked,
      blockReason: plan.block_reason,
    })),
  }
}

export type FirstReportViewModel = ReturnType<typeof buildFirstReportViewModel>
