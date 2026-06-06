import { useMemo, useState } from "react"
import type { ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  GitBranch,
  RefreshCw,
  Settings,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  fetchInstallationStart,
  fetchOrganizationRepositories,
  fetchOrganizations,
  GithubOnboardingRequestError,
  type ManagedRepository,
  type Organization,
} from "./github-onboarding-api"

type CallbackStatus = "installed" | "pending" | "error" | null
const EMPTY_ORGANIZATIONS: Organization[] = []

export function GithubOnboardingPage() {
  const searchParams = new URLSearchParams(window.location.search)
  const callbackStatus = normalizeCallbackStatus(searchParams.get("status"))
  const callbackOrganizationId = searchParams.get("organization_id")
  const callbackError = searchParams.get("error")
  const [manualOrganizationId, setManualOrganizationId] = useState<
    string | null
  >(null)

  const installationStartQuery = useQuery({
    queryKey: ["github-onboarding", "installation-start"],
    queryFn: () => fetchInstallationStart(),
    retry: false,
  })
  const organizationsQuery = useQuery({
    queryKey: ["github-onboarding", "organizations"],
    queryFn: () => fetchOrganizations(),
    retry: false,
  })

  const organizations =
    organizationsQuery.data?.organizations ?? EMPTY_ORGANIZATIONS
  const selectedOrganizationId = useMemo(
    () =>
      chooseOrganizationId({
        callbackOrganizationId,
        manualOrganizationId,
        organizations,
      }),
    [callbackOrganizationId, manualOrganizationId, organizations]
  )

  const repositoriesQuery = useQuery({
    queryKey: ["github-onboarding", "repositories", selectedOrganizationId],
    queryFn: () => fetchOrganizationRepositories(selectedOrganizationId ?? ""),
    enabled: Boolean(selectedOrganizationId),
    retry: false,
  })

  const installUrl = installationStartQuery.data?.install_url
  const isPreInstallForbidden =
    organizationsQuery.error instanceof GithubOnboardingRequestError &&
    organizationsQuery.error.status === 403
  const hasOrganizationError =
    organizationsQuery.isError && !isPreInstallForbidden
  const hasBlockingError =
    installationStartQuery.isError ||
    hasOrganizationError ||
    repositoriesQuery.isError

  if (installationStartQuery.isLoading && !installUrl) {
    return (
      <OnboardingState
        icon={<CircleDashed className="size-5 animate-spin" />}
        title="Loading GitHub onboarding"
      />
    )
  }

  if (hasBlockingError) {
    return (
      <OnboardingState
        action={
          <Button
            aria-label="Retry GitHub onboarding"
            onClick={() => {
              void installationStartQuery.refetch()
              void organizationsQuery.refetch()
              if (selectedOrganizationId) {
                void repositoriesQuery.refetch()
              }
            }}
            type="button"
            variant="outline"
          >
            <RefreshCw />
            Retry
          </Button>
        }
        icon={<AlertTriangle className="size-5 text-destructive" />}
        title="Could not load GitHub onboarding"
      />
    )
  }

  const repositories = repositoriesQuery.data?.repositories ?? []
  const installation = repositoriesQuery.data?.installation

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <GitBranch className="size-4" />
              GitHub App
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal">
              GitHub onboarding
            </h1>
          </div>
          {installUrl ? (
            <Button asChild>
              <a href={installUrl}>
                <GitBranch />
                Install GitHub App
              </a>
            </Button>
          ) : null}
        </header>

        <CallbackBanner errorCode={callbackError} status={callbackStatus} />

        {organizations.length > 1 ? (
          <OrganizationSelector
            organizations={organizations}
            selectedOrganizationId={selectedOrganizationId}
            onSelect={setManualOrganizationId}
          />
        ) : null}

        {organizations.length === 0 ? (
          <EmptyOnboardingPanel installUrl={installUrl} />
        ) : (
          <RepositorySelectionPanel
            isLoading={repositoriesQuery.isLoading}
            repositories={repositories}
            settingsUrl={installation?.html_url}
          />
        )}
      </div>
    </main>
  )
}

