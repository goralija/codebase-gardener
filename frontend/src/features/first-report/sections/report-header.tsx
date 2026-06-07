import { CheckCircle2, CircleDashed, FileText } from "lucide-react"

import type { FirstReportViewModel } from "../first-report-view-model"

type ReportHeaderProps = {
  isLoading: boolean
  prPlanCount: number
  repository: FirstReportViewModel["repository"]
  session: FirstReportViewModel["session"]
}

export function ReportHeader({
  isLoading,
  prPlanCount,
  repository,
  session,
}: ReportHeaderProps) {
  const focusedPrPlanLabel =
    prPlanCount === 1 ? "1 focused PR plan" : `${prPlanCount} focused PR plans`

  return (
    <header className="border-b pb-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex max-w-3xl flex-col gap-3">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <FileText className="size-5" />
            Repository report
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">
              First report
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              {repository.id} at commit {repository.shortCommitSha}. The latest
              session is {session.status.toLowerCase()} with {focusedPrPlanLabel}.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          {isLoading ? (
            <>
              <CircleDashed className="size-4 animate-spin" />
              Loading report
            </>
          ) : (
            <>
              <CheckCircle2 className="size-4 text-primary" />
              Report ready
            </>
          )}
        </div>
      </div>
    </header>
  )
}
