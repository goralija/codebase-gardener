import {
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"

import App from "@/App.tsx"
import { AppShell } from "@/components/app-shell"
import { AutomationPage } from "@/features/automation"
import { FirstReportPage } from "@/features/first-report"
import { GithubOnboardingPage } from "@/features/github-onboarding"

const rootRoute = createRootRoute({
  component: AppShell,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: App,
})

const githubOnboardingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/onboarding/github",
  component: GithubOnboardingPage,
})

const automationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/automation",
  component: AutomationPage,
})

const reportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/report",
  component: FirstReportPage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  automationRoute,
  githubOnboardingRoute,
  reportRoute,
])

export const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
