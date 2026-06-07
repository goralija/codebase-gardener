/* ============================================================
   Repository detail — tabbed report (Summary / Entropy /
   Constitution / Opportunities / Sessions / PR Plans / Automation).
   ============================================================ */
/* eslint-disable react-refresh/only-export-components */
import { useMemo } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { entColor, fmt, relTime, shortTime } from "@/cockpit/format"
import {
  cancelRepositorySession,
  triggerRepositorySession,
} from "@/features/automation/automation-api"
import { deleteManagedRepository } from "@/features/github-onboarding/github-onboarding-api"
import {
  useAutomation,
  useRepoReport,
  useRepositories,
  useSelectedOrganization,
} from "@/cockpit/data"
import {
  COMPONENTS,
  constitutionFromReport,
  entropyFromReport,
  oppsFromReport,
  plansFromReport,
  sessionsFromAutomation,
  systemsFromReport,
  toRepoModel,
  TRIGGER_LABEL,
  type RepoModel,
} from "@/cockpit/model"
import {
  AutonomyBadge,
  Badge,
  Delta,
  Empty,
  EntropyBadge,
  EntropyGauge,
  Radar,
  RepoDot,
} from "@/cockpit/primitives"
import { AutomationPanel } from "@/cockpit/pages/automation"
import {
  OpportunitiesView,
  PullsView,
  SessionsView,
} from "@/cockpit/pages/shared-lists"
import type { FirstReport } from "@/features/first-report/first-report-contract"

const REPO_TABS = [
  { icon: "LayoutPanelTop", id: "summary", label: "Summary" },
  { icon: "Gauge", id: "entropy", label: "Entropy" },
  { icon: "ScrollText", id: "constitution", label: "Constitution" },
  { icon: "Sparkles", id: "opportunities", label: "Opportunities" },
  { icon: "TerminalSquare", id: "sessions", label: "Sessions" },
  { icon: "GitPullRequest", id: "prplans", label: "PR Plans" },
  { icon: "SlidersHorizontal", id: "automation", label: "Automation" },
  { icon: "Settings", id: "settings", label: "Settings" },
]

