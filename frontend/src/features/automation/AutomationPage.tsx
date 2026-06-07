import { useState } from "react"
import type { ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleDashed,
  CircleOff,
  GitCommit,
  GitPullRequest,
  Play,
  RefreshCw,
  Save,
  Settings,
  ShieldAlert,
  Workflow,
} from "lucide-react"

import { GardenerLogo } from "@/components/brand"
import { Button } from "@/components/ui/button"
import {
  fetchOrganizationBilling,
  fetchOrganizationRepositories,
  fetchOrganizations,
  GithubOnboardingRequestError,
  updateOrganizationBilling,
  type ManagedRepository,
  type Organization,
} from "@/features/github-onboarding/github-onboarding-api"
import {
  fetchRepositoryAutomation,
  triggerRepositorySession,
  updateRepositoryAutomation,
  type AutonomyMode,
  type RepositoryAutomationPolicy,
  type RepositoryAutomationResponse,
  type RepositoryAutomationUpdatePayload,
} from "./automation-api"

type AutomationDraft = Pick<
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

type DraftState = {
  policyId: string
  policyUpdatedAt: string
  value: AutomationDraft
}

type RepositorySelection = {
  organizationId: string
  repositoryId: string
}

const EMPTY_ORGANIZATIONS: Organization[] = []
const EMPTY_REPOSITORIES: ManagedRepository[] = []

const MODE_OPTIONS: Array<{
  label: string
  mode: AutonomyMode
  summary: string
}> = [
  {
    label: "Conservative",
    mode: "conservative",
    summary: "Reports only",
  },
  {
    label: "Assisted",
    mode: "assisted",
    summary: "Human-led PRs",
  },
  {
    label: "Autonomous",
    mode: "autonomous",
    summary: "Focused PRs",
  },
]

