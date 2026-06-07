/* ============================================================
   Overview dashboard — operational state + next actions.
   ============================================================ */
import { useMemo } from "react"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { entColor, relTime } from "@/cockpit/format"
import { useCockpit } from "@/cockpit/data"
import {
  entropyFromReport,
  sessionsFromAutomation,
  TRIGGER_LABEL,
  toRepoModel,
} from "@/cockpit/model"
import {
  AutonomyBadge,
  Badge,
  Delta,
  Empty,
  RepoName,
  Stat,
} from "@/cockpit/primitives"
import { useGateState } from "@/cockpit/pages/states"

export function OverviewPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const navigate = useNavigate()

  const repos = useMemo(
    () =>
      cockpit.repositories.map((r) =>
        toRepoModel(r, cockpit.automationMap.get(r.id))
      ),
    [cockpit.repositories, cockpit.automationMap]
  )

  const scored = useMemo(() => {
    return cockpit.repositories
      .map((repo) => {
        const report = cockpit.reportsMap.get(repo.id)
        return report
          ? { entropy: entropyFromReport(report).overall, repo }
          : null
      })
      .filter((x): x is NonNullable<typeof x> => x !== null)
      .sort((a, b) => b.entropy - a.entropy)
  }, [cockpit.repositories, cockpit.reportsMap])

  const recentActivity = useMemo(() => {
    return [...cockpit.automationMap.values()]
      .flatMap(sessionsFromAutomation)
      .sort(
        (a, b) =>
          new Date(b.startedAt ?? 0).getTime() -
          new Date(a.startedAt ?? 0).getTime()
      )
      .slice(0, 8)
  }, [cockpit.automationMap])

  if (gate) return gate

  const withBaseline = repos.filter((r) => r.hasBaseline).length
  const missingBaseline = repos.filter((r) => !r.hasBaseline)
  const failed = repos.filter((r) => r.scanStatus === "failed")
  const avgEntropy =
    scored.length > 0
      ? Math.round(scored.reduce((a, s) => a + s.entropy, 0) / scored.length)
      : null
  const openPrs = repos.reduce(
    (a, r) =>
      a +
      ((r.stats?.created_pr_count ?? 0) - (r.stats?.merged_pr_count ?? 0)),
    0
  )

  const attention = [
    ...missingBaseline.map((r) => ({
      action: "Run first scan",
      icon: "CircleDashed",
      repoId: r.id,
      sub: "Run first scan to promote a baseline. No PRs will be planned yet.",
      tab: "summary",
      title: `${r.name} has no baseline`,
      tone: "amber",
    })),
    ...failed.map((r) => ({
      action: "View & retry",
      icon: "CircleX",
      repoId: r.id,
      sub: "The last session failed. Review the error and retry.",
      tab: "sessions",
      title: `${r.name} — last session failed`,
      tone: "red",
    })),
  ]

  return (
    <div className="page wide">
      <div className="phead">
        <div>
          <div className="ph-eyebrow">
            <Icon name="LayoutDashboard" size={13} />
            Overview
          </div>
          <h1>Gardener operations</h1>
          <div className="ph-sub">
            Autonomous maintenance across {repos.length} repositories in{" "}
            <span className="mono fg2">@{cockpit.organization?.github_login}</span>
          </div>
          <div className="row gap6 wrap mt12">
            {[
              ["/entropy", "Entropy report", "Gauge"],
              ["/opportunities", "Opportunities", "Sparkles"],
              ["/sessions", "Sessions", "TerminalSquare"],
              ["/pulls", "Pull requests", "GitPullRequest"],
              ["/constitution", "Constitution", "ScrollText"],
            ].map(([to, label, ic]) => (
              <button
                className="pill link"
                key={to}
                onClick={() => navigate({ to } as never)}
                type="button"
              >
                <Icon color="var(--fg-3)" name={ic} size={12} />
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="statrow mb20">
        <Stat
          foot={<span className="muted">all connected</span>}
          icon="FolderGit2"
          label="Active repositories"
          onClick={() => navigate({ to: "/repos" })}
          value={repos.length}
        />
        <Stat
          accent={missingBaseline.length ? "var(--amber)" : "var(--green)"}
          foot={
            missingBaseline.length ? (
              <span style={{ color: "var(--amber)" }}>
                <Icon name="TriangleAlert" size={11} />
                {missingBaseline.length} need first scan
              </span>
            ) : (
              <span className="muted">all promoted</span>
            )
          }
          icon="Flag"
          label="With baseline"
          onClick={() => navigate({ to: "/repos" })}
          unit={`/ ${repos.length}`}
          value={withBaseline}
        />
        <Stat
          accent={entColor(avgEntropy)}
          foot={<span className="muted">across {scored.length} scanned</span>}
          icon="Gauge"
          label="Avg entropy"
          onClick={() => navigate({ to: "/entropy" })}
          tone={entColor(avgEntropy)}
          value={avgEntropy ?? "—"}
        />
        <Stat
          foot={<span className="muted">detected across repos</span>}
          icon="Sparkles"
          label="Opportunities"
          onClick={() => navigate({ to: "/opportunities" })}
          value={[...cockpit.reportsMap.values()].reduce(
            (a, r) => a + r.maintenance_opportunities.length,
            0
          )}
        />
        <Stat
          foot={<span className="muted">total runs</span>}
          icon="TerminalSquare"
          label="Sessions"
          onClick={() => navigate({ to: "/sessions" })}
          value={repos.reduce((a, r) => a + (r.stats?.session_count ?? 0), 0)}
        />
        <Stat
          accent="var(--blue)"
          foot={<span className="muted">awaiting review/merge</span>}
          icon="GitPullRequest"
          label="Open Gardener PRs"
          onClick={() => navigate({ to: "/pulls" })}
          value={Math.max(openPrs, 0)}
        />
      </div>

      <div
        style={{
          alignItems: "start",
          display: "grid",
          gap: 16,
          gridTemplateColumns: "1.35fr 1fr",
        }}
      >
        <div className="card">
          <div className="card-h">
            <Icon color="var(--amber)" name="TriangleAlert" size={15} />
            <h3>Needs attention</h3>
            <span className="ch-sub">{attention.length} items</span>
            <span className="spacer" />
            <button
              className="btn ghost sm"
              onClick={() => navigate({ to: "/repos" })}
              type="button"
            >
              All repos
              <Icon name="ArrowRight" size={13} />
            </button>
          </div>
          <div className="card-b" style={{ display: "grid", gap: 9 }}>
            {attention.length === 0 ? (
              <div className="row gap10 sm" style={{ color: "var(--green)" }}>
                <Icon name="CircleCheck" size={15} />
                All repositories are baselined and healthy.
              </div>
            ) : (
              attention.map((it, i) => (
                <button
                  className="att"
                  key={i}
                  onClick={() =>
                    navigate({
                      params: { repoId: it.repoId },
                      search: { tab: it.tab },
                      to: "/repo/$repoId",
                    } as never)
                  }
                  style={{ borderLeftColor: `var(--${it.tone})` }}
                  type="button"
                >
                  <div
                    className="a-ico"
                    style={{
                      background: `var(--${it.tone}-bg)`,
                      color: `var(--${it.tone})`,
                    }}
                  >
                    <Icon name={it.icon} size={16} />
                  </div>
                  <div className="a-body">
                    <div className="a-title">{it.title}</div>
                    <div className="a-sub">{it.sub}</div>
                  </div>
                  <div className="a-meta">
                    <span
                      className="btn ghost sm nowrap"
                      style={{ color: `var(--${it.tone})` }}
                    >
                      {it.action}
                      <Icon name="ChevronRight" size={13} />
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <Icon color="var(--fg-3)" name="Activity" size={15} />
            <h3>Recent activity</h3>
            <span className="spacer" />
            <button
              className="btn ghost sm"
              onClick={() => navigate({ to: "/sessions" })}
              type="button"
            >
              Sessions
              <Icon name="ArrowRight" size={13} />
            </button>
          </div>
          <div className="card-b">
            {recentActivity.length === 0 ? (
              <Empty icon="Activity" title="No recent activity" />
            ) : (
              <div className="tl">
                {recentActivity.map((s) => {
                  const repo = repos.find((r) => r.id === s.repoId)
                  return (
                    <div className="tl-item" key={s.id}>
                      <div className="tl-rail">
                        <div
                          className="tl-node"
                          style={{
                            color:
                              s.status === "failed"
                                ? "var(--red)"
                                : "var(--accent-2)",
                          }}
                        >
                          <Icon
                            name={
                              s.status === "failed"
                                ? "CircleX"
                                : "TerminalSquare"
                            }
                            size={14}
                          />
                        </div>
                        <div className="tl-line" />
                      </div>
                      <div className="tl-body">
                        <div className="tl-title">
                          Session {s.status} ·{" "}
                          {TRIGGER_LABEL[s.trigger] || s.trigger}
                        </div>
                        <div className="tl-meta">
                          <span style={{ color: "var(--fg-2)" }}>
                            {repo?.name ?? s.repoId}
                          </span>
                          <span>·</span>
                          <span>{relTime(s.startedAt)}</span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card mt16">
        <div className="card-h">
          <Icon color="var(--fg-3)" name="Gauge" size={15} />
          <h3>Repository health</h3>
          <span className="ch-sub">ranked by entropy</span>
          <span className="spacer" />
          <button
            className="btn ghost sm"
            onClick={() => navigate({ to: "/entropy" })}
            type="button"
          >
            Full entropy report
            <Icon name="ArrowRight" size={13} />
          </button>
        </div>
        <div className="tbl-wrap" style={{ border: "none", borderRadius: 0 }}>
          {scored.length === 0 ? (
            <Empty
              icon="Gauge"
              sub="Run first scans to compute entropy scores."
              title="No scanned repositories yet"
            />
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Autonomy</th>
                  <th>Baseline</th>
                  <th className="num">Entropy</th>
                  <th className="num">Δ forecast</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {scored.map(({ entropy, repo }) => {
                  const model = toRepoModel(
                    repo,
                    cockpit.automationMap.get(repo.id)
                  )
                  const report = cockpit.reportsMap.get(repo.id)
                  const predicted = report
                    ? Math.round(
                        report.entropy_report.forecast.predicted_overall
                      )
                    : null
                  return (
                    <tr
                      className="click"
                      key={repo.id}
                      onClick={() =>
                        navigate({
                          params: { repoId: repo.id },
                          to: "/repo/$repoId",
                        } as never)
                      }
                    >
                      <td>
                        <RepoName color={entColor(entropy)} name={repo.name} />
                      </td>
                      <td>
                        <AutonomyBadge mode={model.autonomy} />
                      </td>
                      <td>
                        {model.hasBaseline ? (
                          <Badge icon="Flag" tone="slate">
                            <span className="mono">
                              {model.baseSha?.slice(0, 7)}
                            </span>
                          </Badge>
                        ) : (
                          <Badge tone="amber">none</Badge>
                        )}
                      </td>
                      <td className="num">
                        <span style={{ color: entColor(entropy), fontWeight: 600 }}>
                          {entropy}
                        </span>
                      </td>
                      <td className="num">
                        <Delta
                          value={predicted == null ? null : predicted - entropy}
                        />
                      </td>
                      <td>
                        <Icon color="var(--fg-4)" name="ChevronRight" size={15} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