export function RepoDetailPage({
  repoId,
  tab = "summary",
}: {
  repoId: string
  tab?: string
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { organization } = useSelectedOrganization()
  const repositoriesQuery = useRepositories(organization?.id)
  const repository = repositoriesQuery.data?.repositories.find(
    (r) => r.id === repoId
  )
  const automationQuery = useAutomation(organization?.id, repoId)
  const reportQuery = useRepoReport(repoId)

  const trigger = useMutation({
    mutationFn: () => triggerRepositorySession(organization?.id ?? "", repoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cockpit", "automation"] })
      queryClient.invalidateQueries({ queryKey: ["cockpit", "report", repoId] })
    },
  })

  const removeRepo = useMutation({
    mutationFn: () => deleteManagedRepository(organization?.id ?? "", repoId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["cockpit", "repositories", organization?.id],
      })
      navigate({ to: "/repos" })
    },
  })

  const cancel = useMutation({
    mutationFn: (sessionId: string) =>
      cancelRepositorySession(organization?.id ?? "", repoId, sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cockpit", "automation"] })
      queryClient.invalidateQueries({ queryKey: ["cockpit", "report", repoId] })
    },
  })

  const model = useMemo(
    () => (repository ? toRepoModel(repository, automationQuery.data) : null),
    [repository, automationQuery.data]
  )

  if (!repository || !model) {
    if (repositoriesQuery.isLoading) {
      return (
        <div className="page wide">
          <div className="card">
            <Empty icon="Loader" title="Loading repository…" />
          </div>
        </div>
      )
    }
    return (
      <div className="page wide">
        <div className="card">
          <Empty icon="FolderGit2" title="Repository not found" />
        </div>
      </div>
    )
  }

  const report = reportQuery.data ?? null
  const setTab = (t: string) =>
    navigate({
      params: { repoId },
      search: { tab: t },
      to: "/repo/$repoId",
    } as never)

  const curSha = report?.entropy_report.commit_sha ?? model.baseSha
  const activeSession =
    automationQuery.data?.recent_sessions.find((session) =>
      ["queued", "running"].includes(session.status)
    ) ?? null
  const activeSessionProgress = activeSession?.progress
  const activeSessionMessage =
    activeSessionProgress?.message ||
    (activeSession?.status === "running"
      ? "Hosted worker is running this session."
      : "Session queued. Waiting for hosted worker.")
  const shouldShowSessionProgress = Boolean(activeSession || trigger.isSuccess)

  return (
    <div className="page wide">
      <div className="phead" style={{ marginBottom: 16 }}>
        <div style={{ minWidth: 0 }}>
          <div className="ph-eyebrow row gap6">
            <a
              className="muted"
              onClick={() => navigate({ to: "/repos" })}
              style={{ cursor: "pointer" }}
            >
              Repositories
            </a>
            <Icon name="ChevronRight" size={12} />
            <RepoDot
              color={entColor(
                report ? entropyFromReport(report).overall : undefined
              )}
            />
            <span
              className="mono"
              style={{ letterSpacing: 0, textTransform: "none" }}
            >
              @{model.ownerLogin}
            </span>
          </div>
          <h1 className="mono" style={{ fontWeight: 600 }}>
            {model.name}
          </h1>
          <div className="row gap10 mt12 wrap">
            <span className="pill mono">
              <Icon name="GitBranch" size={11} />
              {model.branch}
            </span>
            <AutonomyBadge mode={model.autonomy} />
            <EntropyBadge
              score={report ? entropyFromReport(report).overall : null}
            />
            {model.scanStatus === "failed" && (
              <Badge icon="CircleX" tone="red">
                last scan failed
              </Badge>
            )}
          </div>
        </div>
        <div className="ph-actions">
          <button
            className="btn"
            onClick={() => setTab("automation")}
            type="button"
          >
            <Icon name="SlidersHorizontal" size={15} />
            Automation
          </button>
          <a
            className="btn"
            href={model.htmlUrl}
            rel="noreferrer"
            target="_blank"
          >
            <Icon name="ExternalLink" size={14} />
            GitHub
          </a>
          <button
            className="btn primary"
            disabled={
              trigger.isPending ||
              !automationQuery.data?.permissions.can_trigger_manual_session
            }
            onClick={() => trigger.mutate()}
            type="button"
          >
            <Icon
              className={trigger.isPending ? "spin" : ""}
              name={trigger.isPending ? "Loader" : "Play"}
              size={15}
            />
            {trigger.isPending
              ? "Starting…"
              : model.hasBaseline
                ? "Run session"
                : "Run first scan"}
          </button>
        </div>
      </div>

      {shouldShowSessionProgress && (
        <div
          className="card pad mb20"
          style={{
            background: "var(--accent-bg)",
            borderColor: "var(--accent-bd)",
          }}
        >
          <div className="row gap10" style={{ alignItems: "flex-start" }}>
            <Icon
              className={activeSession?.status === "running" ? "spin" : ""}
              color="var(--accent-2)"
              name={activeSession?.status === "running" ? "Loader" : "CircleCheck"}
              size={16}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="sm fg2">{activeSessionMessage}</div>
              <div className="row gap6 mt8 wrap tiny muted">
                <span className="mono">
                  {activeSessionProgress?.phase || activeSession?.status || "queued"}
                </span>
                {activeSessionProgress?.event && (
                  <>
                    <span>·</span>
                    <span className="mono">{activeSessionProgress.event}</span>
                  </>
                )}
                {activeSessionProgress?.updated_at && (
                  <>
                    <span>·</span>
                    <span>{relTime(activeSessionProgress.updated_at)}</span>
                  </>
                )}
              </div>
              {cancel.isError && (
                <div className="tiny mt8" style={{ color: "var(--red)" }}>
                  Could not stop the session. Try again.
                </div>
              )}
            </div>
            {activeSession &&
              automationQuery.data?.permissions.can_trigger_manual_session && (
                <button
                  className="btn"
                  disabled={cancel.isPending}
                  onClick={() => cancel.mutate(activeSession.id)}
                  type="button"
                >
                  <Icon
                    className={cancel.isPending ? "spin" : ""}
                    name={cancel.isPending ? "Loader" : "Square"}
                    size={14}
                  />
                  {cancel.isPending ? "Stopping…" : "Stop session"}
                </button>
              )}
          </div>
        </div>
      )}

      <div
        className="card mb20"
        style={{
          background: "var(--border)",
          display: "grid",
          gap: 1,
          gridTemplateColumns: "repeat(auto-fit, minmax(132px, 1fr))",
          overflow: "hidden",
        }}
      >
        {[
          {
            l: "Baseline",
            mono: true,
            tone: model.hasBaseline ? null : "var(--amber)",
            v: model.hasBaseline ? model.baseSha?.slice(0, 7) : "not promoted",
          },
          { l: "Current", mono: true, v: curSha?.slice(0, 7) ?? "—" },
          {
            l: "Last scan",
            tone: model.scanStatus === "failed" ? "var(--red)" : null,
            v: model.lastReportAt ? shortTime(model.lastReportAt) : "never",
          },
          { l: "LOC", mono: true, v: fmt(model.loc) },
          { l: "Modules", mono: true, v: model.modules ?? "—" },
          { l: "Contributors", mono: true, v: model.contributors ?? "—" },
          { l: "Complexity", mono: true, v: model.multiplier.toFixed(2) + "×" },
        ].map((c) => (
          <div
            key={c.l}
            style={{ background: "var(--panel)", padding: "13px 18px" }}
          >
            <div
              className="tiny faint"
              style={{
                fontWeight: 600,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
              }}
            >
              {c.l}
            </div>
            <div
              className={c.mono ? "mono" : ""}
              style={{
                color: (c.tone as string) || "var(--fg)",
                fontSize: 13.5,
                fontWeight: 500,
                marginTop: 4,
              }}
            >
              {c.v}
            </div>
          </div>
        ))}
      </div>

      <div className="tabs">
        {REPO_TABS.map((tb) => (
          <button
            className={`tab${tab === tb.id ? " on" : ""}`}
            key={tb.id}
            onClick={() => setTab(tb.id)}
            type="button"
          >
            <Icon name={tb.icon} size={15} />
            {tb.label}
          </button>
        ))}
      </div>

      {reportQuery.isLoading && tab !== "automation" && tab !== "sessions" ? (
        <div className="card">
          <Empty icon="Loader" title="Loading report…" />
        </div>
      ) : (
        <RepoTab
          automation={automationQuery.data}
          model={model}
          onRemove={() => {
            if (
              window.confirm(
                `Permanently remove ${model.name} and all stored Gardener data for it? This cannot be undone.`
              )
            ) {
              removeRepo.mutate()
            }
          }}
          organizationId={organization?.id ?? ""}
          removeError={removeRepo.isError}
          removing={removeRepo.isPending}
          report={report}
          setTab={setTab}
          tab={tab}
        />
      )}
    </div>
  )
}

