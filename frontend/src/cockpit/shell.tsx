/* ============================================================
   Cockpit app shell — sidebar + topbar, ported from the design.
   ============================================================ */
import {
  Link,
  Outlet,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { entColor } from "@/cockpit/format"
import {
  EMPTY_REPOS,
  useAutomationMap,
  useReportsMap,
  useRepositories,
  useSelectedOrganization,
} from "@/cockpit/data"
import "@/cockpit/cockpit.css"

const NAV = [
  { icon: "LayoutDashboard", id: "overview", label: "Overview", to: "/" },
  { icon: "FolderGit2", id: "repos", label: "Repositories", to: "/repos" },
  { icon: "Github", id: "github", label: "GitHub setup", to: "/onboarding/github" },
]

const REPO_SECTION = new Set([
  "repos",
  "repo",
  "entropy",
  "constitution",
  "opportunities",
  "sessions",
  "pulls",
  "automation",
])

const PAGE_TITLE: Record<string, string> = {
  automation: "Automation",
  constitution: "Constitution",
  entropy: "Entropy",
  github: "GitHub setup",
  opportunities: "Opportunities",
  overview: "Overview",
  pulls: "Pull Requests",
  repos: "Repositories",
  sessions: "Sessions",
}

function topSegment(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean)
  if (parts.length === 0) return "overview"
  if (parts[0] === "onboarding") return "github"
  return parts[0]
}

export function CockpitShell() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const navigate = useNavigate()
  const { organization } = useSelectedOrganization()
  const repositoriesQuery = useRepositories(organization?.id)
  const repositories = repositoriesQuery.data?.repositories ?? EMPTY_REPOS
  const { map: automationMap } = useAutomationMap(organization?.id, repositories)
  const { map: reportsMap } = useReportsMap(repositories)

  const top = topSegment(pathname)
  const orgLogin = organization?.github_login ?? "—"
  const orgName = organization?.name ?? "Organization"

  // org-level rollups for the topbar chips
  let missingBaseline = 0
  let failedSessions = 0
  let openPrs = 0
  automationMap.forEach((automation) => {
    if (!automation.baseline.commit_sha) missingBaseline += 1
    if (automation.recent_sessions[0]?.status === "failed") failedSessions += 1
    openPrs += automation.recent_pr_plans.filter(
      (p) => !p.terminal_outcome && (p.created_pr_url || !p.blocked)
    ).length
  })
  const attention = missingBaseline + failedSessions

  let entropySum = 0
  let entropyCount = 0
  reportsMap.forEach((report) => {
    entropySum += report.entropy_report.score.overall
    entropyCount += 1
  })
  const avgEntropy =
    entropyCount > 0 ? Math.round(entropySum / entropyCount) : null

  const crumbs = buildCrumbs(pathname, repositories, orgLogin)

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sb-brand">
          <div className="sb-logo">
            <Icon name="Sprout" size={18} />
          </div>
          <div>
            <div className="name">Codebase Gardener</div>
            <div className="sub">ops · v2.4</div>
          </div>
        </div>
        <nav className="sb-nav">
          {NAV.map((item) => {
            const active =
              top === item.id ||
              (item.id === "repos" && REPO_SECTION.has(top))
            const count = item.id === "repos" ? repositories.length : null
            return (
              <Link
                className={`sb-item${active ? " active" : ""}`}
                key={item.id}
                to={item.to}
              >
                <Icon className="ico" name={item.icon} size={16} />
                <span>{item.label}</span>
                {count != null && <span className="count">{count}</span>}
              </Link>
            )
          })}
        </nav>
        <div className="sb-foot">
          <button
            className="sb-org"
            onClick={() => navigate({ to: "/onboarding/github" })}
            type="button"
          >
            <div className="avatar">{orgName.charAt(0).toUpperCase()}</div>
            <div className="meta grow">
              <div className="o1">{orgName}</div>
              <div className="o2">
                @{orgLogin} · {repositories.length} repos
              </div>
            </div>
            <Icon color="var(--fg-3)" name="ChevronsUpDown" size={14} />
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div className="crumbs">
            {crumbs.map((crumb, index) => (
              <span key={index} style={{ alignItems: "center", display: "flex", gap: 7 }}>
                {index > 0 && (
                  <Icon className="sep" name="ChevronRight" size={13} />
                )}
                {crumb.to ? (
                  <Link style={{ cursor: "pointer" }} to={crumb.to}>
                    {crumb.label}
                  </Link>
                ) : (
                  <span className={index === crumbs.length - 1 ? "cur" : ""}>
                    {crumb.label}
                  </span>
                )}
              </span>
            ))}
          </div>
          <span className="spacer" />
          <div className="hchips">
            <button
              className="hchip"
              onClick={() => navigate({ to: "/entropy" })}
              title="Org average entropy"
              type="button"
            >
              <span
                className="hc-dot"
                style={{ background: entColor(avgEntropy) }}
              />
              <span className="hc-num" style={{ color: entColor(avgEntropy) }}>
                {avgEntropy ?? "—"}
              </span>
              <span className="hc-lbl">avg entropy</span>
            </button>
            <button
              className="hchip"
              onClick={() => navigate({ to: "/repos" })}
              title="Items needing attention"
              type="button"
            >
              <Icon color="var(--amber)" name="TriangleAlert" size={13} />
              <span className="hc-num">{attention}</span>
              <span className="hc-lbl">attention</span>
            </button>
            <button
              className="hchip"
              onClick={() => navigate({ to: "/pulls" })}
              title="Open Gardener PRs"
              type="button"
            >
              <Icon color="var(--blue)" name="GitPullRequest" size={13} />
              <span className="hc-num">{openPrs}</span>
              <span className="hc-lbl">open PRs</span>
            </button>
          </div>
        </div>
        <div className="content">
          <Outlet />
        </div>
      </div>
    </div>
  )
}

function buildCrumbs(
  pathname: string,
  repositories: { id: string; name: string }[],
  orgLogin: string
): { label: string; to?: string }[] {
  const parts = pathname.split("/").filter(Boolean)
  const crumbs: { label: string; to?: string }[] = [
    { label: orgLogin, to: "/" },
  ]
  if (parts[0] === "repo") {
    crumbs[0] = { label: "Repositories", to: "/repos" }
    const repo = repositories.find((r) => r.id === parts[1])
    crumbs.push({ label: repo ? repo.name : (parts[1] ?? "repository") })
    return crumbs
  }
  const top = topSegment(pathname)
  crumbs.push({ label: PAGE_TITLE[top] ?? top })
  return crumbs
}
