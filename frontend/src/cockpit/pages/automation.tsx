/* ============================================================
   Repository automation policy editor (repo-detail tab) +
   standalone automation route (repo picker).
   ============================================================ */
import { useEffect, useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { relTime } from "@/cockpit/format"
import {
  updateRepositoryAutomation,
  type RepositoryAutomationResponse,
  type RepositoryAutomationUpdatePayload,
} from "@/features/automation/automation-api"
import { useCockpit } from "@/cockpit/data"
import {
  AUTONOMY,
  TRIGGER_LABEL,
  TRIGGERS,
  sessionsFromAutomation,
  toRepoModel,
  type AutonomyMode,
} from "@/cockpit/model"
import {
  Badge,
  Empty,
  RepoName,
  StatusBadge,
  Switch,
} from "@/cockpit/primitives"
import { PageShell, useGateState } from "@/cockpit/pages/states"

type PolicyDraft = {
  autonomy_mode: AutonomyMode
  manual_trigger_enabled: boolean
  scheduled_trigger_enabled: boolean
  commit_trigger_enabled: boolean
  risky_module_trigger_enabled: boolean
  pr_opened_trigger_enabled: boolean
  ci_failure_trigger_enabled: boolean
  commit_threshold: number
}

function draftFromPolicy(
  policy: RepositoryAutomationResponse["policy"]
): PolicyDraft {
  return {
    autonomy_mode: policy.autonomy_mode,
    ci_failure_trigger_enabled: policy.ci_failure_trigger_enabled,
    commit_threshold: policy.commit_threshold,
    commit_trigger_enabled: policy.commit_trigger_enabled,
    manual_trigger_enabled: policy.manual_trigger_enabled,
    pr_opened_trigger_enabled: policy.pr_opened_trigger_enabled,
    risky_module_trigger_enabled: policy.risky_module_trigger_enabled,
    scheduled_trigger_enabled: policy.scheduled_trigger_enabled,
  }
}

export function AutomationPanel({
  organizationId,
  automation,
}: {
  organizationId: string
  automation: RepositoryAutomationResponse
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const policy = automation.policy
  const [draft, setDraft] = useState<PolicyDraft>(() => draftFromPolicy(policy))
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(draftFromPolicy(policy))
    setDirty(false)
  }, [policy])

  const canEdit = automation.permissions.can_edit
  const sessions = sessionsFromAutomation(automation).slice(0, 4)

  const save = useMutation({
    mutationFn: (payload: RepositoryAutomationUpdatePayload) =>
      updateRepositoryAutomation(organizationId, automation.repository.id, payload),
    onSuccess: () => {
      setDirty(false)
      queryClient.invalidateQueries({ queryKey: ["cockpit", "automation"] })
    },
  })

  const change = <K extends keyof PolicyDraft>(key: K, value: PolicyDraft[K]) => {
    if (!canEdit) return
    setDraft((d) => ({ ...d, [key]: value }))
    setDirty(true)
  }

  const triggerEnabled: Record<string, boolean> = {
    "after-commits": draft.commit_trigger_enabled,
    "ci-failure": draft.ci_failure_trigger_enabled,
    manual: draft.manual_trigger_enabled,
    "pr-opened": draft.pr_opened_trigger_enabled,
    "risky-module": draft.risky_module_trigger_enabled,
    scheduled: draft.scheduled_trigger_enabled,
  }
  const enabledCount = Object.values(triggerEnabled).filter(Boolean).length

  const eff = automation.effective
  const canAuto = eff.can_create_autonomous_prs
  const gate = [
    {
      label: "Repository baseline",
      pass: Boolean(automation.baseline.commit_sha),
      sub: "first scan promoted",
      val: automation.baseline.commit_sha ? "ready" : "missing",
    },
    {
      label: "Autonomous PR add-on",
      pass: eff.autonomous_pr_add_on_enabled,
      sub: "organization billing gate",
      val: eff.autonomous_pr_add_on_enabled ? "enabled" : "off",
    },
    {
      label: "Autonomy mode",
      pass: draft.autonomy_mode === "autonomous",
      sub: "must be Autonomous",
      val: AUTONOMY[draft.autonomy_mode].label,
    },
    {
      label: "Confidence floor",
      pass: true,
      sub: "plans below floor are held",
      val: `${eff.confidence_threshold}%`,
    },
  ]

  return (
    <div
      style={{
        alignItems: "start",
        display: "grid",
        gap: 16,
        gridTemplateColumns: "1.7fr 1fr",
      }}
    >
      <div style={{ display: "grid", gap: 16 }}>
        <div className="card">
          <div className="card-h">
            <Icon color="var(--fg-3)" name="Bot" size={15} />
            <h3>Autonomy mode</h3>
            <span className="spacer" />
            {dirty && (
              <Badge icon="Dot" tone="amber">
                unsaved
              </Badge>
            )}
            <button
              className="btn sm primary"
              disabled={!dirty || save.isPending}
              onClick={() => save.mutate(draft)}
              type="button"
            >
              <Icon name="Check" size={13} />
              {save.isPending ? "Saving…" : "Save policy"}
            </button>
          </div>
          <div className="card-b">
            <div className="seg row">
              {(Object.entries(AUTONOMY) as [AutonomyMode, (typeof AUTONOMY)[AutonomyMode]][]).map(
                ([k, a]) => (
                  <button
                    className={`seg-opt${draft.autonomy_mode === k ? " on" : ""}`}
                    key={k}
                    onClick={() => change("autonomy_mode", k)}
                    type="button"
                  >
                    <div className="so-top">
                      <Icon
                        color={
                          draft.autonomy_mode === k
                            ? "var(--accent-2)"
                            : "var(--fg-3)"
                        }
                        name={
                          k === "autonomous"
                            ? "Bot"
                            : k === "assisted"
                              ? "UserCheck"
                              : "FileText"
                        }
                        size={15}
                      />
                      <span className="so-title">{a.label}</span>
                      <span className="so-check">
                        <Icon name="CircleCheck" size={16} />
                      </span>
                    </div>
                    <div className="so-desc">{a.desc}</div>
                  </button>
                )
              )}
            </div>
            <div className="card pad mt12" style={{ background: "var(--panel-2)" }}>
              <div className="row gap10">
                <Icon
                  color="var(--accent-2)"
                  name="ShieldCheck"
                  size={15}
                  style={{ flex: "none", marginTop: 1 }}
                />
                <div className="sm fg2" style={{ lineHeight: 1.5 }}>
                  <b style={{ color: "var(--accent-2)" }}>Safety impact · </b>
                  {AUTONOMY[draft.autonomy_mode].impact}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <Icon color="var(--fg-3)" name="Zap" size={15} />
            <h3>Session triggers</h3>
            <span className="spacer" />
            <span className="tiny muted">{enabledCount} of 6 enabled</span>
          </div>
          <div className="card-b">
            <div
              style={{
                alignItems: "start",
                display: "grid",
                gap: 10,
                gridTemplateColumns: "1fr 1fr",
              }}
            >
              {TRIGGERS.map((tr) => {
                const on = triggerEnabled[tr.key]
                const isThresh = tr.key === "after-commits"
                const toggle = () =>
                  change(tr.field as keyof PolicyDraft, !on as never)
                return (
                  <div
                    className={`trig${on ? " on" : ""}`}
                    key={tr.key}
                    onClick={toggle}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        toggle()
                      }
                    }}
                    role="button"
                    style={{
                      cursor: canEdit ? "pointer" : "default",
                      ...(isThresh ? { gridColumn: "1 / -1" } : {}),
                    }}
                    tabIndex={0}
                  >
                    <div className="t-ico">
                      <Icon name={tr.icon} size={15} />
                    </div>
                    <div className="t-body">
                      <div className="t-title">{tr.label}</div>
                      <div className="t-desc">
                        {isThresh
                          ? `Run a session after ${draft.commit_threshold} commits to the default branch`
                          : tr.desc}
                      </div>
                    </div>
                    {isThresh && (
                      <div
                        className="row gap8"
                        onClick={(e) => e.stopPropagation()}
                        style={{ flex: "none" }}
                      >
                        <span className="tiny muted nowrap">commits</span>
                        <span className="stepper">
                          <button
                            onClick={() =>
                              change(
                                "commit_threshold",
                                Math.max(1, draft.commit_threshold - 1)
                              )
                            }
                            type="button"
                          >
                            <Icon name="Minus" size={13} />
                          </button>
                          <span className="val">{draft.commit_threshold}</span>
                          <button
                            onClick={() =>
                              change(
                                "commit_threshold",
                                draft.commit_threshold + 1
                              )
                            }
                            type="button"
                          >
                            <Icon name="Plus" size={13} />
                          </button>
                        </span>
                      </div>
                    )}
                    <Switch on={on} />
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gap: 16 }}>
        <div className="card">
          <div className="card-h">
            <Icon
              color={canAuto ? "var(--green)" : "var(--amber)"}
              name="ShieldCheck"
              size={15}
            />
            <h3>Autonomous PR gate</h3>
          </div>
          <div className="card-b">
            <div
              className="card pad mb12"
              style={{
                background: canAuto ? "var(--green-bg)" : "var(--amber-bg)",
                borderColor: canAuto ? "var(--green-bd)" : "var(--amber-bd)",
              }}
            >
              <div className="row gap10">
                <Icon
                  color={canAuto ? "var(--green)" : "var(--amber)"}
                  name={canAuto ? "CircleCheck" : "CircleAlert"}
                  size={18}
                />
                <div>
                  <div
                    className="b6"
                    style={{ color: canAuto ? "var(--green)" : "var(--amber)" }}
                  >
                    {canAuto ? "Ready" : "Not eligible"}
                  </div>
                  <div className="tiny fg2 mt8">{eff.pr_creation_status}</div>
                </div>
              </div>
            </div>
            {gate.map((g) => (
              <div className="gate-row" key={g.label}>
                <div className={`gate-ico ${g.pass ? "pass" : "fail"}`}>
                  <Icon name={g.pass ? "Check" : "X"} size={13} strokeWidth={3} />
                </div>
                <div>
                  <div className="g-label sm">{g.label}</div>
                  <div className="g-sub">{g.sub}</div>
                </div>
                <span className="g-val">{g.val}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <Icon color="var(--fg-3)" name="TerminalSquare" size={15} />
            <h3>Recent sessions</h3>
            <span className="spacer" />
            <button
              className="btn ghost sm"
              onClick={() =>
                navigate({
                  params: { repoId: automation.repository.id },
                  search: { tab: "sessions" },
                  to: "/repo/$repoId",
                } as never)
              }
              type="button"
            >
              All
              <Icon name="ArrowRight" size={12} />
            </button>
          </div>
          <div className="card-b" style={{ display: "grid", gap: 8 }}>
            {sessions.length === 0 ? (
              <div className="sm muted">No sessions yet.</div>
            ) : (
              sessions.map((s) => (
                <div
                  className="row gap10"
                  key={s.id}
                  style={{ borderBottom: "1px solid var(--border)", padding: "7px 0" }}
                >
                  <Badge tone="slate">
                    {TRIGGER_LABEL[s.trigger] || s.trigger}
                  </Badge>
                  <span className="grow tiny muted mono">
                    {relTime(s.startedAt)}
                  </span>
                  <StatusBadge status={s.status} />
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/* Standalone /automation route: pick a repository to configure. */
export function AutomationPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const navigate = useNavigate()

  const rows = useMemo(
    () =>
      cockpit.repositories.map((repo) =>
        toRepoModel(repo, cockpit.automationMap.get(repo.id))
      ),
    [cockpit.repositories, cockpit.automationMap]
  )

  if (gate) return gate

  return (
    <PageShell
      eyebrow="Operations"
      eyebrowIcon="SlidersHorizontal"
      sub="Configure autonomy mode and session triggers per repository"
      title="Automation"
    >
      {rows.length === 0 ? (
        <div className="card">
          <Empty icon="SlidersHorizontal" title="No repositories to configure" />
        </div>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Autonomy</th>
                <th>Add-on</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((model) => (
                <tr
                  className="click"
                  key={model.id}
                  onClick={() =>
                    navigate({
                      params: { repoId: model.id },
                      search: { tab: "automation" },
                      to: "/repo/$repoId",
                    } as never)
                  }
                >
                  <td>
                    <RepoName name={model.name} />
                  </td>
                  <td>
                    <Badge tone={AUTONOMY[model.autonomy].color}>
                      {AUTONOMY[model.autonomy].label}
                    </Badge>
                  </td>
                  <td>
                    {model.effective?.autonomous_pr_add_on_enabled ? (
                      <Badge tone="green">enabled</Badge>
                    ) : (
                      <Badge tone="slate">off</Badge>
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
    </PageShell>
  )
}
