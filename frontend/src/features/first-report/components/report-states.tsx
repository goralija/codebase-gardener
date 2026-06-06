import {
  AlertTriangle,
  CircleDashed,
  FileSearch,
  RefreshCw,
} from "lucide-react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"

type ReportStateLayoutProps = {
  children?: ReactNode
  description: string
  icon: ReactNode
  title: string
}

type RetryStateProps = {
  isRetrying: boolean
  onRetry: () => void
}

function ReportStateLayout({
  children,
  description,
  icon,
  title,
}: ReportStateLayoutProps) {
  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex min-h-svh w-full max-w-7xl items-center px-5 py-6 sm:px-6 lg:px-8">
        <section className="w-full rounded-md border bg-card p-6 text-card-foreground">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex max-w-2xl gap-3">
              <div className="mt-0.5 text-primary">{icon}</div>
              <div>
                <h1 className="text-2xl font-semibold tracking-normal">
                  {title}
                </h1>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {description}
                </p>
              </div>
            </div>
            {children}
          </div>
        </section>
      </div>
    </main>
  )
}

export function FirstReportLoadingState() {
  return (
    <ReportStateLayout
      description="Gardener is loading the latest first report from the API."
      icon={<CircleDashed className="size-5 animate-spin" />}
      title="Loading first report"
    />
  )
}

export function FirstReportEmptyState({
  isRetrying,
  onRetry,
}: RetryStateProps) {
  return (
    <ReportStateLayout
      description="No first report is available for this repository yet."
      icon={<FileSearch className="size-5" />}
      title="First report is not ready"
    >
      <Button
        aria-label="Retry first report"
        disabled={isRetrying}
        onClick={onRetry}
        type="button"
        variant="outline"
      >
        <RefreshCw className={isRetrying ? "animate-spin" : undefined} />
        Retry
      </Button>
    </ReportStateLayout>
  )
}

export function FirstReportErrorState({
  isRetrying,
  onRetry,
}: RetryStateProps) {
  return (
    <ReportStateLayout
      description="The first report API returned an error or data that does not match the shared contract."
      icon={<AlertTriangle className="size-5 text-destructive" />}
      title="Could not load first report"
    >
      <Button
        aria-label="Retry first report"
        disabled={isRetrying}
        onClick={onRetry}
        type="button"
        variant="outline"
      >
        <RefreshCw className={isRetrying ? "animate-spin" : undefined} />
        Retry
      </Button>
    </ReportStateLayout>
  )
}
