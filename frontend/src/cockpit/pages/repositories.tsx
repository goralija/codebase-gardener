/* ============================================================
   Repositories list.
   ============================================================ */
import { useMemo, useState } from "react"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { entColor, fmt, relTime } from "@/cockpit/format"
import { useCockpit } from "@/cockpit/data"
import {
  AUTONOMY,
  entropyFromReport,
  toRepoModel,
  type AutonomyMode,
} from "@/cockpit/model"
import {
  AutonomyBadge,
  Badge,
  Empty,
  RepoDot,
  Selector,
} from "@/cockpit/primitives"
import { useGateState } from "@/cockpit/pages/states"

export function RepositoriesPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const navigate = useNavigate()
  const [q, setQ] = useState("")
  const [autonomy, setAutonomy] = useState("all")
  const [sort, setSort] = useState("entropy")

  const rows = useMemo(() => {
    return cockpit.repositories.map((repo) => {
      const model = toRepoModel(repo, cockpit.automationMap.get(repo.id))
      const report = cockpit.reportsMap.get(repo.id)
      const entropy = report ? entropyFromReport(report).overall : null
      const opps = report?.maintenance_opportunities.length ?? 0
      return { entropy, model, opps, repo }
    })
  }, [cockpit.repositories, cockpit.automationMap, cockpit.reportsMap])

  if (gate) return gate

  let list = rows.filter(
    (r) =>
      (q === "" || r.model.name.toLowerCase().includes(q.toLowerCase())) &&
      (autonomy === "all" || r.model.autonomy === autonomy)
  )
  list = [...list].sort((a, b) => {
    if (sort === "entropy") return (b.entropy ?? -1) - (a.entropy ?? -1)
    if (sort === "name") return a.model.name.localeCompare(b.model.name)
    if (sort === "opps") return b.opps - a.opps
    return 0
  })

  const withBaseline = rows.filter((r) => r.model.hasBaseline).length
  const missing = rows.filter((r) => !r.model.hasBaseline).length

  return (
    <div className="page wide">
      <div className="phead">
        <div>
          <div className="ph-eyebrow">
            <Icon name="FolderGit2" size={13} />
            Operations
          </div>
          <h1>Repositories</h1>
          <div className="ph-sub">
            {rows.length} connected · {withBaseline} with baseline · {missing}{" "}
            awaiting first scan
          </div>
        </div>
        <div className="ph-actions">
          <button
            className="btn"
            onClick={() => navigate({ to: "/onboarding/github" })}
            type="button"
          >
            <Icon name="Github" size={15} />
            Manage access
          </button>
        </div>
      </div>

      <div className="row gap10 mb16 wrap">
        <div className="search" style={{ minWidth: 260 }}>
          <Icon name="Search" size={14} />
          <input
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter repositories…"
            value={q}
          />
        </div>
        <span className="grow" />
        <Selector
          align="right"
          icon="Bot"
          onChange={setAutonomy}
          options={[
            { label: "All modes", value: "all" },
            ...Object.entries(AUTONOMY).map(([k, v]) => ({
              label: v.label,
              value: k,
            })),
          ]}
          value={
            autonomy === "all" ? "All modes" : AUTONOMY[autonomy as AutonomyMode].label
          }
          width={190}
        />
        <Selector
          align="right"
          icon="ArrowUpDown"
          onChange={setSort}
          options={[
            { label: "Sort: Entropy", value: "entropy" },
            { label: "Sort: Name", value: "name" },
            { label: "Sort: Opportunities", value: "opps" },
          ]}
          value={
            { entropy: "Entropy", name: "Name", opps: "Opportunities" }[sort] ??
            "Entropy"
          }
          width={180}
        />
      </div>

      {list.length === 0 ? (
        <div className="card">
          <Empty
            icon="FolderGit2"
            sub="No repositories match the current filters."
            title="No repositories"
          />
        </div>
      ) : (
        <div className="tbl-wrap scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Branch</th>
                <th>Autonomy</th>
                <th>Baseline</th>
                <th className="num">Entropy</th>
                <th className="num">Opps</th>
                <th className="num">PR plans</th>
                <th>Last scan</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.map(({ entropy, model, opps }) => (
                <tr
                  className="click"
                  key={model.id}
                  onClick={() =>
                    navigate({
                      params: { repoId: model.id },
                      to: "/repo/$repoId",
                    } as never)
                  }
                >
                  <td>
                    <div className="repo-cell">
                      <RepoDot color={entColor(entropy ?? undefined)} />
                      <div>
                        <div className="mono primary" style={{ fontSize: 13 }}>
                          {model.name}
                        </div>
                        <div className="tiny faint mono">
                          {model.loc != null ? `${fmt(model.loc)} LOC` : "—"} ·{" "}
                          {model.modules != null
                            ? `${model.modules} modules`
                            : "—"}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className="pill mono">
                      <Icon name="GitBranch" size={11} />
                      {model.branch}
                    </span>
                  </td>
                  <td>
                    <AutonomyBadge mode={model.autonomy} />
                  </td>
                  <td>
                    {model.hasBaseline ? (
                      <span className="mono tiny fg2">
                        {model.baseSha?.slice(0, 7)}
                      </span>
                    ) : (
                      <Badge icon="CircleDashed" tone="amber">
                        none
                      </Badge>
                    )}
                  </td>
                  <td className="num">
                    {entropy != null ? (
                      <span style={{ color: entColor(entropy), fontWeight: 600 }}>
                        {entropy}
                      </span>
                    ) : (
                      <span className="faint">—</span>
                    )}
                  </td>
                  <td className="num">
                    {opps > 0 ? (
                      <span className="fg2">{opps}</span>
                    ) : (
                      <span className="faint">0</span>
                    )}
                  </td>
                  <td className="num">
                    {model.stats?.pr_plan_count ? (
                      <span className="fg2">{model.stats.pr_plan_count}</span>
                    ) : (
                      <span className="faint">0</span>
                    )}
                  </td>
                  <td className="muted sm">
                    {model.scanStatus === "failed" ? (
                      <Badge icon="CircleX" tone="red">
                        failed
                      </Badge>
                    ) : model.lastReportAt ? (
                      relTime(model.lastReportAt)
                    ) : (
                      <span className="faint">never</span>
                    )}
                  </td>
                  <td>
                    <Icon color="var(--fg-4)" name="ChevronRight" size={15} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