function CallbackBanner({
  errorCode,
  status,
}: {
  errorCode: string | null
  status: CallbackStatus
}) {
  if (status === "installed") {
    return (
      <StatusBand icon={<CheckCircle2 className="size-4" />} tone="success">
        GitHub App installed
      </StatusBand>
    )
  }

  if (status === "pending") {
    return (
      <StatusBand icon={<CircleDashed className="size-4" />} tone="neutral">
        Installation request pending approval
      </StatusBand>
    )
  }

  if (status === "error") {
    return (
      <StatusBand icon={<AlertTriangle className="size-4" />} tone="danger">
        GitHub callback could not be verified
        {errorCode ? (
          <span className="font-mono text-xs text-muted-foreground">
            {errorCode}
          </span>
        ) : null}
      </StatusBand>
    )
  }

  return null
}

function OrganizationSelector({
  onSelect,
  organizations,
  selectedOrganizationId,
}: {
  onSelect: (organizationId: string) => void
  organizations: Organization[]
  selectedOrganizationId: string | null
}) {
  return (
    <label className="flex max-w-sm flex-col gap-2 text-sm font-medium">
      Organization
      <select
        className="h-9 rounded-md border bg-background px-3 text-sm font-normal"
        onChange={(event) => onSelect(event.target.value)}
        value={selectedOrganizationId ?? ""}
      >
        {organizations.map((organization) => (
          <option key={organization.id} value={organization.id}>
            {organization.github_login}
          </option>
        ))}
      </select>
    </label>
  )
}

function EmptyOnboardingPanel({ installUrl }: { installUrl?: string }) {
  return (
    <section className="rounded-md border border-dashed bg-muted/30 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-normal">
            No GitHub installation
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            No managed repositories are connected to this Gardener workspace.
          </p>
        </div>
        {installUrl ? (
          <Button asChild>
            <a href={installUrl}>
              <GitBranch />
              Install GitHub App
            </a>
          </Button>
        ) : null}
      </div>
    </section>
  )
}

