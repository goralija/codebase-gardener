/* ============================================================
   Reusable Opportunities / Sessions / Pull Requests lists + drawers.
   Presentation-only: parents supply already-fetched, mapped data.
   ============================================================ */
import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { duration, relTime } from "@/cockpit/format"
import {
  CAT_ICON,
  STATUS_ICON,
  STATUS_TONE,
  TRIGGER_LABEL,
  TRIGGERS,
  type OppModel,
  type PlanModel,
  type SessionModel,
} from "@/cockpit/model"
import {
  Badge,
  CategoryBadge,
  ConfidenceBadge,
  Drawer,
  Empty,
  RepoName,
  RiskBadge,
  SegX,
  Selector,
  StatusBadge,
} from "@/cockpit/primitives"
import { COMPONENTS } from "@/cockpit/model"

type RepoLookup = (id: string) => string

function gotoRepo(
  navigate: ReturnType<typeof useNavigate>,
  repoId: string,
  tab?: string
) {
  navigate({
    search: tab ? { tab } : undefined,
    to: "/repo/$repoId",
    params: { repoId },
  } as never)
}

/* ---------------- Opportunity drawer ---------------- */
function OpportunityDrawer({
  opp,
  onClose,
  repoName,
}: {
  opp: OppModel
  onClose: () => void
  repoName: string
}) {
  return (
    <Drawer onClose={onClose}>
      <div className="drawer-h">
        <div
          className="a-ico"
          style={{
            background: "var(--panel-2)",
            border: "1px solid var(--border)",
            borderRadius: 9,
            height: 34,
            width: 34,
          }}
        >
          <Icon
            color="var(--fg-2)"
            name={CAT_ICON[opp.category] || "FileText"}
            size={17}
          />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row gap6 mb8 wrap">
            <CategoryBadge cat={opp.category} />
            <RiskBadge risk={opp.risk} />
            <StatusBadge status={opp.status} />
          </div>
          <div
            style={{
              fontSize: 15,
              fontWeight: 600,
              letterSpacing: "-0.01em",
              lineHeight: 1.3,
            }}
          >
            {opp.title}
          </div>
          <div className="row gap6 mt8 mono tiny muted">
            <span className="fg2">{repoName}</span>
            <span>·</span>
            <span>{opp.id}</span>
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} type="button">
          <Icon name="X" size={17} />
        </button>
      </div>
      <div className="drawer-b">
        {opp.blocked && (
          <div
            className="card pad mb16"
            style={{
              background: "var(--amber-bg)",
              borderColor: "var(--amber-bd)",
            }}
          >
            <div className="row gap10">
              <Icon color="var(--amber)" name="Ban" size={16} />
              <div>
                <div
                  className="b6"
                  style={{ color: "var(--amber)", fontSize: 13 }}
                >
                  Blocked — won't be opened
                </div>
                <div className="sm fg2 mt8">{opp.blocked}</div>
              </div>
            </div>
          </div>
        )}

        <div className="sect-title mb12">Evidence</div>
        <div className="evi mb20">
          <div className="evi-h">
            <Icon name="FileSearch" size={13} />
            analysis · {repoName}
          </div>
          <div className="evi-b">{opp.evidence || "No evidence recorded."}</div>
        </div>

        <div className="sect-title mb12">Confidence</div>
        <div className="card pad mb20">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div className="row gap10">
              <ConfidenceBadge
                floor={opp.confidenceFloor}
                value={opp.confidence}
              />
              <span className="sm muted">
                {opp.confidence >= opp.confidenceFloor
                  ? `Above autonomous floor (${opp.confidenceFloor}%)`
                  : `Below autonomous floor (${opp.confidenceFloor}%)`}
              </span>
            </div>
          </div>
          <div className="meter mt12" style={{ height: 7 }}>
            <span
              style={{
                background:
                  opp.confidence >= opp.confidenceFloor
                    ? "var(--green)"
                    : "var(--amber)",
                width: opp.confidence + "%",
              }}
            />
          </div>
        </div>

        {opp.paths.length > 0 && (
          <>
            <div className="sect-title mb12">Changed paths</div>
            <div className="row gap6 wrap mb20">
              {opp.paths.map((p) => (
                <span className="path" key={p}>
                  {p}
                </span>
              ))}
            </div>
          </>
        )}

        {opp.verify.length > 0 && (
          <>
            <div className="sect-title mb12">Verification</div>
            <div className="card pad">
              {opp.verify.map((v, i) => (
                <div className="row gap10" key={i} style={{ padding: "5px 0" }}>
                  <Icon color="var(--fg-4)" name="Terminal" size={13} />
                  <span className="kbd grow">{v}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      <div className="drawer-f">
        <button className="btn" onClick={onClose} type="button">
          Close
        </button>
      </div>
    </Drawer>
  )
}

export function OpportunitiesView({
  opps,
  repoName,
  showRepo,
}: {
  opps: OppModel[]
  repoName: RepoLookup
  showRepo: boolean
}) {
  const navigate = useNavigate()
  const [cat, setCat] = useState("all")
  const [risk, setRisk] = useState("all")
  const [status, setStatus] = useState("all")
  const [q, setQ] = useState("")
  const [sel, setSel] = useState<OppModel | null>(null)

  const filtered = opps.filter(
    (o) =>
      (cat === "all" || o.category === cat) &&
      (status === "all" || o.status === status) &&
      (risk === "all" || o.risk === risk) &&
      (q === "" ||
        o.title.toLowerCase().includes(q.toLowerCase()) ||
        repoName(o.repoId).toLowerCase().includes(q.toLowerCase()))
  )
  const cnt = (k: keyof OppModel, v: string) =>
    opps.filter((o) => o[k] === v).length

  return (
    <>
      <div className="row gap10 wrap mb16">
        <div className="search" style={{ minWidth: 260 }}>
          <Icon name="Search" size={14} />
          <input
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search opportunities…"
            value={q}
          />
        </div>
        <span className="spacer grow" />
        <SegX
          onChange={setStatus}
          options={[
            { count: opps.length, label: "All", value: "all" },
            { count: cnt("status", "ready"), label: "Ready", value: "ready" },
            {
              count: cnt("status", "blocked"),
              label: "Blocked",
              value: "blocked",
            },
          ]}
          value={status}
        />
        <Selector
          align="right"
          icon="Boxes"
          onChange={setCat}
          options={[
            { label: "All categories", value: "all" },
            ...COMPONENTS.map((c) => ({
              icon: c.icon,
              label: c.label,
              value: c.key,
            })),
          ]}
          value={cat === "all" ? "All categories" : cat}
          width={200}
        />
        <Selector
          align="right"
          icon="ShieldAlert"
          onChange={setRisk}
          options={[
            { label: "All risk", value: "all" },
            { label: "Low risk", value: "low" },
            { label: "Medium risk", value: "medium" },
            { label: "High risk", value: "high" },
          ]}
          value={risk === "all" ? "All risk" : risk + " risk"}
          width={170}
        />
      </div>

      {filtered.length === 0 ? (
        <div className="card">
          <Empty
            icon="Sparkles"
            sub="Run a session to detect new maintenance candidates, or clear the filters."
            title="No matching opportunities"
          />
        </div>
      ) : (
        <div style={{ display: "grid", gap: 9 }}>
          {filtered.map((o) => (
            <button
              className="att"
              key={o.id}
              onClick={() => setSel(o)}
              style={{
                borderLeftColor:
                  o.status === "blocked" ? "var(--amber)" : "var(--accent)",
              }}
              type="button"
            >
              <div
                className="a-ico"
                style={{
                  background: "var(--panel-2)",
                  border: "1px solid var(--border)",
                  color: "var(--fg-2)",
                }}
              >
                <Icon name={CAT_ICON[o.category] || "FileText"} size={16} />
              </div>
              <div className="a-body">
                <div className="a-title">{o.title}</div>
                <div className="row gap6 mt8 wrap">
                  {showRepo && (
                    <span
                      className="pill"
                      onClick={(e) => {
                        e.stopPropagation()
                        gotoRepo(navigate, o.repoId)
                      }}
                    >
                      {repoName(o.repoId)}
                    </span>
                  )}
                  <CategoryBadge cat={o.category} />
                  <RiskBadge risk={o.risk} />
                  {o.paths.length > 0 && (
                    <span className="pill mono">
                      <Icon name="FileCode" size={11} />
                      {o.paths.length} path{o.paths.length > 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>
              <div className="a-meta">
                <div className="col" style={{ alignItems: "flex-end", gap: 6 }}>
                  <StatusBadge status={o.status} />
                  <span className="row gap6 tiny muted nowrap">
                    conf{" "}
                    <ConfidenceBadge
                      floor={o.confidenceFloor}
                      value={o.confidence}
                    />
                  </span>
                </div>
                <Icon color="var(--fg-4)" name="ChevronRight" size={16} />
              </div>
            </button>
          ))}
        </div>
      )}
      {sel && (
        <OpportunityDrawer
          onClose={() => setSel(null)}
          opp={sel}
          repoName={repoName(sel.repoId)}
        />
      )}
    </>
  )
}

/* ---------------- Sessions ---------------- */
export function SessionsView({
  sessions,
  repoName,
  showRepo,
}: {
  sessions: SessionModel[]
  repoName: RepoLookup
  showRepo: boolean
}) {
  const navigate = useNavigate()
  const [status, setStatus] = useState("all")
  const list = sessions.filter((s) => status === "all" || s.status === status)

  return (
    <>
      <div className="row gap10 mb16">
        <SegX
          onChange={setStatus}
          options={[
            { count: sessions.length, label: "All", value: "all" },
            {
              count: sessions.filter((s) => s.status === "completed").length,
              label: "Completed",
              value: "completed",
            },
            {
              count: sessions.filter((s) => s.status === "failed").length,
              label: "Failed",
              value: "failed",
            },
          ]}
          value={status}
        />
      </div>
      {list.length === 0 ? (
        <div className="card">
          <Empty
            icon="TerminalSquare"
            sub="Run a session manually, or enable triggers in Automation to start scanning."
            title="No sessions yet"
          />
        </div>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Session</th>
                {showRepo && <th>Repository</th>}
                <th>Trigger</th>
                <th>Status</th>
                <th className="num">Duration</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {list.map((s) => (
                <tr
                  className="click"
                  key={s.id}
                  onClick={() => gotoRepo(navigate, s.repoId, "sessions")}
                >
                  <td>
                    <span className="mono fg2">{s.id.slice(0, 8)}</span>
                  </td>
                  {showRepo && (
                    <td>
                      <RepoName name={repoName(s.repoId)} />
                    </td>
                  )}
                  <td>
                    <Badge
                      icon={TRIGGERS.find((t) => t.key === s.trigger)?.icon}
                      tone="slate"
                    >
                      {TRIGGER_LABEL[s.trigger] || s.trigger}
                    </Badge>
                  </td>
                  <td>
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="num muted">
                    {duration(s.startedAt, s.finishedAt)}
                  </td>
                  <td className="muted sm">{relTime(s.startedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

/* ---------------- PR plan drawer ---------------- */
function PRDrawer({
  pr,
  onClose,
  repoName,
}: {
  pr: PlanModel
  onClose: () => void
  repoName: string
}) {
  let pendingReasonTitle = "Pending approval — not opened"
  if (pr.executionError) {
    pendingReasonTitle = pr.executionError.startsWith("No implemented file fix")
      ? "Not executable — not opened"
      : "Deferred — not opened"
  }

  return (
    <Drawer onClose={onClose}>
      <div className="drawer-h">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row gap6 mb8 wrap">
            <StatusBadge lg status={pr.status} />
            <CategoryBadge cat={pr.category} />
            <RiskBadge risk={pr.risk} />
          </div>
          <div
            className="mono"
            style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.35 }}
          >
            {pr.title}
          </div>
          <div className="row gap6 mt8 mono tiny muted">
            <span className="fg2">{repoName}</span>
            <span>·</span>
            <span>{pr.id}</span>
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} type="button">
          <Icon name="X" size={17} />
        </button>
      </div>
      <div className="drawer-b">
        {pr.blocked && (
          <div
            className="card pad mb16"
            style={{
              background: "var(--amber-bg)",
              borderColor: "var(--amber-bd)",
            }}
          >
            <div className="row gap10">
              <Icon color="var(--amber)" name="Ban" size={16} />
              <div>
                <div
                  className="b6"
                  style={{ color: "var(--amber)", fontSize: 13 }}
                >
                  Blocked — not opened
                </div>
                <div className="sm fg2 mt8">{pr.blocked}</div>
              </div>
            </div>
          </div>
        )}
        {pr.status === "failed" && pr.executionError && (
          <div
            className="card pad mb16"
            style={{
              background: "var(--red-bg)",
              borderColor: "var(--red-bd)",
            }}
          >
            <div className="row gap10">
              <Icon color="var(--red)" name="CircleX" size={16} />
              <div>
                <div
                  className="b6"
                  style={{ color: "var(--red)", fontSize: 13 }}
                >
                  Execution failed — not opened
                </div>
                <div className="sm fg2 mt8">{pr.executionError}</div>
              </div>
            </div>
          </div>
        )}
        {pr.status === "pending" && (
          <div
            className="card pad mb16"
            style={{
              background: "var(--panel-2)",
              borderColor: "var(--border-2)",
            }}
          >
            <div className="row gap10">
              <Icon color="var(--fg-3)" name="CircleDot" size={16} />
              <div>
                <div className="b6" style={{ fontSize: 13 }}>
                  {pendingReasonTitle}
                </div>
                <div className="sm fg2 mt8">
                  {pr.executionError ||
                    "Gardener planned this PR but did not approve it for execution."}
                </div>
              </div>
            </div>
          </div>
        )}

        <dl className="kv mb20">
          <dt>Status</dt>
          <dd>
            <StatusBadge status={pr.status} />
          </dd>
          <dt>Confidence</dt>
          <dd className="row gap10">
            <ConfidenceBadge floor={pr.confidenceFloor} value={pr.confidence} />
            <span className="sm muted">
              {pr.confidence >= pr.confidenceFloor
                ? "above floor"
                : "below floor"}
            </span>
          </dd>
          <dt>Risk tier</dt>
          <dd>
            <RiskBadge risk={pr.risk} />
          </dd>
          {pr.branch && (
            <>
              <dt>Branch</dt>
              <dd className="mono sm">{pr.branch}</dd>
            </>
          )}
        </dl>

        {pr.evidence && (
          <>
            <div className="sect-title mb12">Rationale</div>
            <div className="evi mb20">
              <div className="evi-h">
                <Icon name="FileSearch" size={13} />
                evidence
              </div>
              <div className="evi-b">{pr.evidence}</div>
            </div>
          </>
        )}

        {pr.paths.length > 0 && (
          <>
            <div className="sect-title mb12">Changed paths</div>
            <div className="row gap6 wrap mb20">
              {pr.paths.map((p) => (
                <span className="path" key={p}>
                  {p}
                </span>
              ))}
            </div>
          </>
        )}

        {pr.checks.length > 0 && (
          <>
            <div className="sect-title mb12">Required checks</div>
            <div className="card pad">
              {pr.checks.map((c, i) => (
                <div
                  className="row gap10"
                  key={i}
                  style={{
                    borderBottom:
                      i < pr.checks.length - 1
                        ? "1px solid var(--border)"
                        : "none",
                    padding: "6px 0",
                  }}
                >
                  <Icon color="var(--fg-4)" name="Circle" size={15} />
                  <span className="kbd">{c}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      <div className="drawer-f">
        <button className="btn" onClick={onClose} type="button">
          Close
        </button>
        {pr.prUrl && (
          <a className="btn" href={pr.prUrl} rel="noreferrer" target="_blank">
            <Icon name="ExternalLink" size={14} />
            Open on GitHub
          </a>
        )}
      </div>
    </Drawer>
  )
}

/* ---------------- Pull Requests ---------------- */
export function PullsView({
  plans,
  repoName,
  showRepo,
}: {
  plans: PlanModel[]
  repoName: RepoLookup
  showRepo: boolean
}) {
  const [status, setStatus] = useState("all")
  const [sel, setSel] = useState<PlanModel | null>(null)
  const list = plans.filter(
    (p) =>
      status === "all" ||
      p.status === status ||
      (status === "terminal" &&
        ["merged", "closed", "reverted"].includes(p.status))
  )
  const cnt = (s: string) => plans.filter((p) => p.status === s).length

  return (
    <>
      <div className="row gap10 mb16 wrap">
        <SegX
          onChange={setStatus}
          options={[
            { count: plans.length, label: "All", value: "all" },
            { count: cnt("ready"), label: "Ready", value: "ready" },
            { count: cnt("open"), label: "Open", value: "open" },
            { count: cnt("pending"), label: "Pending", value: "pending" },
            { count: cnt("failed"), label: "Failed", value: "failed" },
            { count: cnt("blocked"), label: "Blocked", value: "blocked" },
            {
              count: cnt("merged") + cnt("closed") + cnt("reverted"),
              label: "Terminal",
              value: "terminal",
            },
          ]}
          value={status}
        />
      </div>
      {list.length === 0 ? (
        <div className="card">
          <Empty
            icon="GitPullRequest"
            sub="Sessions in Assisted or Autonomous mode draft focused PR plans here."
            title="No PR plans"
          />
        </div>
      ) : (
        <div className="tbl-wrap scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>PR plan</th>
                {showRepo && <th>Repository</th>}
                <th>Status</th>
                <th className="num">Conf.</th>
                <th>Risk</th>
                <th>Category</th>
                <th>Checks</th>
              </tr>
            </thead>
            <tbody>
              {list.map((p) => (
                <tr className="click" key={p.id} onClick={() => setSel(p)}>
                  <td style={{ maxWidth: 360 }}>
                    <div className="row gap10">
                      <Icon
                        color={`var(--${STATUS_TONE[p.status] || "slate"})`}
                        name={STATUS_ICON[p.status] || "GitPullRequest"}
                        size={15}
                      />
                      <span
                        className="mono primary"
                        style={{
                          fontSize: 12.5,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {p.title}
                      </span>
                    </div>
                  </td>
                  {showRepo && (
                    <td>
                      <RepoName name={repoName(p.repoId)} />
                    </td>
                  )}
                  <td>
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="num">
                    <ConfidenceBadge
                      floor={p.confidenceFloor}
                      value={p.confidence}
                    />
                  </td>
                  <td>
                    <RiskBadge risk={p.risk} />
                  </td>
                  <td>
                    <CategoryBadge cat={p.category} />
                  </td>
                  <td>
                    <span className="pill mono">
                      <Icon color="var(--fg-3)" name="CircleCheck" size={11} />
                      {p.checks.length}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {sel && (
        <PRDrawer
          onClose={() => setSel(null)}
          pr={sel}
          repoName={repoName(sel.repoId)}
        />
      )}
    </>
  )
}
