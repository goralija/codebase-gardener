/* ============================================================
   Shared full-page states for the cockpit (loading / auth / empty).
   ============================================================ */
/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from "react"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { Empty } from "@/cockpit/primitives"

export function PageShell({
  eyebrow,
  eyebrowIcon,
  title,
  sub,
  actions,
  wide = true,
  children,
}: {
  eyebrow: string
  eyebrowIcon: string
  title: string
  sub?: string
  actions?: ReactNode
  wide?: boolean
  children: ReactNode
}) {
  return (
    <div className={wide ? "page wide" : "page"}>
      <div className="phead">
        <div>
          <div className="ph-eyebrow">
            <Icon name={eyebrowIcon} size={13} />
            {eyebrow}
          </div>
          <h1>{title}</h1>
          {sub && <div className="ph-sub">{sub}</div>}
        </div>
        {actions && <div className="ph-actions">{actions}</div>}
      </div>
      {children}
    </div>
  )
}

/**
 * Resolves the common org-gating states. Returns a node to render, or null
 * when the caller should render its own content.
 */
export function useGateState({
  authRequired,
  orgLoading,
  dataLoading,
  isError,
  dataError,
  organization,
}: {
  authRequired: boolean
  orgLoading: boolean
  dataLoading?: boolean
  isError: boolean
  dataError?: boolean
  organization: unknown
}): ReactNode | null {
  const navigate = useNavigate()

  if (orgLoading) {
    return (
      <div className="page wide">
        <div className="card">
          <Empty icon="Loader" title="Loading…" />
        </div>
      </div>
    )
  }
  if (authRequired) {
    return (
      <div className="page wide">
        <div className="card">
          <Empty
            action={
              <button
                className="btn primary mt8"
                onClick={() => navigate({ to: "/onboarding/github" })}
                type="button"
              >
                <Icon name="Github" size={15} />
                GitHub setup
              </button>
            }
            icon="CircleOff"
            sub="Your GitHub session is required to load operations data."
            title="GitHub session required"
          />
        </div>
      </div>
    )
  }
  if (isError) {
    return (
      <div className="page wide">
        <div className="card">
          <Empty icon="TriangleAlert" title="Could not load operations data" />
        </div>
      </div>
    )
  }
  if (!organization) {
    return (
      <div className="page wide">
        <div className="card">
          <Empty
            action={
              <button
                className="btn primary mt8"
                onClick={() => navigate({ to: "/onboarding/github" })}
                type="button"
              >
                <Icon name="Github" size={15} />
                Install GitHub App
              </button>
            }
            icon="FolderGit2"
            sub="Install the Gardener GitHub App to connect repositories."
            title="No GitHub installation"
          />
        </div>
      </div>
    )
  }
  if (dataLoading) {
    return (
      <div className="page wide">
        <div className="card">
          <Empty icon="Loader" title="Loading operations data…" />
        </div>
      </div>
    )
  }
  if (dataError) {
    return (
      <div className="page wide">
        <div className="card">
          <Empty
            icon="TriangleAlert"
            title="Could not load repository operations"
          />
        </div>
      </div>
    )
  }
  return null
}
