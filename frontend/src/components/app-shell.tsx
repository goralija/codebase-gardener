import { Link, Outlet } from "@tanstack/react-router"
import { Bot, FileText, GitBranch, Gauge } from "lucide-react"

const NAV_ITEMS = [
  { icon: Gauge, label: "Overview", to: "/" },
  { icon: Bot, label: "Automation", to: "/automation" },
  { icon: GitBranch, label: "GitHub", to: "/onboarding/github" },
  { icon: FileText, label: "Report", to: "/report" },
]

export function AppShell() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-5 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <Link
            className="flex items-center gap-2 text-sm font-semibold"
            to="/"
          >
            <span className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Bot className="size-4" />
            </span>
            Codebase Gardener
          </Link>
          <nav aria-label="Primary" className="flex flex-wrap items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              return (
                <Link
                  activeProps={{
                    className:
                      "bg-primary/10 text-primary hover:bg-primary/10",
                  }}
                  className="inline-flex h-8 items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
                  inactiveProps={{
                    className: "text-muted-foreground",
                  }}
                  key={item.to}
                  to={item.to}
                >
                  <Icon className="size-4" />
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
