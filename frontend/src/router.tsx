import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router"

import App from "@/App.tsx"
import { GithubOnboardingPage } from "@/features/github-onboarding"

const rootRoute = createRootRoute({
  component: () => <Outlet />,
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

const routeTree = rootRoute.addChildren([indexRoute, githubOnboardingRoute])

export const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
