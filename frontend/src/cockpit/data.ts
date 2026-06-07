/* ============================================================
   Cockpit data layer — TanStack Query hooks over the real API.
   ============================================================ */
import { useMemo } from "react"
import { useQueries, useQuery } from "@tanstack/react-query"

import {
  fetchRepositoryAutomation,
  type RepositoryAutomationResponse,
} from "@/features/automation/automation-api"
import {
  FirstReportNotReadyError,
  fetchFirstReport,
} from "@/features/first-report/first-report-api"
import type { FirstReport } from "@/features/first-report/first-report-contract"
import {
  fetchOrganizationBilling,
  fetchOrganizationRepositories,
  fetchOrganizations,
  isGithubOnboardingAuthenticationRequired,
  type BillingResponse,
  type ManagedRepository,
  type Organization,
} from "@/features/github-onboarding/github-onboarding-api"

const EMPTY_REPOS: ManagedRepository[] = []

export function useOrganizations() {
  return useQuery({
    queryFn: () => fetchOrganizations(),
    queryKey: ["cockpit", "organizations"],
    retry: false,
  })
}

export function useSelectedOrganization() {
  const query = useOrganizations()
  const organization: Organization | null =
    query.data?.organizations[0] ?? null
  return {
    authRequired: isGithubOnboardingAuthenticationRequired(query.error),
    isError: query.isError,
    isLoading: query.isLoading,
    organization,
    query,
  }
}

export function useRepositories(organizationId: string | undefined) {
  return useQuery({
    enabled: Boolean(organizationId),
    queryFn: () => fetchOrganizationRepositories(organizationId ?? ""),
    queryKey: ["cockpit", "repositories", organizationId],
    retry: false,
  })
}

export function useBilling(organizationId: string | undefined) {
  return useQuery<BillingResponse>({
    enabled: Boolean(organizationId),
    queryFn: () => fetchOrganizationBilling(organizationId ?? ""),
    queryKey: ["cockpit", "billing", organizationId],
    retry: false,
  })
}

export type AutomationQueryResult = {
  repositoryId: string
  data?: RepositoryAutomationResponse
  isLoading: boolean
  isError: boolean
}

export function useAutomationMap(
  organizationId: string | undefined,
  repositories: ManagedRepository[]
) {
  const results = useQueries({
    queries: repositories.map((repository) => ({
      enabled: Boolean(organizationId),
      queryFn: () =>
        fetchRepositoryAutomation(organizationId ?? "", repository.id),
      queryKey: ["cockpit", "automation", organizationId, repository.id],
      retry: false,
    })),
  })

  return useMemo(() => {
    const map = new Map<string, RepositoryAutomationResponse>()
    let isLoading = false
    repositories.forEach((repository, index) => {
      const result = results[index]
      if (result?.isLoading) isLoading = true
      if (result?.data) map.set(repository.id, result.data)
    })
    return { isLoading, map }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, repositories])
}

async function fetchReportOrNull(
  repositoryId: string
): Promise<FirstReport | null> {
  try {
    return await fetchFirstReport({ baseline: false, repositoryId })
  } catch (error) {
    if (error instanceof FirstReportNotReadyError) return null
    throw error
  }
}

export function useRepoReport(repositoryId: string | undefined) {
  return useQuery<FirstReport | null>({
    enabled: Boolean(repositoryId),
    queryFn: () => fetchReportOrNull(repositoryId ?? ""),
    queryKey: ["cockpit", "report", repositoryId],
    retry: false,
  })
}

export function useAutomation(
  organizationId: string | undefined,
  repositoryId: string | undefined
) {
  return useQuery<RepositoryAutomationResponse>({
    enabled: Boolean(organizationId && repositoryId),
    queryFn: () =>
      fetchRepositoryAutomation(organizationId ?? "", repositoryId ?? ""),
    queryKey: ["cockpit", "automation", organizationId, repositoryId],
    retry: false,
  })
}

export function useReportsMap(repositories: ManagedRepository[]) {
  const results = useQueries({
    queries: repositories.map((repository) => ({
      queryFn: () => fetchReportOrNull(repository.id),
      queryKey: ["cockpit", "report", repository.id],
      retry: false,
    })),
  })

  return useMemo(() => {
    const map = new Map<string, FirstReport>()
    let isLoading = false
    repositories.forEach((repository, index) => {
      const result = results[index]
      if (result?.isLoading) isLoading = true
      if (result?.data) map.set(repository.id, result.data)
    })
    return { isLoading, map }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, repositories])
}

/**
 * Composite cockpit state used by the cross-repo pages and the shell.
 * Returns the selected org, its repositories, and the per-repo automation +
 * report maps (lazily populated, shared via the query cache).
 */
export function useCockpit() {
  const { authRequired, isError, isLoading, organization } =
    useSelectedOrganization()
  const repositoriesQuery = useRepositories(organization?.id)
  const repositories = repositoriesQuery.data?.repositories ?? EMPTY_REPOS
  const automation = useAutomationMap(organization?.id, repositories)
  const reports = useReportsMap(repositories)

  return {
    authRequired,
    automationMap: automation.map,
    isError,
    organization,
    orgLoading: isLoading,
    reportsMap: reports.map,
    repositories,
    repositoriesError: repositoriesQuery.isError,
    repositoriesLoading: repositoriesQuery.isLoading,
  }
}

export { EMPTY_REPOS }
