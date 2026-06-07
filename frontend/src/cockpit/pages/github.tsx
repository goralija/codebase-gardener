/* ============================================================
   GitHub onboarding — setup checklist, repositories, billing.
   Wired to the real onboarding / billing endpoints.
   ============================================================ */
import { useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { fmt } from "@/cockpit/format"
import {
  fetchInstallationStart,
  updateOrganizationBilling,
} from "@/features/github-onboarding/github-onboarding-api"
import { useBilling, useCockpit } from "@/cockpit/data"
import { toRepoModel } from "@/cockpit/model"
import { Badge, Empty, RepoName, Switch } from "@/cockpit/primitives"

function money(cents: number): string {
  return "$" + (cents / 100).toFixed(2)
}

export function GithubPage() {
  const cockpit = useCockpit()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [q, setQ] = useState("")
  const billingQuery = useBilling(cockpit.organization?.id)

  const install = useMutation({
    mutationFn: () => fetchInstallationStart(),
    onSuccess: (data) => {
      window.location.href = data.install_url
    },
  })

  const toggleAddon = useMutation({
    mutationFn: (enabled: boolean) =>
      updateOrganizationBilling(cockpit.organization?.id ?? "", {
        autonomous_pr_add_on_enabled: enabled,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cockpit", "billing"] })
    },
  })

  const rows = useMemo(
    () =>
      cockpit.repositories.map((repo) =>
        toRepoModel(repo, cockpit.automationMap.get(repo.id))
      ),
    [cockpit.repositories, cockpit.automationMap]
  )

  const installed = Boolean(cockpit.organization)

  // Auth-required and hard errors still need the install affordance, so we only
  // gate on loading state here.
  if (cockpit.orgLoading) {
    return (
      <div className="page wide">
        <div className="card">
          <Empty icon="Loader" title="Loading…" />
        </div>
      </div>
    )
  }

  const filtered = rows.filter((r) =>
    r.name.toLowerCase().includes(q.toLowerCase())
  )
  const baselined = rows.filter((r) => r.hasBaseline).length
  const configured = rows.filter((r) => r.policy).length

  const billing = billingQuery.data

  const steps = [
    {
      desc: "Grant the Gardener access to your organization.",
      done: installed,
      id: "install",
      node: installed ? (
        <Badge icon="CircleCheck" lg tone="green">
          Installed on @{cockpit.organization?.github_login}
        </Badge>
      ) : (
        <button
          className="btn primary"
          disabled={install.isPending}
          onClick={() => install.mutate()}
          type="button"
        >
          <Icon name="Github" size={15} />
          {install.isPending ? "Redirecting…" : "Install GitHub App"}
        </button>
      ),
    },
    {
      desc: "Choose which repositories the Gardener manages.",
      done: installed && rows.length > 0,
      id: "select",
      node: installed ? (
        <Badge icon="FolderGit2" lg tone="teal">
          {rows.length} repositories selected
        </Badge>
      ) : (
        <span className="sm faint">Install the app first.</span>
      ),
    },
    {
      desc: "Set autonomy mode and session triggers per repository.",
      done: installed && configured > 0,
      id: "config",
      node: installed ? (
        <button
          className="btn sm"
          onClick={() => navigate({ to: "/automation" })}
          type="button"
        >
          <Icon name="SlidersHorizontal" size={13} />
          Open automation
        </button>
      ) : (
        <span className="sm faint">—</span>
      ),
    },
    {
      desc: "Promote baselines so drift and PR planning can begin.",
      done: installed && baselined > 0,
      id: "scan",
      node: installed ? (
        <div className="row gap10">
          <Badge lg tone={baselined === rows.length ? "green" : "amber"}>
            {baselined} of {rows.length} baselined
          </Badge>
          <button
            className="btn sm primary"
            onClick={() => navigate({ to: "/repos" })}
            type="button"
          >
            <Icon name="Play" size={13} />
            Scan repositories
          </button>
        </div>
      ) : (
        <span className="sm faint">—</span>
      ),
    },
  ]
  const activeIdx = steps.findIndex((s) => !s.done)

  return (
    <div className="page wide">
      <div className="phead">
        <div>
          <div className="ph-eyebrow">
            <Icon name="Github" size={13} />
            Setup
          </div>
          <h1>GitHub onboarding</h1>
          <div className="ph-sub">
            Connect repositories and bring the Gardener online
          </div>
        </div>
        <div className="ph-actions">
          {installed ? (
            <Badge icon="CircleCheck" lg tone="green">
              App installed
            </Badge>
          ) : (
            <button
              className="btn primary"
              disabled={install.isPending}
              onClick={() => install.mutate()}
              type="button"
            >
              <Icon name="Github" size={15} />
              Install GitHub App
            </button>
          )}
        </div>
      </div>

      {!installed && (
        <div
          className="card pad mb16"
          style={{ background: "var(--amber-bg)", borderColor: "var(--amber-bd)" }}
        >
          <div className="row gap10">
            <Icon color="var(--amber)" name="CircleAlert" size={16} />
            <span className="sm fg2">
              Install the GitHub App to begin. Repository analysis, automation,
              and PR planning are unavailable until the app is installed.
            </span>
          </div>
        </div>
      )}

      <div
        style={{
          alignItems: "start",
          display: "grid",
          gap: 16,
          gridTemplateColumns: "1fr 1.4fr",
        }}
      >
        <div className="card">
          <div className="card-h">
            <Icon color="var(--fg-3)" name="ListChecks" size={15} />
            <h3>Setup checklist</h3>
            <span className="spacer" />
            <span className="ch-sub">
              {steps.filter((s) => s.done).length}/{steps.length}
            </span>
          </div>
          <div className="card-b">
            <div className="steps">
              {steps.map((s, i) => {
                const state = s.done
                  ? "done"
                  : i === activeIdx
                    ? "active"
                    : "pending"
                return (
                  <div
                    className={`step ${state}${i === steps.length - 1 ? " last" : ""}`}
                    key={s.id}
                  >
                    <div className="step-rail">
                      <div className="step-num">
                        {s.done ? (
                          <Icon name="Check" size={14} strokeWidth={3} />
                        ) : (
                          i + 1
                        )}
                      </div>
                      {i < steps.length - 1 && <div className="step-conn" />}
                    </div>
                    <div className="step-body">
                      <div className="step-title">
                        {s.desc.split(".")[0]}
                        {state === "active" && <Badge tone="teal">next</Badge>}
                      </div>
                      <div className="step-desc">{s.desc}</div>
                      <div className="step-content">{s.node}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gap: 16 }}>
          <div className="card">
            <div className="card-h">
              <Icon color="var(--fg-3)" name="FolderGit2" size={15} />
              <h3>Selected repositories</h3>
              <span className="ch-sub">{rows.length} active</span>
              <span className="spacer" />
              <div className="search" style={{ height: 28, minWidth: 150 }}>
                <Icon name="Search" size={13} />
                <input
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Filter…"
                  value={q}
                />
              </div>
            </div>
            {installed && rows.length > 0 ? (
              <div className="tbl-wrap" style={{ border: "none", borderRadius: 0 }}>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Repository</th>
                      <th>Branch</th>
                      <th>Visibility</th>
                      <th>Complexity</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r) => (
                      <tr
                        className="click"
                        key={r.id}
                        onClick={() =>
                          navigate({
                            params: { repoId: r.id },
                            to: "/repo/$repoId",
                          } as never)
                        }
                      >
                        <td>
                          <RepoName name={r.name} />
                        </td>
                        <td>
                          <span className="pill mono">
                            <Icon name="GitBranch" size={11} />
                            {r.branch}
                          </span>
                        </td>
                        <td>
                          <Badge
                            icon={r.isPrivate ? "Lock" : "Globe"}
                            tone="slate"
                          >
                            {r.isPrivate ? "private" : "public"}
                          </Badge>
                        </td>
                        <td>
                          <span className="mono sm">
                            {r.multiplier.toFixed(2)}×
                          </span>{" "}
                          <span className="tiny faint">
                            · {r.loc != null ? `${fmt(r.loc)} LOC` : "—"}
                          </span>
                        </td>
                        <td>
                          <Icon color="var(--fg-4)" name="ChevronRight" size={15} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                icon="FolderGit2"
                sub="Select repositories in GitHub App settings after installing."
                title="No repositories selected"
              />
            )}
          </div>

          {billing && (
            <div className="card">
              <div className="card-h">
                <Icon color="var(--fg-3)" name="CreditCard" size={15} />
                <h3>Billing plan</h3>
                <span className="ch-sub">{billing.subscription.plan_code}</span>
                <span className="spacer" />
                <span className="row gap8 sm">
                  <span className="muted">Autonomous PR add-on</span>
                  <Switch
                    on={billing.subscription.autonomous_pr_add_on_enabled}
                    onClick={
                      billing.permissions.can_edit_add_on
                        ? () =>
                            toggleAddon.mutate(
                              !billing.subscription
                                .autonomous_pr_add_on_enabled
                            )
                        : undefined
                    }
                  />
                </span>
              </div>
              <div className="card-b">
                <div
                  style={{
                    display: "grid",
                    gap: 14,
                    gridTemplateColumns: "repeat(4,1fr)",
                  }}
                >
                  {[
                    {
                      l: "Managed repos",
                      v: String(billing.billing.active_managed_repository_count),
                    },
                    {
                      l: "Billable units",
                      v: billing.billing.billable_repository_units.toFixed(2),
                    },
                    {
                      l: "Base subtotal",
                      v: money(billing.billing.base_subtotal_cents),
                    },
                    {
                      hot: true,
                      l: "Monthly estimate",
                      v: money(billing.billing.monthly_estimate_cents),
                    },
                  ].map((c) => (
                    <div key={c.l}>
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
                        className="mono"
                        style={{
                          color: c.hot ? "var(--accent-2)" : "var(--fg)",
                          fontSize: 21,
                          fontWeight: 600,
                          marginTop: 6,
                        }}
                      >
                        {c.v}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
