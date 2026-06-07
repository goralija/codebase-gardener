import { GitBranch, Gauge, Workflow } from "lucide-react"

export const NAV_ITEMS = [
  { icon: Gauge, label: "Overview", to: "/" },
  { icon: Workflow, label: "Automation", to: "/automation" },
  { icon: GitBranch, label: "GitHub", to: "/onboarding/github" },
]