export function AutomationPage() {
  const queryClient = useQueryClient()
  const [manualOrganizationId, setManualOrganizationId] = useState<
    string | null
  >(null)
  const [manualRepositorySelection, setManualRepositorySelection] =
    useState<RepositorySelection | null>(null)
  const [draftState, setDraftState] = useState<DraftState | null>(null)

  const organizationsQuery = useQuery({
    queryKey: ["automation", "organizations"],
    queryFn: () => fetchOrganizations(),
    retry: false,
  })

  const organizations =
    organizationsQuery.data?.organizations ?? EMPTY_ORGANIZATIONS
  const selectedOrganizationId =
    manualOrganizationId ?? organizations[0]?.id ?? null

  const repositoriesQuery = useQuery({
    queryKey: ["automation", "repositories", selectedOrganizationId],
    queryFn: () => fetchOrganizationRepositories(selectedOrganizationId ?? ""),
    enabled: Boolean(selectedOrganizationId),
    retry: false,
  })
  const billingQuery = useQuery({
    queryKey: ["automation", "billing", selectedOrganizationId],
    queryFn: () => fetchOrganizationBilling(selectedOrganizationId ?? ""),
    enabled: Boolean(selectedOrganizationId),
    retry: false,
  })

  const repositories = repositoriesQuery.data?.repositories ?? EMPTY_REPOSITORIES
  const selectedRepositoryId = chooseRepositoryId(
    selectedOrganizationId,
    manualRepositorySelection,
    repositories
  )
  const selectedRepository = repositories.find(
    (repository) => repository.id === selectedRepositoryId
  )

  const automationQuery = useQuery({
    queryKey: [
      "automation",
      "repository-policy",
      selectedOrganizationId,
      selectedRepositoryId,
    ],
    queryFn: () =>
      fetchRepositoryAutomation(
        selectedOrganizationId ?? "",
        selectedRepositoryId ?? ""
      ),
    enabled: Boolean(selectedOrganizationId && selectedRepositoryId),
    retry: false,
  })

  const saveMutation = useMutation({
    mutationFn: (payload: RepositoryAutomationUpdatePayload) =>
      updateRepositoryAutomation(
        selectedOrganizationId ?? "",
        selectedRepositoryId ?? "",
        payload
      ),
    onSuccess: (payload) => {
      queryClient.setQueryData(
        [
          "automation",
          "repository-policy",
          selectedOrganizationId,
          selectedRepositoryId,
        ],
        payload
      )
    },
  })

  const triggerMutation = useMutation({
    mutationFn: () =>
      triggerRepositorySession(
        selectedOrganizationId ?? "",
        selectedRepositoryId ?? ""
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: [
          "automation",
          "repository-policy",
          selectedOrganizationId,
          selectedRepositoryId,
        ],
      })
    },
  })

  const addOnMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      updateOrganizationBilling(selectedOrganizationId ?? "", {
        autonomous_pr_add_on_enabled: enabled,
      }),
    onSuccess: async (payload) => {
      queryClient.setQueryData(
        ["automation", "billing", selectedOrganizationId],
        payload
      )
      await queryClient.invalidateQueries({
        queryKey: [
          "automation",
          "repository-policy",
          selectedOrganizationId,
          selectedRepositoryId,
        ],
      })
    },
  })

  const automation = automationQuery.data
  const currentDraft = currentPolicyDraft(automation, draftState)
  const dirty = Boolean(
    automation && currentDraft && !draftMatchesPolicy(currentDraft, automation.policy)
  )
  const isPreInstallForbidden =
    organizationsQuery.error instanceof GithubOnboardingRequestError &&
    organizationsQuery.error.status === 403

  if (organizationsQuery.isLoading) {
    return (
      <AutomationState
        icon={<CircleDashed className="size-5 animate-spin" />}
        title="Loading automation"
      />
    )
  }

  if (organizationsQuery.isError && !isPreInstallForbidden) {
    return (
      <AutomationState
        action={
          <Button
            aria-label="Retry automation"
            onClick={() => void organizationsQuery.refetch()}
            type="button"
            variant="outline"
          >
            <RefreshCw />
            Retry
          </Button>
        }
        icon={<AlertTriangle className="size-5 text-destructive" />}
        title="Could not load automation"
      />
    )
  }

  if (isPreInstallForbidden || organizations.length === 0) {
    return (
      <AutomationState
        action={
          <Button asChild>
            <a href="/onboarding/github">
              <Settings />
              Open GitHub setup
            </a>
          </Button>
        }
        icon={<CircleOff className="size-5 text-muted-foreground" />}
        title="No GitHub installation"
      />
    )
  }

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <GardenerLogo className="size-5" />
              Automation
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal">
              Session triggers and PR policy
            </h1>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            {organizations.length > 1 ? (
              <LabeledSelect
                label="Organization"
                onChange={setManualOrganizationId}
                value={selectedOrganizationId ?? ""}
                options={organizations.map((organization) => ({
                  label: organization.github_login,
                  value: organization.id,
                }))}
              />
            ) : null}
            <LabeledSelect
              disabled={repositoriesQuery.isLoading || repositories.length === 0}
              label="Repository"
              onChange={(repositoryId) => {
                if (selectedOrganizationId) {
                  setManualRepositorySelection({
                    organizationId: selectedOrganizationId,
                    repositoryId,
                  })
                }
              }}
              value={selectedRepositoryId ?? ""}
              options={repositories.map((repository) => ({
                label: repository.full_name,
                value: repository.id,
              }))}
            />
          </div>
        </header>

        {repositoriesQuery.isError ? (
          <StatusBand icon={<AlertTriangle className="size-4" />} tone="danger">
            Could not load selected repositories
          </StatusBand>
        ) : repositoriesQuery.isLoading ? (
          <StatusBand icon={<CircleDashed className="size-4 animate-spin" />}>
            Loading repositories
          </StatusBand>
        ) : repositories.length === 0 ? (
          <EmptyRepositories />
        ) : selectedRepository ? (
          <AutomationWorkspace
            addOnMutationPending={addOnMutation.isPending}
            automation={automation}
            billingCanEditAddOn={
              billingQuery.data?.permissions.can_edit_add_on ?? false
            }
            draft={currentDraft}
            isDirty={dirty}
            isLoading={automationQuery.isLoading}
            isSaving={saveMutation.isPending}
            isTriggering={triggerMutation.isPending}
            mutationError={
              saveMutation.error ?? triggerMutation.error ?? addOnMutation.error
            }
            onDraftChange={(nextDraft) => {
              if (automation) {
                setDraftState({
                  policyId: automation.policy.id,
                  policyUpdatedAt: automation.policy.updated_at,
                  value: nextDraft,
                })
              }
            }}
            onRunNow={() => triggerMutation.mutate()}
            onSave={() => {
              if (currentDraft) {
                saveMutation.mutate(currentDraft)
              }
            }}
            onToggleAddOn={(enabled) => addOnMutation.mutate(enabled)}
            repository={selectedRepository}
          />
        ) : null}
      </div>
    </main>
  )
}

