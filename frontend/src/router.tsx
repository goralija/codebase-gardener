import {
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router"

import { CockpitShell } from "@/cockpit/shell"
import { AutomationPage } from "@/cockpit/pages/automation"
import {
  OpportunitiesPage,
  PullsPage,
  SessionsPage,
} from "@/cockpit/pages/cross-org"
import { ConstitutionPage, EntropyPage } from "@/cockpit/pages/entropy"
import { GithubPage } from "@/cockpit/pages/github"
import { OverviewPage } from "@/cockpit/pages/overview"
import { RepoDetailPage } from "@/cockpit/pages/repo-detail"
import { RepositoriesPage } from "@/cockpit/pages/repositories"

const rootRoute = createRootRoute({
  component: CockpitShell,
})

const indexRoute = createRoute({
  component: OverviewPage,
  getParentRoute: () => rootRoute,
  path: "/",
})

const repositoriesRoute = createRoute({
  component: RepositoriesPage,
  getParentRoute: () => rootRoute,
  path: "/repos",
})

type RepoSearch = { tab?: string }

const repoDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/repo/$repoId",
  validateSearch: (search: Record<string, unknown>): RepoSearch => ({
    tab: typeof search.tab === "string" ? search.tab : undefined,
  }),
  component: function RepoDetailRouteComponent() {
    const { repoId } = repoDetailRoute.useParams()
    const { tab } = repoDetailRoute.useSearch()
    return <RepoDetailPage repoId={repoId} tab={tab} />
  },
})

const entropyRoute = createRoute({
  component: EntropyPage,
  getParentRoute: () => rootRoute,
  path: "/entropy",
})

const constitutionRoute = createRoute({
  component: ConstitutionPage,
  getParentRoute: () => rootRoute,
  path: "/constitution",
})

const opportunitiesRoute = createRoute({
  component: OpportunitiesPage,
  getParentRoute: () => rootRoute,
  path: "/opportunities",
})

const sessionsRoute = createRoute({
  component: SessionsPage,
  getParentRoute: () => rootRoute,
  path: "/sessions",
})

const pullsRoute = createRoute({
  component: PullsPage,
  getParentRoute: () => rootRoute,
  path: "/pulls",
})

const automationRoute = createRoute({
  component: AutomationPage,
  getParentRoute: () => rootRoute,
  path: "/automation",
})

const githubOnboardingRoute = createRoute({
  component: GithubPage,
  getParentRoute: () => rootRoute,
  path: "/onboarding/github",
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  repositoriesRoute,
  repoDetailRoute,
  entropyRoute,
  constitutionRoute,
  opportunitiesRoute,
  sessionsRoute,
  pullsRoute,
  automationRoute,
  githubOnboardingRoute,
])

export const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
