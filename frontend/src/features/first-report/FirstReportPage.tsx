import { FirstReportNotReadyError } from "./first-report-api"
import { ArchitectureConstitutionPanels } from "./sections/architecture-constitution-panels"
import { EntropyPanels } from "./sections/entropy-panels"
import { MaintenancePanels } from "./sections/maintenance-panels"
import { ReportHeader } from "./sections/report-header"
import { SessionPanel } from "./sections/session-panel"
import { SummaryMetrics } from "./sections/summary-metrics"
import { buildFirstReportViewModel } from "./first-report-view-model"
import { useFirstReport } from "./use-first-report"
import {
  FirstReportEmptyState,
  FirstReportErrorState,
  FirstReportLoadingState,
} from "./components/report-states"

export function FirstReportPage() {
  const { data, error, isError, isFetching, isLoading, refetch } =
    useFirstReport()

  const retry = () => {
    void refetch()
  }

  if (isLoading) {
    return <FirstReportLoadingState />
  }

  if (isError) {
    if (error instanceof FirstReportNotReadyError) {
      return <FirstReportEmptyState isRetrying={isFetching} onRetry={retry} />
    }

    return <FirstReportErrorState isRetrying={isFetching} onRetry={retry} />
  }

  if (!data) {
    return <FirstReportEmptyState isRetrying={isFetching} onRetry={retry} />
  }

  const report = data
  const view = buildFirstReportViewModel(report)
  const prPlanCount = view.prPlans.length

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 sm:px-6 lg:px-8">
        <ReportHeader
          isLoading={isLoading}
          prPlanCount={prPlanCount}
          repository={view.repository}
          session={view.session}
        />
        <SummaryMetrics
          constitution={view.constitution}
          entropy={view.entropy}
          prPlanCount={prPlanCount}
          session={view.session}
        />
        <EntropyPanels
          entropy={view.entropy}
          logicalSystems={view.logicalSystems}
        />
        <ArchitectureConstitutionPanels
          architecture={view.architecture}
          constitution={view.constitution}
        />
        <SessionPanel session={view.session} />
        <MaintenancePanels
          opportunities={view.opportunities}
          prPlans={view.prPlans}
        />
      </div>
    </main>
  )
}