function AutomationWorkspace({
  addOnMutationPending,
  automation,
  billingCanEditAddOn,
  draft,
  isDirty,
  isLoading,
  isSaving,
  isTriggering,
  mutationError,
  onDraftChange,
  onRunNow,
  onSave,
  onToggleAddOn,
  repository,
}: {
  addOnMutationPending: boolean
  automation?: RepositoryAutomationResponse
  billingCanEditAddOn: boolean
  draft: AutomationDraft | null
  isDirty: boolean
  isLoading: boolean
  isSaving: boolean
  isTriggering: boolean
  mutationError: Error | null
  onDraftChange: (draft: AutomationDraft) => void
  onRunNow: () => void
  onSave: () => void
  onToggleAddOn: (enabled: boolean) => void
  repository: ManagedRepository
}) {
  if (isLoading || !automation || !draft) {
    return (
      <StatusBand icon={<CircleDashed className="size-4 animate-spin" />}>
        Loading automation policy
      </StatusBand>
    )
  }

  const canEdit = automation.permissions.can_edit
  const canRunNow =
    automation.permissions.can_trigger_manual_session &&
    automation.policy.manual_trigger_enabled

  return (
    <>
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="rounded-md border bg-card p-5 text-card-foreground">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Workflow className="size-4 text-primary" />
                <h2>{repository.full_name}</h2>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                Default branch: {repository.default_branch || "unknown"}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                disabled={!canRunNow || isTriggering}
                onClick={onRunNow}
                type="button"
                variant="outline"
              >
                {isTriggering ? (
                  <CircleDashed className="animate-spin" />
                ) : (
                  <Play />
                )}
                Run now
              </Button>
              <Button
                disabled={!canEdit || !isDirty || isSaving}
                onClick={onSave}
                type="button"
              >
                {isSaving ? <CircleDashed className="animate-spin" /> : <Save />}
                Save
              </Button>
            </div>
          </div>

          {mutationError ? (
            <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {mutationError.message}
            </div>
          ) : null}

          <div className="mt-5">
            <h3 className="text-sm font-semibold">Autonomy mode</h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {MODE_OPTIONS.map((option) => (
                <button
                  aria-pressed={draft.autonomy_mode === option.mode}
                  className={[
                    "rounded-md border px-3 py-3 text-left transition",
                    draft.autonomy_mode === option.mode
                      ? "border-primary bg-primary/10"
                      : "bg-background hover:bg-muted",
                  ].join(" ")}
                  disabled={!canEdit}
                  key={option.mode}
                  onClick={() =>
                    onDraftChange({ ...draft, autonomy_mode: option.mode })
                  }
                  type="button"
                >
                  <span className="block text-sm font-semibold">
                    {option.label}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {option.summary}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <TriggerControls
            canEdit={canEdit}
            draft={draft}
            onDraftChange={onDraftChange}
          />
        </div>

        <GatePanel
          addOnMutationPending={addOnMutationPending}
          automation={automation}
          billingCanEditAddOn={billingCanEditAddOn}
          onToggleAddOn={onToggleAddOn}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <RecentSessions sessions={automation.recent_sessions} />
        <RecentPrPlans plans={automation.recent_pr_plans} />
      </section>
    </>
  )
}

function TriggerControls({
  canEdit,
  draft,
  onDraftChange,
}: {
  canEdit: boolean
  draft: AutomationDraft
  onDraftChange: (draft: AutomationDraft) => void
}) {
  const rows: Array<{
    description: string
    field: keyof Omit<AutomationDraft, "autonomy_mode" | "commit_threshold">
    icon: ReactNode
    label: string
  }> = [
    {
      description: "On-demand sessions",
      field: "manual_trigger_enabled",
      icon: <Play className="size-4" />,
      label: "Manual run",
    },
    {
      description: "Periodic repository pass",
      field: "scheduled_trigger_enabled",
      icon: <CalendarClock className="size-4" />,
      label: "Schedule",
    },
    {
      description: `After ${draft.commit_threshold} commits`,
      field: "commit_trigger_enabled",
      icon: <GitCommit className="size-4" />,
      label: "Commit threshold",
    },
    {
      description: "Protected-area changes",
      field: "risky_module_trigger_enabled",
      icon: <ShieldAlert className="size-4" />,
      label: "Risky module",
    },
    {
      description: "Pull request activity",
      field: "pr_opened_trigger_enabled",
      icon: <GitPullRequest className="size-4" />,
      label: "PR opened",
    },
    {
      description: "Failed workflow activity",
      field: "ci_failure_trigger_enabled",
      icon: <AlertTriangle className="size-4" />,
      label: "CI failure",
    },
  ]

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Session triggers</h3>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Commit threshold</span>
          <input
            aria-label="Commit threshold"
            className="h-8 w-20 rounded-md border bg-background px-2 text-sm text-foreground disabled:opacity-50"
            disabled={!canEdit || !draft.commit_trigger_enabled}
            min={1}
            max={500}
            onChange={(event) =>
              onDraftChange({
                ...draft,
                commit_threshold: clampCommitThreshold(event.target.value),
              })
            }
            type="number"
            value={draft.commit_threshold}
          />
        </label>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {rows.map((row) => (
          <label
            className="flex min-h-20 items-center justify-between gap-3 rounded-md border bg-background px-3 py-3"
            key={row.field}
          >
            <span className="flex min-w-0 items-center gap-3">
              <span className="text-muted-foreground">{row.icon}</span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">
                  {row.label}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {row.description}
                </span>
              </span>
            </span>
            <input
              checked={Boolean(draft[row.field])}
              className="size-4 accent-primary"
              disabled={!canEdit}
              onChange={(event) =>
                onDraftChange({ ...draft, [row.field]: event.target.checked })
              }
              type="checkbox"
            />
          </label>
        ))}
      </div>
    </div>
  )
}

function GatePanel({
  addOnMutationPending,
  automation,
  billingCanEditAddOn,
  onToggleAddOn,
}: {
  addOnMutationPending: boolean
  automation: RepositoryAutomationResponse
  billingCanEditAddOn: boolean
  onToggleAddOn: (enabled: boolean) => void
}) {
  const enabled = automation.effective.can_create_autonomous_prs
  return (
    <aside className="rounded-md border bg-card p-5 text-card-foreground">
      <div className="flex items-center gap-2 text-sm font-semibold">
        {enabled ? (
          <CheckCircle2 className="size-4 text-primary" />
        ) : (
          <AlertTriangle className="size-4 text-destructive" />
        )}
        <h2>Autonomous PR gate</h2>
      </div>
      <div className="mt-4 rounded-md border bg-background p-3">
        <div className="text-sm font-medium">
          {enabled ? "Ready" : "Blocked"}
        </div>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {automation.effective.pr_creation_status}
        </p>
      </div>

      <div className="mt-4 space-y-3 text-sm">
        <label className="flex items-center justify-between gap-3 rounded-md border bg-background px-3 py-3">
          <span>
            <span className="block font-medium">Autonomous PR add-on</span>
            <span className="block text-xs text-muted-foreground">
              Organization gate
            </span>
          </span>
          <input
            aria-label="Autonomous PR add-on"
            checked={automation.effective.autonomous_pr_add_on_enabled}
            className="size-4 accent-primary"
            disabled={!billingCanEditAddOn || addOnMutationPending}
            onChange={(event) => onToggleAddOn(event.target.checked)}
            type="checkbox"
          />
        </label>

        <MetricLine
          label="Confidence floor"
          value={formatPercent(automation.effective.confidence_threshold)}
        />
        <MetricLine
          label="Default commit threshold"
          value={String(automation.effective.default_commit_threshold)}
        />
      </div>
    </aside>
  )
}

function RecentSessions({
  sessions,
}: {
  sessions: RepositoryAutomationResponse["recent_sessions"]
}) {
  return (
    <section className="rounded-md border bg-card p-5 text-card-foreground">
      <h2 className="text-sm font-semibold">Recent sessions</h2>
      {sessions.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No sessions yet</p>
      ) : (
        <div className="mt-4 divide-y rounded-md border">
          {sessions.map((session) => (
            <div className="flex items-center justify-between gap-3 p-3" key={session.id}>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {triggerName(session.trigger)}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {formatDate(session.created_at)}
                </div>
              </div>
              <StatusPill value={session.status} />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function RecentPrPlans({
  plans,
}: {
  plans: RepositoryAutomationResponse["recent_pr_plans"]
}) {
  return (
    <section className="rounded-md border bg-card p-5 text-card-foreground">
      <h2 className="text-sm font-semibold">Recent PR plans</h2>
      {plans.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No PR plans yet</p>
      ) : (
        <div className="mt-4 divide-y rounded-md border">
          {plans.map((plan) => (
            <div className="flex items-center justify-between gap-3 p-3" key={plan.id}>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{plan.title}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {plan.blocked
                    ? plan.block_reason
                    : `${formatPercent(plan.confidence)} confidence`}
                </div>
              </div>
              <StatusPill value={plan.blocked ? "blocked" : plan.execution_status} />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function LabeledSelect({
  disabled,
  label,
  onChange,
  options,
  value,
}: {
  disabled?: boolean
  label: string
  onChange: (value: string) => void
  options: Array<{ label: string; value: string }>
  value: string
}) {
  return (
    <label className="flex min-w-56 flex-col gap-2 text-sm font-medium">
      {label}
      <select
        className="h-9 rounded-md border bg-background px-3 text-sm font-normal"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function StatusBand({
  children,
  icon,
  tone = "neutral",
}: {
  children: ReactNode
  icon: ReactNode
  tone?: "danger" | "neutral"
}) {
  const toneClass =
    tone === "danger"
      ? "border-destructive/30 bg-destructive/10 text-destructive"
      : "border-border bg-muted/30 text-muted-foreground"
  return (
    <div className={`flex items-center gap-2 rounded-md border px-4 py-3 text-sm ${toneClass}`}>
      {icon}
      {children}
    </div>
  )
}

function AutomationState({
  action,
  icon,
  title,
}: {
  action?: ReactNode
  icon: ReactNode
  title: string
}) {
  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex min-h-svh w-full max-w-3xl items-center justify-center px-5 py-10">
        <section className="w-full rounded-md border bg-card p-6 text-card-foreground">
          <div className="flex items-center gap-3">
            {icon}
            <h1 className="text-xl font-semibold tracking-normal">{title}</h1>
          </div>
          {action ? <div className="mt-5">{action}</div> : null}
        </section>
      </div>
    </main>
  )
}

function EmptyRepositories() {
  return (
    <section className="rounded-md border border-dashed bg-muted/30 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-normal">
            No selected repositories
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Repository access is managed in GitHub setup.
          </p>
        </div>
        <Button asChild variant="outline">
          <a href="/onboarding/github">
            <Settings />
            GitHub setup
          </a>
        </Button>
      </div>
    </section>
  )
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-background px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function StatusPill({ value }: { value: string }) {
  const tone =
    value === "completed" || value === "succeeded"
      ? "bg-primary/10 text-primary"
      : value === "blocked" || value === "failed"
        ? "bg-destructive/10 text-destructive"
        : "bg-muted text-muted-foreground"
  return (
    <span className={`shrink-0 rounded-md px-2 py-1 text-xs font-medium ${tone}`}>
      {formatStatus(value)}
    </span>
  )
}

function policyToDraft(policy: RepositoryAutomationPolicy): AutomationDraft {
  return {
    autonomy_mode: policy.autonomy_mode,
    manual_trigger_enabled: policy.manual_trigger_enabled,
    scheduled_trigger_enabled: policy.scheduled_trigger_enabled,
    commit_trigger_enabled: policy.commit_trigger_enabled,
    risky_module_trigger_enabled: policy.risky_module_trigger_enabled,
    pr_opened_trigger_enabled: policy.pr_opened_trigger_enabled,
    ci_failure_trigger_enabled: policy.ci_failure_trigger_enabled,
    commit_threshold: policy.commit_threshold,
  }
}

function draftMatchesPolicy(
  draft: AutomationDraft,
  policy: RepositoryAutomationPolicy
) {
  const current = policyToDraft(policy)
  return (Object.keys(current) as Array<keyof AutomationDraft>).every(
    (key) => current[key] === draft[key]
  )
}

function chooseRepositoryId(
  selectedOrganizationId: string | null,
  manualRepositorySelection: RepositorySelection | null,
  repositories: ManagedRepository[]
) {
  if (
    manualRepositorySelection &&
    manualRepositorySelection.organizationId === selectedOrganizationId &&
    repositories.some((repo) => repo.id === manualRepositorySelection.repositoryId)
  ) {
    return manualRepositorySelection.repositoryId
  }
  return repositories[0]?.id ?? null
}

function currentPolicyDraft(
  automation: RepositoryAutomationResponse | undefined,
  draftState: DraftState | null
) {
  if (!automation) {
    return null
  }
  if (
    draftState &&
    draftState.policyId === automation.policy.id &&
    draftState.policyUpdatedAt === automation.policy.updated_at
  ) {
    return draftState.value
  }
  return policyToDraft(automation.policy)
}

function clampCommitThreshold(value: string) {
  const parsed = Number.parseInt(value, 10)
  if (Number.isNaN(parsed)) {
    return 1
  }
  return Math.min(500, Math.max(1, parsed))
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

function formatStatus(value: string) {
  return value.replaceAll("_", " ")
}

function triggerName(trigger: Record<string, unknown>) {
  const type = trigger.type
  return typeof type === "string" ? formatStatus(type) : "session"
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