function RepositorySelectionPanel({
  isLoading,
  repositories,
  settingsUrl,
}: {
  isLoading: boolean
  repositories: Array<{
    id: string
    complexity: ManagedRepository["complexity"]
    default_branch: string
    full_name: string
    html_url: string
    private: boolean
  }>
  settingsUrl?: string
}) {
  return (
    <section className="rounded-md border bg-card p-5 text-card-foreground">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CheckCircle2 className="size-4 text-primary" />
            <h2>Selected repositories</h2>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {repositories.length} active{" "}
            {repositories.length === 1 ? "repository" : "repositories"}
          </p>
        </div>
        {settingsUrl ? (
          <Button asChild variant="outline">
            <a href={settingsUrl}>
              <Settings />
              Edit repository access in GitHub
              <ExternalLink />
            </a>
          </Button>
        ) : null}
      </div>

      <div className="mt-5">
        {isLoading ? (
          <div className="flex items-center gap-2 rounded-md border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
            <CircleDashed className="size-4 animate-spin" />
            Loading selected repositories
          </div>
        ) : repositories.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
            No selected repositories
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full min-w-[52rem] table-fixed text-left text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground uppercase">
                <tr>
                  <th className="w-4/12 px-3 py-2 font-medium">Repository</th>
                  <th className="w-2/12 px-3 py-2 font-medium">
                    Default branch
                  </th>
                  <th className="w-2/12 px-3 py-2 font-medium">Visibility</th>
                  <th className="w-4/12 px-3 py-2 font-medium">Complexity</th>
                </tr>
              </thead>
              <tbody>
                {repositories.map((repository) => (
                  <tr className="border-t" key={repository.id}>
                    <td className="truncate px-3 py-3 font-medium">
                      <a
                        className="hover:text-primary hover:underline"
                        href={repository.html_url}
                      >
                        {repository.full_name}
                      </a>
                    </td>
                    <td className="truncate px-3 py-3 text-muted-foreground">
                      {repository.default_branch || "main"}
                    </td>
                    <td className="px-3 py-3 text-muted-foreground">
                      {repository.private ? "Private" : "Public"}
                    </td>
                    <td className="px-3 py-3">
                      <RepositoryComplexity complexity={repository.complexity} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

function RepositoryComplexity({
  complexity,
}: {
  complexity: ManagedRepository["complexity"]
}) {
  if (complexity.input_status === "complete") {
    return (
      <div className="flex min-w-0 flex-col gap-1">
        <span className="font-medium">{formatMultiplier(complexity.multiplier)}</span>
        <span className="truncate text-xs text-muted-foreground">
          {formatComplexityInputs(complexity)}
        </span>
      </div>
    )
  }

  if (complexity.input_status === "partial") {
    return (
      <div className="flex min-w-0 flex-col gap-1">
        <span className="font-medium">Partial / 1.0x</span>
        <span className="truncate text-xs text-muted-foreground">
          {formatComplexityInputs(complexity)}
        </span>
      </div>
    )
  }

  if (complexity.input_status === "restricted") {
    return (
      <div className="flex min-w-0 flex-col gap-1">
        <span className="font-medium">Restricted</span>
        <span className="truncate text-xs text-muted-foreground">
          Owner or admin can view billing inputs
        </span>
      </div>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="font-medium">Unknown / 1.0x</span>
      <span className="truncate text-xs text-muted-foreground">
        Waiting for LOC, modules, and contributors
      </span>
    </div>
  )
}

function formatMultiplier(multiplier: number) {
  return multiplier === 1 ? "1.0x" : `${multiplier.toFixed(2)}x`
}

function formatComplexityInputs(complexity: ManagedRepository["complexity"]) {
  return [
    complexity.loc == null ? "Unknown LOC" : `${formatNumber(complexity.loc)} LOC`,
    complexity.module_count == null
      ? "Unknown modules"
      : `${formatNumber(complexity.module_count)} modules`,
    complexity.contributor_count == null
      ? "Unknown contributors"
      : `${formatNumber(complexity.contributor_count)} contributors`,
  ].join(" · ")
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value)
}

function StatusBand({
  children,
  icon,
  tone,
}: {
  children: ReactNode
  icon: ReactNode
  tone: "danger" | "neutral" | "success"
}) {
  const toneClassName = {
    danger: "border-destructive/30 bg-destructive/10 text-destructive",
    neutral: "border-border bg-muted/40 text-foreground",
    success: "border-primary/30 bg-primary/10 text-foreground",
  }[tone]

  return (
    <div
      className={`flex flex-wrap items-center gap-2 rounded-md border px-4 py-3 text-sm font-medium ${toneClassName}`}
    >
      {icon}
      {children}
    </div>
  )
}

function OnboardingState({
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
      <div className="mx-auto flex min-h-svh w-full max-w-7xl items-center px-5 py-6 sm:px-6 lg:px-8">
        <section className="flex w-full flex-col gap-4 rounded-md border bg-card p-6 text-card-foreground sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="text-primary">{icon}</div>
            <h1 className="text-2xl font-semibold tracking-normal">{title}</h1>
          </div>
          {action}
        </section>
      </div>
    </main>
  )
}

function chooseOrganizationId({
  callbackOrganizationId,
  manualOrganizationId,
  organizations,
}: {
  callbackOrganizationId: string | null
  manualOrganizationId: string | null
  organizations: Organization[]
}) {
  if (
    manualOrganizationId &&
    organizations.some(
      (organization) => organization.id === manualOrganizationId
    )
  ) {
    return manualOrganizationId
  }

  if (
    callbackOrganizationId &&
    organizations.some(
      (organization) => organization.id === callbackOrganizationId
    )
  ) {
    return callbackOrganizationId
  }

  return organizations[0]?.id ?? null
}

function normalizeCallbackStatus(status: string | null): CallbackStatus {
  if (status === "installed" || status === "pending" || status === "error") {
    return status
  }
  return null
}
