import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, GitBranch, Sprout } from "lucide-react"

import firstReportFixture from "../../fixtures/contracts/first_report_fixture.json"
import { Button } from "@/components/ui/button"

type FirstReportFixture = typeof firstReportFixture

function useFirstReportFixture() {
  return useQuery<FirstReportFixture>({
    queryKey: ["first-report-fixture"],
    queryFn: () => Promise.resolve(firstReportFixture),
  })
}

export function App() {
  const { data } = useFirstReportFixture()
  const report = data ?? firstReportFixture
  const entropy = report.entropy_report.score
  const opportunity = report.maintenance_opportunities[0]
  const prPlan = report.maintenance_pr_plans[0]

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-8">
        <header className="flex flex-col gap-4 border-b pb-6 md:flex-row md:items-end md:justify-between">
          <div className="flex max-w-3xl flex-col gap-3">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Sprout data-icon="inline-start" />
              Foundation workspace
            </div>
            <h1 className="text-3xl font-semibold tracking-normal md:text-4xl">
              Codebase Gardener
            </h1>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
              First-report fixture data is wired through TanStack Query so Lane A
              can replace it with DRF responses without changing the screen
              contract.
            </p>
          </div>
          <Button asChild>
            <a href="http://localhost:8000/api/v1/health/">
              <CheckCircle2 data-icon="inline-start" />
              API health
            </a>
          </Button>
        </header>

        <section className="grid gap-4 md:grid-cols-[1fr_2fr]">
          <div className="rounded-lg border bg-card p-5 text-card-foreground">
            <p className="text-sm font-medium text-muted-foreground">
              Repository Entropy Score
            </p>
            <div className="mt-4 flex items-end gap-3">
              <span className="text-5xl font-semibold">{entropy.overall}</span>
              <span className="pb-2 text-sm capitalize text-muted-foreground">
                {entropy.classification}
              </span>
            </div>
          </div>

          <div className="rounded-lg border bg-card p-5 text-card-foreground">
            <p className="text-sm font-medium text-muted-foreground">
              Logical systems
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {report.analysis_snapshot.logical_systems.map((system) => (
                <div
                  key={system.logical_system_id}
                  className="rounded-md border bg-background p-4"
                >
                  <p className="font-medium">{system.name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {system.paths.join(", ")}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border bg-card p-5 text-card-foreground">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Sprout data-icon="inline-start" />
              Maintenance opportunity
            </div>
            <h2 className="mt-3 text-xl font-semibold">{opportunity.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {opportunity.summary}
            </p>
            <p className="mt-4 text-sm">
              Confidence:{" "}
              <span className="font-medium">
                {Math.round(opportunity.confidence * 100)}%
              </span>
            </p>
          </div>

          <div className="rounded-lg border bg-card p-5 text-card-foreground">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <GitBranch data-icon="inline-start" />
              PR plan
            </div>
            <h2 className="mt-3 text-xl font-semibold">{prPlan.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {prPlan.branch_name}
            </p>
            <p className="mt-4 text-sm">
              Required checks:{" "}
              <span className="font-medium">
                {prPlan.required_checks.join(", ")}
              </span>
            </p>
          </div>
        </section>
      </div>
    </main>
  )
}

export default App
