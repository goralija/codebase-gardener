import type { ReactNode } from "react"
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleOff,
  FileText,
  GitBranch,
  GitPullRequest,
  Gauge,
  Settings,
  Trash2,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  fetchRepositoryAutomation,
  type RepositoryAutomationResponse,
} from "@/features/automation/automation-api"
import {
  deleteManagedRepository,
  fetchOrganizationRepositories,
  fetchOrganizations,
  isGithubOnboardingAuthenticationRequired,
  type ManagedRepository,
} from "@/features/github-onboarding/github-onboarding-api"

const EMPTY_REPOSITORIES: ManagedRepository[] = []

type RepositoryStatsView = {
  hasBaseline: boolean
  repositoryId: string
  stats?: RepositoryAutomationResponse["stats"]
  status: "error" | "loading" | "ready"
}

export function App() {
  const queryClient = useQueryClient()
  const organizationsQuery = useQuery({
    queryKey: ["overview", "organizations"],
    queryFn: () => fetchOrganizations(),
    retry: false,
  })

  const selectedOrganization = organizationsQuery.data?.organizations[0] ?? null
  const repositoriesQuery = useQuery({
    queryKey: ["overview", "repositories", selectedOrganization?.id],
    queryFn: () =>
      fetchOrganizationRepositories(selectedOrganization?.id ?? ""),
    enabled: Boolean(selectedOrganization?.id),
    retry: false,
  })

  const repositories =
    repositoriesQuery.data?.repositories ?? EMPTY_REPOSITORIES
  const repositoryAutomationQueries = useQueries({
    queries: repositories.map((repository) => ({
      queryKey: [
        "overview",
        "repository-automation",
        selectedOrganization?.id,
        repository.id,
      ],
      queryFn: () =>
        fetchRepositoryAutomation(
          selectedOrganization?.id ?? "",
          repository.id
        ),
      enabled: Boolean(selectedOrganization?.id),
      retry: false,
    })),
  })
  const repositoryStats = repositories.map((repository, index) =>
    buildRepositoryStats(repository, repositoryAutomationQueries[index])
  )
  const repositoryStatsById = new Map(
    repositoryStats.map((stats) => [stats.repositoryId, stats])
  )
  const aggregateStats = aggregateRepositoryStats(repositoryStats)
  const statsAreLoading =
    repositoriesQuery.isLoading ||
    repositoryStats.some((stats) => stats.status === "loading")
  const statsUnavailable =
    repositories.length > 0 &&
    !statsAreLoading &&
    repositoryStats.every((stats) => stats.status === "error")
  const isAuthenticationRequired = isGithubOnboardingAuthenticationRequired(
    organizationsQuery.error
  )
  const deleteRepositoryMutation = useMutation({
    mutationFn: (repository: ManagedRepository) =>
      deleteManagedRepository(selectedOrganization?.id ?? "", repository.id),
    onSuccess: async () => {
      if (!selectedOrganization?.id) {
        return
      }
      await queryClient.invalidateQueries({
        queryKey: ["overview", "repositories", selectedOrganization.id],
      })
      await queryClient.invalidateQueries({
        queryKey: [
          "overview",
          "repository-automation",
          selectedOrganization.id,
        ],
      })
    },
  })

  if (organizationsQuery.isLoading) {
    return (
      <OverviewState
        icon={<CircleDashed className="size-5 animate-spin" />}
        title="Loading overview"
      />
    )
  }

  if (organizationsQuery.isError && !isAuthenticationRequired) {
    return (
      <OverviewState
        icon={<AlertTriangle className="size-5 text-destructive" />}
        title="Could not load overview"
      />
    )
  }

  if (isAuthenticationRequired) {
    return (
      <OverviewState
        action={
          <Button asChild>
            <a href="/onboarding/github">
              <GitBranch />
              GitHub setup
            </a>
          </Button>
        }
        icon={<CircleOff className="size-5 text-muted-foreground" />}
        title="GitHub session required"
      />
    )
  }

  if (!selectedOrganization) {
    return (
      <OverviewState
        action={
          <Button asChild>
            <a href="/onboarding/github">
              <GitBranch />
              GitHub setup
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
        <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Gauge className="size-5" />
              Overview
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal">
              Gardener operations
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {selectedOrganization.github_login}
            </p>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <OverviewLink
            href="/onboarding/github"
            icon={<GitBranch className="size-4" />}
            label="Managed repositories"
            value={
              repositoriesQuery.isLoading
                ? "Loading"
                : `${repositories.length} repositories`
            }
          />
          <OverviewLink
            href={firstReportHref(repositories[0], repositoryStats[0])}
            icon={<FileText className="size-4" />}
            label="Reports generated"
            value={formatAggregateCount(
              aggregateStats.reportCount,
              "report",
              "reports",
              statsAreLoading,
              statsUnavailable
            )}
          />
          <OverviewLink
            href="/automation"
            icon={<GitPullRequest className="size-4" />}
            label="Focused PRs created"
            value={formatAggregateCount(
              aggregateStats.createdPrCount,
              "PR",
              "PRs",
              statsAreLoading,
              statsUnavailable
            )}
          />
        </section>

        <section className="rounded-md border bg-card p-5 text-card-foreground">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold">
                <CheckCircle2 className="size-4 text-primary" />
                <h2>Managed repositories</h2>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {repositoriesQuery.isLoading
                  ? "Loading repositories"
                  : `${repositories.length} active repositories`}
              </p>
            </div>
            <Button asChild variant="outline">
              <a href="/automation">
                <Settings />
                Automation
              </a>
            </Button>
          </div>

          <RepositoryList
            deleteError={deleteRepositoryMutation.isError}
            deletingRepositoryId={
              deleteRepositoryMutation.isPending
                ? (deleteRepositoryMutation.variables?.id ?? null)
                : null
            }
            isLoading={repositoriesQuery.isLoading}
            onDeleteRepository={(repository) => {
              if (
                window.confirm(
                  `Permanently remove ${repository.full_name} and all stored Gardener data for it? This cannot be undone.`
                )
              ) {
                deleteRepositoryMutation.mutate(repository)
              }
            }}
            repositories={repositories}
            statsByRepositoryId={repositoryStatsById}
          />
        </section>
      </div>
    </main>
  )
}

function OverviewLink({
  href,
  icon,
  label,
  value,
}: {
  href: string
  icon: ReactNode
  label: string
  value: string
}) {
  return (
    <a
      className="rounded-md border bg-card p-5 text-card-foreground transition hover:bg-muted/40"
      href={href}
    >
      <span className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        {label}
      </span>
      <span className="mt-3 block text-2xl font-semibold tracking-normal">
        {value}
      </span>
    </a>
  )
}

function RepositoryList({
  deleteError,
  deletingRepositoryId,
  isLoading,
  onDeleteRepository,
  repositories,
  statsByRepositoryId,
}: {
  deleteError: boolean
  deletingRepositoryId: string | null
  isLoading: boolean
  onDeleteRepository: (repository: ManagedRepository) => void
  repositories: ManagedRepository[]
  statsByRepositoryId: Map<string, RepositoryStatsView>
}) {
  if (isLoading) {
    return (
      <div className="mt-5 flex items-center gap-2 rounded-md border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
        <CircleDashed className="size-4 animate-spin" />
        Loading selected repositories
      </div>
    )
  }

  if (repositories.length === 0) {
    return (
      <div className="mt-5 rounded-md border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
        No selected repositories
      </div>
    )
  }

  return (
    <>
      {deleteError ? (
        <div className="mt-5 flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertTriangle className="size-4" />
          Repository removal failed
        </div>
      ) : null}
      <div className="mt-5 divide-y rounded-md border">
        {repositories.map((repository) => {
          const isDeleting = deletingRepositoryId === repository.id
          return (
            <div
              className="grid gap-4 px-3 py-4 text-sm sm:grid-cols-2 lg:grid-cols-[minmax(0,1.35fr)_8rem_8rem_8rem_minmax(0,1fr)_2.5rem]"
              key={repository.id}
            >
              <div className="min-w-0">
                <a
                  className="block truncate font-medium underline-offset-4 hover:underline"
                  href={repositoryReportHref(
                    repository.id,
                    statsByRepositoryId.get(repository.id)?.hasBaseline ?? false
                  )}
                >
                  {repository.full_name}
                </a>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {repository.default_branch || "unknown"} branch
                </p>
              </div>
              <RepositoryStat
                detail={latestReportLabel(statsByRepositoryId.get(repository.id))}
                label="Reports"
                value={repositoryCountLabel(
                  statsByRepositoryId.get(repository.id),
                  "report_count",
                  "report",
                  "reports"
                )}
              />
              <RepositoryStat
                detail={prOutcomeLabel(statsByRepositoryId.get(repository.id))}
                label="PRs"
                value={repositoryCountLabel(
                  statsByRepositoryId.get(repository.id),
                  "created_pr_count",
                  "PR",
                  "PRs"
                )}
              />
              <RepositoryStat
                detail={completedSessionLabel(
                  statsByRepositoryId.get(repository.id)
                )}
                label="Sessions"
                value={repositoryCountLabel(
                  statsByRepositoryId.get(repository.id),
                  "session_count",
                  "session",
                  "sessions"
                )}
              />
              <RepositoryStat
                detail={prPlanLabel(statsByRepositoryId.get(repository.id))}
                label="Status"
                value={baselineLabel(statsByRepositoryId.get(repository.id))}
              />
              <div className="flex items-start justify-end">
                <Button
                  aria-label={`Remove ${repository.full_name}`}
                  disabled={isDeleting}
                  onClick={() => onDeleteRepository(repository)}
                  size="icon"
                  title={`Remove ${repository.full_name}`}
                  type="button"
                  variant="ghost"
                >
                  {isDeleting ? (
                    <CircleDashed className="animate-spin" />
                  ) : (
                    <Trash2 />
                  )}
                </Button>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}

function RepositoryStat({
  detail,
  label,
  value,
}: {
  detail: string
  label: string
  value: string
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-semibold">{value}</div>
      <div className="mt-1 truncate text-xs text-muted-foreground">
        {detail}
      </div>
    </div>
  )
}

function buildRepositoryStats(
  repository: ManagedRepository,
  query:
    | {
        data?: RepositoryAutomationResponse
        isError: boolean
        isLoading: boolean
      }
    | undefined
): RepositoryStatsView {
  if (!query || query.isLoading) {
    return {
      hasBaseline: false,
      repositoryId: repository.id,
      status: "loading",
    }
  }

  if (query.isError || !query.data) {
    return {
      hasBaseline: false,
      repositoryId: repository.id,
      status: "error",
    }
  }

  return {
    hasBaseline: Boolean(query.data.baseline.commit_sha),
    repositoryId: repository.id,
    stats: query.data.stats,
    status: "ready",
  }
}

function aggregateRepositoryStats(repositoryStats: RepositoryStatsView[]) {
  return repositoryStats.reduce(
    (totals, repositoryStat) => {
      if (repositoryStat.status !== "ready" || !repositoryStat.stats) {
        return totals
      }

      return {
        createdPrCount:
          totals.createdPrCount + repositoryStat.stats.created_pr_count,
        reportCount: totals.reportCount + repositoryStat.stats.report_count,
      }
    },
    { createdPrCount: 0, reportCount: 0 }
  )
}

function repositoryCountLabel(
  stats: RepositoryStatsView | undefined,
  field: keyof RepositoryAutomationResponse["stats"],
  singular: string,
  plural: string
) {
  if (!stats || stats.status === "loading") {
    return "Loading"
  }
  if (stats.status === "error" || !stats.stats) {
    return "Unavailable"
  }

  return countLabel(Number(stats.stats[field]), singular, plural)
}

function formatAggregateCount(
  count: number,
  singular: string,
  plural: string,
  isLoading: boolean,
  isUnavailable: boolean
) {
  if (isLoading) {
    return "Loading"
  }
  if (isUnavailable) {
    return "Unavailable"
  }

  return countLabel(count, singular, plural)
}

function countLabel(count: number, singular: string, plural: string) {
  return count === 1 ? `1 ${singular}` : `${count} ${plural}`
}

function latestReportLabel(stats: RepositoryStatsView | undefined) {
  if (!stats || stats.status === "loading") {
    return "Checking reports"
  }
  if (stats.status === "error" || !stats.stats) {
    return "Report stats unavailable"
  }

  return stats.stats.latest_report_at
    ? `Latest ${formatDate(stats.stats.latest_report_at)}`
    : "No reports yet"
}

function prOutcomeLabel(stats: RepositoryStatsView | undefined) {
  if (!stats || stats.status === "loading") {
    return "Checking PRs"
  }
  if (stats.status === "error" || !stats.stats) {
    return "PR stats unavailable"
  }

  return `${stats.stats.merged_pr_count} merged, ${stats.stats.blocked_pr_count} blocked`
}

function completedSessionLabel(stats: RepositoryStatsView | undefined) {
  if (!stats || stats.status === "loading") {
    return "Checking sessions"
  }
  if (stats.status === "error" || !stats.stats) {
    return "Session stats unavailable"
  }

  return countLabel(
    stats.stats.completed_session_count,
    "completed",
    "completed"
  )
}

function prPlanLabel(stats: RepositoryStatsView | undefined) {
  if (!stats || stats.status === "loading") {
    return "Checking status"
  }
  if (stats.status === "error" || !stats.stats) {
    return "Status unavailable"
  }

  return countLabel(stats.stats.pr_plan_count, "PR plan", "PR plans")
}

function baselineLabel(stats: RepositoryStatsView | undefined) {
  if (!stats || stats.status === "loading") {
    return "Loading"
  }
  if (stats.status === "error") {
    return "Unavailable"
  }

  return stats.hasBaseline ? "Baseline ready" : "No baseline"
}

function firstReportHref(
  repository: ManagedRepository | undefined,
  stats: RepositoryStatsView | undefined
) {
  if (!repository) {
    return "/report"
  }

  return repositoryReportHref(repository.id, stats?.hasBaseline ?? false)
}

function repositoryReportHref(repositoryId: string, hasBaseline: boolean) {
  return hasBaseline
    ? `/report?repositoryId=${repositoryId}&baseline=1`
    : `/report?repositoryId=${repositoryId}`
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return "unknown date"
  }

  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
  }).format(date)
}

function OverviewState({
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

export default App