function RepoTab({
  tab,
  model,
  report,
  automation,
  organizationId,
  setTab,
  onRemove,
  removing,
  removeError,
}: {
  tab: string
  model: RepoModel
  report: FirstReport | null
  automation: ReturnType<typeof useAutomation>["data"]
  organizationId: string
  setTab: (t: string) => void
  onRemove: () => void
  removing: boolean
  removeError: boolean
}) {
  const repoName = () => model.name

  if (tab === "automation") {
    if (!automation) {
      return (
        <div className="card">
          <Empty icon="Loader" title="Loading automation…" />
        </div>
      )
    }
    return (
      <AutomationPanel
        automation={automation}
        organizationId={organizationId}
      />
    )
  }

  if (tab === "sessions") {
    const sessions = automation ? sessionsFromAutomation(automation) : []
    return (
      <SessionsView repoName={repoName} sessions={sessions} showRepo={false} />
    )
  }

  if (tab === "settings") {
    return (
      <div style={{ display: "grid", gap: 16 }}>
        <RemoveRepoCard
          onRemove={onRemove}
          removeError={removeError}
          removing={removing}
        />
      </div>
    )
  }

  if (!report) {
    return (
      <div className="card">
        <Empty
          action={
            <div className="row gap6 tiny muted mt8">
              <Icon name="ArrowUp" size={13} />
              Use <b className="fg2">Run first scan</b> in the header above
            </div>
          }
          icon="CircleDashed"
          sub="No analysis has been stored for this repository yet. Run the first scan to analyze code health and promote a baseline."
          title="No report yet"
        />
      </div>
    )
  }

  if (tab === "opportunities") {
    return (
      <OpportunitiesView
        opps={oppsFromReport(report, automation)}
        repoName={repoName}
        showRepo={false}
      />
    )
  }
  if (tab === "prplans") {
    return (
      <PullsView
        plans={plansFromReport(report, automation)}
        repoName={repoName}
        showRepo={false}
      />
    )
  }
  if (tab === "entropy") {
    return <RepoEntropy report={report} />
  }
  if (tab === "constitution") {
    return <RepoConstitution report={report} />
  }
  return <RepoSummary report={report} setTab={setTab} />
}

