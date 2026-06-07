/* ============================================================
   Cross-repo pages: Opportunities · Sessions · Pull Requests.
   ============================================================ */
import { useMemo } from "react"

import { useCockpit } from "@/cockpit/data"
import {
  oppsFromReport,
  plansFromAutomation,
  plansFromReport,
  sessionsFromAutomation,
} from "@/cockpit/model"
import { PageShell, useGateState } from "@/cockpit/pages/states"
import {
  OpportunitiesView,
  PullsView,
  SessionsView,
} from "@/cockpit/pages/shared-lists"

function useRepoNameLookup(
  repositories: { id: string; name: string }[]
): (id: string) => string {
  return useMemo(() => {
    const map = new Map(repositories.map((r) => [r.id, r.name]))
    return (id: string) => map.get(id) ?? id
  }, [repositories])
}

export function OpportunitiesPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const repoName = useRepoNameLookup(cockpit.repositories)
  const opps = useMemo(() => {
    return cockpit.repositories.flatMap((repo) => {
      const report = cockpit.reportsMap.get(repo.id)
      if (!report) return []
      return oppsFromReport(report, cockpit.automationMap.get(repo.id))
    })
  }, [cockpit.repositories, cockpit.reportsMap, cockpit.automationMap])

  if (gate) return gate
  return (
    <PageShell
      eyebrow="Maintenance"
      eyebrowIcon="Sparkles"
      sub="Detected improvement candidates across all repositories · evidence before recommendation"
      title="Opportunities"
      wide={false}
    >
      <OpportunitiesView opps={opps} repoName={repoName} showRepo />
    </PageShell>
  )
}

export function SessionsPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const repoName = useRepoNameLookup(cockpit.repositories)
  const sessions = useMemo(() => {
    return [...cockpit.automationMap.values()]
      .flatMap(sessionsFromAutomation)
      .sort(
        (a, b) =>
          new Date(b.startedAt ?? 0).getTime() -
          new Date(a.startedAt ?? 0).getTime()
      )
  }, [cockpit.automationMap])

  if (gate) return gate
  return (
    <PageShell
      eyebrow="Execution"
      eyebrowIcon="TerminalSquare"
      sub="Hosted worker runs triggered manually or by automation"
      title="Gardening sessions"
      wide={false}
    >
      <SessionsView repoName={repoName} sessions={sessions} showRepo />
    </PageShell>
  )
}

export function PullsPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const repoName = useRepoNameLookup(cockpit.repositories)
  const plans = useMemo(() => {
    return cockpit.repositories.flatMap((repo) => {
      const report = cockpit.reportsMap.get(repo.id)
      const automation = cockpit.automationMap.get(repo.id)
      if (report) return plansFromReport(report, automation)
      return automation ? plansFromAutomation(automation) : []
    })
  }, [cockpit.repositories, cockpit.reportsMap, cockpit.automationMap])

  if (gate) return gate
  return (
    <PageShell
      eyebrow="Execution"
      eyebrowIcon="GitPullRequest"
      sub="Focused, verified maintenance PR plans — planned, blocked, opened, merged"
      title="Pull requests"
    >
      <PullsView plans={plans} repoName={repoName} showRepo />
    </PageShell>
  )
}
