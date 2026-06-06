import { useMemo } from "react"
import type { ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  CircleDashed,
  CircleOff,
  FileText,
  GitBranch,
  Settings,
  Zap,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  fetchOrganizationBilling,
  fetchOrganizationRepositories,
  fetchOrganizations,
  GithubOnboardingRequestError,
  type ManagedRepository,
} from "@/features/github-onboarding/github-onboarding-api"

export function App() {
  const organizationsQuery = useQuery({
    queryKey: ["overview", "organizations"],
    queryFn: () => fetchOrganizations(),
    retry: false,
  })

  const selectedOrganization = organizationsQuery.data?.organizations[0] ?? null
  const repositoriesQuery = useQuery({
    queryKey: ["overview", "repositories", selectedOrganization?.id],
    queryFn: () => fetchOrganizationRepositories(selectedOrganization?.id ?? ""),
    enabled: Boolean(selectedOrganization?.id),
    retry: false,
  })
  const billingQuery = useQuery({
    queryKey: ["overview", "billing", selectedOrganization?.id],
    queryFn: () => fetchOrganizationBilling(selectedOrganization?.id ?? ""),
    enabled: Boolean(selectedOrganization?.id),
    retry: false,
  })

  const repositories = repositoriesQuery.data?.repositories ?? []
  const topRepositories = useMemo(() => repositories.slice(0, 4), [repositories])
  const isPreInstallForbidden =
    organizationsQuery.error instanceof GithubOnboardingRequestError &&
    organizationsQuery.error.status === 403

  if (organizationsQuery.isLoading) {
    return (
      <OverviewState
        icon={<CircleDashed className="size-5 animate-spin" />}
        title="Loading overview"
      />
    )
  }

  if (organizationsQuery.isError && !isPreInstallForbidden) {
    return (
      <OverviewState
        icon={<AlertTriangle className="size-5 text-destructive" />}
        title="Could not load overview"
      />
    )
  }

  if (isPreInstallForbidden || !selectedOrganization) {
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
        <header className="flex flex-col gap-2 border-b pb-5">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Bot className="size-4" />
            Overview
          </div>
          <h1 className="text-3xl font-semibold tracking-normal">
            Gardener operations
          </h1>
          <p className="text-sm text-muted-foreground">
            {selectedOrganization.github_login}
          </p>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <OverviewLink
            href="/onboarding/github"
            icon={<GitBranch className="size-4" />}
            label="GitHub setup"
            value={
              repositoriesQuery.isLoading
                ? "Loading"
                : `${repositories.length} repositories`
            }
          />
          <OverviewLink
            href="/automation"
            icon={<Zap className="size-4" />}
            label="Automation"
            value={
              billingQuery.data?.subscription.autonomous_pr_add_on_enabled
                ? "PR add-on on"
                : "PR add-on off"
            }
          />
          <OverviewLink
            href="/report"
            icon={<FileText className="size-4" />}
            label="First report"
            value="Open report"
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
                  : `${repositories.length} active`}
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
            isLoading={repositoriesQuery.isLoading}
            repositories={topRepositories}
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
  isLoading,
  repositories,
}: {
  isLoading: boolean
  repositories: ManagedRepository[]
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
    <div className="mt-5 divide-y rounded-md border">
      {repositories.map((repository) => (
        <div
          className="grid gap-2 px-3 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_8rem_8rem]"
          key={repository.id}
        >
          <div className="min-w-0 truncate font-medium">
            {repository.full_name}
          </div>
          <div className="text-muted-foreground">
            {repository.default_branch || "unknown"}
          </div>
          <div className="text-muted-foreground">
            {repository.complexity.multiplier.toFixed(2)}x
          </div>
        </div>
      ))}
    </div>
  )
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