function RepoSummary({
  report,
  setTab,
}: {
  report: FirstReport
  setTab: (t: string) => void
}) {
  const entropy = entropyFromReport(report)
  const systems = systemsFromReport(report)
  const constitution = constitutionFromReport(report)
  const forecastDelta = Math.round(
    report.entropy_report.forecast.predicted_overall - entropy.overall
  )

  return (
    <div
      style={{
        alignItems: "start",
        display: "grid",
        gap: 16,
        gridTemplateColumns: "1.5fr 1fr",
      }}
    >
      <div style={{ display: "grid", gap: 16 }}>
        <div className="card pad">
          <div
            style={{
              alignItems: "center",
              display: "grid",
              gap: 24,
              gridTemplateColumns: "auto 1fr",
            }}
          >
            <EntropyGauge score={entropy.overall} size={150} />
            <div>
              <div className="sect-title mb8">Repository entropy score</div>
              <div className="row gap10 mb12 wrap">
                <EntropyBadge score={entropy.overall} />
                <span className="row gap6 sm muted">
                  forecast <Delta value={forecastDelta} />
                </span>
              </div>
              <p className="sm fg2" style={{ lineHeight: 1.55 }}>
                {entropy.forecast}
              </p>
              <button
                className="btn sm mt12"
                onClick={() => setTab("entropy")}
                type="button"
              >
                Component breakdown
                <Icon name="ArrowRight" size={13} />
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <Icon color="var(--fg-3)" name="Boxes" size={15} />
            <h3>Logical systems</h3>
            <span className="ch-sub">{systems.length}</span>
          </div>
          {systems.length === 0 ? (
            <div className="card-b">
              <div className="sm muted">No logical systems detected.</div>
            </div>
          ) : (
            <div
              className="tbl-wrap"
              style={{ border: "none", borderRadius: 0 }}
            >
              <table className="tbl">
                <tbody>
                  {systems.map((s) => (
                    <tr key={s.name}>
                      <td>
                        <span className="primary">{s.name}</span>
                      </td>
                      <td className="num muted">{s.files} paths</td>
                      <td style={{ width: 140 }}>
                        <div className="meter">
                          <span
                            style={{
                              background: entColor(s.entropy ?? undefined),
                              width: (s.entropy ?? 0) + "%",
                            }}
                          />
                        </div>
                      </td>
                      <td
                        className="num"
                        style={{
                          color: entColor(s.entropy ?? undefined),
                          fontWeight: 600,
                          width: 50,
                        }}
                      >
                        {s.entropy ?? "—"}
                      </td>
                      <td className="sm muted">
                        {s.protected && (
                          <span className="row gap6">
                            <Icon color="var(--amber)" name="Lock" size={11} />
                            Protected
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gap: 16 }}>
        <div className="card">
          <div className="card-h">
            <Icon color="var(--fg-3)" name="ScrollText" size={15} />
            <h3>Constitution</h3>
            <span className="spacer" />
            <button
              className="btn ghost sm"
              onClick={() => setTab("constitution")}
              type="button"
            >
              View
              <Icon name="ArrowRight" size={12} />
            </button>
          </div>
          <div className="card-b">
            {constitution.hasSourceTruth ? (
              <>
                <div
                  className="row"
                  style={{ justifyContent: "space-between" }}
                >
                  <span className="sm muted">Source-truth coverage</span>
                  <span
                    className="mono b6"
                    style={{
                      color:
                        constitution.coverage >= 80
                          ? "var(--green)"
                          : "var(--amber)",
                    }}
                  >
                    {constitution.coverage}%
                  </span>
                </div>
                <div className="meter mt8">
                  <span
                    style={{
                      background:
                        constitution.coverage >= 80
                          ? "var(--green)"
                          : "var(--amber)",
                      width: constitution.coverage + "%",
                    }}
                  />
                </div>
                <div
                  className="row mt16"
                  style={{ justifyContent: "space-between" }}
                >
                  <span className="sm muted">Protected modules</span>
                  <span className="mono fg2">
                    {constitution.protected.length}
                  </span>
                </div>
                <div
                  className="row mt8"
                  style={{ justifyContent: "space-between" }}
                >
                  <span className="sm muted">Open questions</span>
                  {constitution.questions.length > 0 ? (
                    <Badge tone="amber">{constitution.questions.length}</Badge>
                  ) : (
                    <span className="mono faint">0</span>
                  )}
                </div>
              </>
            ) : (
              <div className="row gap10 sm" style={{ color: "var(--blue)" }}>
                <Icon name="FileWarning" size={15} />
                No source truth — inferred mode
              </div>
            )}
          </div>
        </div>

        <div className="card pad">
          <div className="sect-title mb12">Maintenance</div>
          <button
            className="att mb8"
            onClick={() => setTab("opportunities")}
            style={{ borderLeftColor: "var(--accent)" }}
            type="button"
          >
            <div
              className="a-ico"
              style={{
                background: "var(--accent-bg)",
                color: "var(--accent-2)",
              }}
            >
              <Icon name="Sparkles" size={16} />
            </div>
            <div className="a-body">
              <div className="a-title">
                {report.maintenance_opportunities.length} opportunities
              </div>
              <div className="a-sub">detected candidates</div>
            </div>
            <Icon color="var(--fg-4)" name="ChevronRight" size={15} />
          </button>
          <button
            className="att"
            onClick={() => setTab("prplans")}
            style={{ borderLeftColor: "var(--blue)" }}
            type="button"
          >
            <div
              className="a-ico"
              style={{ background: "var(--blue-bg)", color: "var(--blue)" }}
            >
              <Icon name="GitPullRequest" size={16} />
            </div>
            <div className="a-body">
              <div className="a-title">
                {report.maintenance_pr_plans.length} PR plans
              </div>
              <div className="a-sub">planned &amp; terminal</div>
            </div>
            <Icon color="var(--fg-4)" name="ChevronRight" size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}

function RemoveRepoCard({
  onRemove,
  removing,
  removeError,
}: {
  onRemove: () => void
  removing: boolean
  removeError: boolean
}) {
  return (
    <div
      className="card pad"
      style={{ borderColor: "var(--red-bd, var(--border))" }}
    >
      <div className="sect-title mb8" style={{ color: "var(--red)" }}>
        Remove repository
      </div>
      <p className="sm muted mb12" style={{ lineHeight: 1.5 }}>
        Untie this repository from Codebase Gardener. Stored reports, sessions,
        and PR plans are permanently deleted. This does not uninstall the GitHub
        App.
      </p>
      {removeError && (
        <div className="row gap6 sm mb8" style={{ color: "var(--red)" }}>
          <Icon name="CircleX" size={14} />
          Could not remove repository. Try again.
        </div>
      )}
      <button
        className="btn"
        disabled={removing}
        onClick={onRemove}
        style={{
          borderColor: "var(--red-bd, var(--red))",
          color: "var(--red)",
        }}
        type="button"
      >
        <Icon
          className={removing ? "spin" : ""}
          name={removing ? "Loader" : "Trash2"}
          size={14}
        />
        {removing ? "Removing…" : "Untie repository"}
      </button>
    </div>
  )
}

function RepoEntropy({ report }: { report: FirstReport }) {
  const entropy = entropyFromReport(report)
  const forecastDelta = Math.round(
    report.entropy_report.forecast.predicted_overall - entropy.overall
  )
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "1fr 1fr" }}>
        <div
          className="card pad"
          style={{ display: "grid", gap: 14, placeItems: "center" }}
        >
          <EntropyGauge score={entropy.overall} size={190} />
          <div className="row gap10">
            <span className="sm muted">
              forecast {report.entropy_report.forecast.horizon_days}d
            </span>
            <Delta value={forecastDelta} />
          </div>
        </div>
        <div
          className="card pad"
          style={{ display: "grid", placeItems: "center" }}
        >
          <div className="sect-title" style={{ alignSelf: "flex-start" }}>
            Component radar
          </div>
          <Radar
            color={entColor(entropy.overall)}
            components={entropy.components}
            size={250}
          />
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <Icon color="var(--fg-3)" name="BarChart3" size={15} />
          <h3>Entropy components</h3>
          <span className="ch-sub">6 signals · higher = more risk</span>
        </div>
        <div
          className="card-b"
          style={{
            display: "grid",
            gap: "0 36px",
            gridTemplateColumns: "1fr 1fr",
          }}
        >
          {COMPONENTS.map((c) => {
            const v = entropy.components[c.key]
            const maxVal = Math.max(
              10,
              ...COMPONENTS.map((cc) => entropy.components[cc.key])
            )
            return (
              <div
                key={c.key}
                style={{
                  borderBottom: "1px solid var(--border)",
                  padding: "11px 0",
                }}
              >
                <div
                  className="row"
                  style={{ justifyContent: "space-between" }}
                >
                  <span className="row gap8 sm fg2">
                    <Icon color={entColor(v)} name={c.icon} size={14} />
                    {c.label}
                  </span>
                  <span className="mono b6" style={{ color: entColor(v) }}>
                    {v}
                  </span>
                </div>
                <div className="meter mt8">
                  <span
                    style={{
                      background: entColor(v),
                      width: Math.round((v / maxVal) * 100) + "%",
                    }}
                  />
                </div>
                <div className="tiny faint mt8">{c.desc}</div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <Icon color="var(--fg-3)" name="GitCompareArrows" size={15} />
          <h3>Forecast</h3>
          <span className="ch-sub">
            {report.entropy_report.forecast.horizon_days}d horizon
          </span>
        </div>
        <div className="card-b">
          <p className="sm fg2" style={{ lineHeight: 1.55 }}>
            {entropy.forecast}
          </p>
        </div>
      </div>
    </div>
  )
}

function RepoConstitution({ report }: { report: FirstReport }) {
  const c = constitutionFromReport(report)
  if (!c.hasSourceTruth) {
    return (
      <div className="card">
        <Empty
          icon="FileWarning"
          sub="This repository has no machine-readable Repository Constitution. Gardener runs in inferred mode with conservative defaults. Add source truth to declare protected modules, allowed fixes, and never-touch paths."
          title="No constitution source truth"
        />
      </div>
    )
  }
  return (
    <div
      style={{
        alignItems: "start",
        display: "grid",
        gap: 16,
        gridTemplateColumns: "1fr 1fr",
      }}
    >
      <div style={{ display: "grid", gap: 16 }}>
        <div className="card pad">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div className="row gap10">
              <div className="gate-ico pass">
                <Icon name="Check" size={13} />
              </div>
              <div>
                <div className="b6">Constitution present</div>
                <div className="tiny muted mono">
                  source-truth · machine-readable
                </div>
              </div>
            </div>
            <Badge tone={c.coverage >= 80 ? "green" : "amber"}>
              {c.coverage}% coverage
            </Badge>
          </div>
          <div className="meter mt16" style={{ height: 7 }}>
            <span
              style={{
                background: c.coverage >= 80 ? "var(--green)" : "var(--amber)",
                width: c.coverage + "%",
              }}
            />
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <Icon color="var(--amber)" name="Lock" size={15} />
            <h3>Protected modules</h3>
            <span className="ch-sub">{c.protected.length}</span>
          </div>
          <div className="card-b" style={{ display: "grid", gap: 8 }}>
            {c.protected.length ? (
              c.protected.flatMap((m) =>
                m.paths.map((p) => (
                  <div
                    className="row gap10"
                    key={p}
                    style={{
                      background: "var(--panel-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 7,
                      padding: "7px 11px",
                    }}
                  >
                    <Icon color="var(--amber)" name="Lock" size={13} />
                    <span
                      className="path"
                      style={{
                        background: "var(--amber-bg)",
                        borderColor: "var(--amber-bd)",
                        color: "var(--amber)",
                      }}
                    >
                      {p}
                    </span>
                    <span className="grow" />
                    <span className="tiny faint">{m.name}</span>
                  </div>
                ))
              )
            ) : (
              <div className="sm muted">No protected modules declared.</div>
            )}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gap: 16 }}>
        <div className="card">
          <div className="card-h">
            <Icon color="var(--green)" name="ListChecks" size={15} />
            <h3>Allowed fixes</h3>
            <span className="ch-sub">{c.allowed.length}</span>
          </div>
          <div className="card-b" style={{ display: "grid", gap: 7 }}>
            {c.allowed.length ? (
              c.allowed.map((a) => (
                <div className="row gap10 sm" key={a}>
                  <Icon color="var(--green)" name="CircleCheck" size={15} />
                  <span className="fg2">{a.replace(/_/g, " ")}</span>
                </div>
              ))
            ) : (
              <div className="sm muted">No allowed fixes declared.</div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <Icon color="var(--amber)" name="MessageCircleQuestion" size={15} />
            <h3>Open questions</h3>
            {c.questions.length > 0 ? (
              <Badge tone="amber">{c.questions.length}</Badge>
            ) : (
              <span className="ch-sub">none</span>
            )}
          </div>
          <div className="card-b" style={{ display: "grid", gap: 10 }}>
            {c.questions.length ? (
              c.questions.map((qq) => (
                <div
                  className="card pad"
                  key={qq.id}
                  style={{ background: "var(--panel-2)" }}
                >
                  <div className="row gap10">
                    <Icon
                      color="var(--amber)"
                      name="HelpCircle"
                      size={15}
                      style={{ flex: "none", marginTop: 2 }}
                    />
                    <div>
                      <div className="sm fg2" style={{ lineHeight: 1.5 }}>
                        {qq.question}
                      </div>
                      <span
                        className="path mt8"
                        style={{ display: "inline-block" }}
                      >
                        {qq.severity}
                      </span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="row gap10 sm" style={{ color: "var(--green)" }}>
                <Icon name="CircleCheck" size={15} />
                No unanswered questions. Constitution is complete.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Re-exported helpers kept local; silence unused import lints in some builds.
export const _repoDetailHelpers = { fmt, relTime, TRIGGER_LABEL }
