/* ============================================================
   Cross-repo Entropy + Constitution pages.
   ============================================================ */
import { useMemo } from "react"
import { useNavigate } from "@tanstack/react-router"

import { Icon } from "@/cockpit/icon"
import { entColor } from "@/cockpit/format"
import { useCockpit } from "@/cockpit/data"
import {
  COMPONENTS,
  constitutionFromReport,
  entropyFromReport,
  type EntropyComponentKey,
} from "@/cockpit/model"
import {
  Badge,
  ComponentBars,
  EntropyBadge,
  EntropyGauge,
  Empty,
  RepoName,
  Stat,
} from "@/cockpit/primitives"
import { PageShell, useGateState } from "@/cockpit/pages/states"

function gotoRepo(
  navigate: ReturnType<typeof useNavigate>,
  repoId: string,
  tab: string
) {
  navigate({ params: { repoId }, search: { tab }, to: "/repo/$repoId" } as never)
}

export function EntropyPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const navigate = useNavigate()

  const scored = useMemo(() => {
    return cockpit.repositories
      .map((repo) => {
        const report = cockpit.reportsMap.get(repo.id)
        if (!report) return null
        return { entropy: entropyFromReport(report), loc: repo.complexity.loc, repo }
      })
      .filter((x): x is NonNullable<typeof x> => x !== null)
      .sort((a, b) => b.entropy.overall - a.entropy.overall)
  }, [cockpit.repositories, cockpit.reportsMap])

  if (gate) return gate

  const avg =
    scored.length > 0
      ? Math.round(
          scored.reduce((a, s) => a + s.entropy.overall, 0) / scored.length
        )
      : null

  const totalLoc = scored.reduce((a, s) => a + (s.loc ?? 1), 0) || 1
  const agg = {} as Record<EntropyComponentKey, number>
  COMPONENTS.forEach((c) => {
    agg[c.key] = Math.round(
      scored.reduce(
        (a, s) => a + s.entropy.components[c.key] * (s.loc ?? 1),
        0
      ) / totalLoc
    )
  })

  const bands = [
    { color: "var(--e-high)", key: "high", label: "High", n: scored.filter((s) => s.entropy.overall >= 70).length, range: "70–100" },
    { color: "var(--e-elev)", key: "elev", label: "Elevated", n: scored.filter((s) => s.entropy.overall >= 50 && s.entropy.overall < 70).length, range: "50–69" },
    { color: "var(--e-mod)", key: "mod", label: "Moderate", n: scored.filter((s) => s.entropy.overall >= 30 && s.entropy.overall < 50).length, range: "30–49" },
    { color: "var(--e-low)", key: "low", label: "Low", n: scored.filter((s) => s.entropy.overall < 30).length, range: "0–29" },
  ]

  return (
    <PageShell
      eyebrow="Analysis"
      eyebrowIcon="Gauge"
      sub={`Codebase maintenance risk across ${scored.length} scanned repositories`}
      title="Entropy report"
    >
      {scored.length === 0 ? (
        <div className="card">
          <Empty
            icon="Gauge"
            sub="Run first scans to compute entropy scores. Reports appear here once analyses are stored."
            title="No entropy scores yet"
          />
        </div>
      ) : (
        <>
          <div
            style={{
              alignItems: "stretch",
              display: "grid",
              gap: 16,
              gridTemplateColumns: "auto 1fr 1.1fr",
              marginBottom: 16,
            }}
          >
            <div
              className="card pad"
              style={{ display: "grid", minWidth: 240, placeItems: "center" }}
            >
              <EntropyGauge score={avg} size={170} />
              <div className="tiny faint mono mt8">org average</div>
            </div>
            <div className="card pad">
              <div className="sect-title mb16">Distribution</div>
              <div style={{ display: "grid", gap: 12 }}>
                {bands.map((b) => (
                  <div className="row gap10" key={b.key}>
                    <span
                      style={{
                        background: b.color,
                        borderRadius: 2,
                        flex: "none",
                        height: 9,
                        width: 9,
                      }}
                    />
                    <span className="sm" style={{ width: 76 }}>
                      {b.label}
                    </span>
                    <span className="tiny faint mono" style={{ width: 54 }}>
                      {b.range}
                    </span>
                    <div className="meter grow">
                      <span
                        style={{
                          background: b.color,
                          width: (b.n / scored.length) * 100 + "%",
                        }}
                      />
                    </div>
                    <span className="mono b6" style={{ textAlign: "right", width: 20 }}>
                      {b.n}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card pad">
              <div className="sect-title mb12">Org component pressure</div>
              <ComponentBars components={agg} />
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <Icon color="var(--fg-3)" name="Gauge" size={15} />
              <h3>Entropy by repository</h3>
              <span className="ch-sub">ranked high → low</span>
            </div>
            <div
              className="tbl-wrap scroll"
              style={{ border: "none", borderRadius: 0 }}
            >
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Repository</th>
                    <th className="num">Entropy</th>
                    <th>Class</th>
                    {COMPONENTS.map((c) => (
                      <th className="num" key={c.key} title={c.label}>
                        {c.label.slice(0, 4)}
                      </th>
                    ))}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {scored.map(({ entropy, repo }) => (
                    <tr
                      className="click"
                      key={repo.id}
                      onClick={() => gotoRepo(navigate, repo.id, "entropy")}
                    >
                      <td>
                        <RepoName
                          color={entColor(entropy.overall)}
                          name={repo.name}
                        />
                      </td>
                      <td className="num">
                        <span
                          style={{
                            color: entColor(entropy.overall),
                            fontSize: 14,
                            fontWeight: 600,
                          }}
                        >
                          {entropy.overall}
                        </span>
                      </td>
                      <td>
                        <EntropyBadge score={entropy.overall} />
                      </td>
                      {COMPONENTS.map((c) => {
                        const v = entropy.components[c.key]
                        return (
                          <td className="num" key={c.key}>
                            <span
                              className="mono tiny"
                              style={{ color: entColor(v) }}
                            >
                              {v}
                            </span>
                          </td>
                        )
                      })}
                      <td>
                        <Icon
                          color="var(--fg-4)"
                          name="ChevronRight"
                          size={15}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </PageShell>
  )
}

export function ConstitutionPage() {
  const cockpit = useCockpit()
  const gate = useGateState(cockpit)
  const navigate = useNavigate()

  const rows = useMemo(() => {
    return cockpit.repositories.map((repo) => {
      const report = cockpit.reportsMap.get(repo.id)
      return {
        constitution: report ? constitutionFromReport(report) : null,
        repo,
      }
    })
  }, [cockpit.repositories, cockpit.reportsMap])

  if (gate) return gate

  const withConstitution = rows.filter((r) => r.constitution?.present)
  const missing = rows.filter((r) => r.constitution && !r.constitution.present)
  const avgCov =
    withConstitution.length > 0
      ? Math.round(
          withConstitution.reduce(
            (a, r) => a + (r.constitution?.coverage ?? 0),
            0
          ) / withConstitution.length
        )
      : 0
  const totalProtected = rows.reduce(
    (a, r) => a + (r.constitution?.protected.length ?? 0),
    0
  )
  const totalQuestions = rows.reduce(
    (a, r) => a + (r.constitution?.questions.length ?? 0),
    0
  )

  return (
    <PageShell
      eyebrow="Analysis"
      eyebrowIcon="ScrollText"
      sub="Machine-readable rules, protected modules, and source-truth coverage across repositories"
      title="Repository constitution"
    >
      <div
        className="statrow mb20"
        style={{ gridTemplateColumns: "repeat(4,1fr)" }}
      >
        <Stat
          accent={missing.length ? "var(--amber)" : "var(--green)"}
          foot={
            missing.length ? (
              <span style={{ color: "var(--amber)" }}>
                <Icon name="TriangleAlert" size={11} />
                {missing.length} missing
              </span>
            ) : (
              <span className="muted">all present</span>
            )
          }
          icon="FileCheck2"
          label="With GARDENER.md"
          unit={`/ ${rows.length}`}
          value={withConstitution.length}
        />
        <Stat
          icon="ScrollText"
          label="Avg source-truth coverage"
          tone={avgCov >= 80 ? "var(--green)" : "var(--amber)"}
          unit="%"
          value={avgCov}
        />
        <Stat
          foot={<span className="muted">across org</span>}
          icon="Lock"
          label="Protected modules"
          value={totalProtected}
        />
        <Stat
          accent={totalQuestions ? "var(--amber)" : undefined}
          foot={<span className="muted">need maintainer input</span>}
          icon="MessageCircleQuestion"
          label="Open questions"
          value={totalQuestions}
        />
      </div>

      <div className="card">
        <div className="card-h">
          <Icon color="var(--fg-3)" name="ScrollText" size={15} />
          <h3>Constitution coverage</h3>
        </div>
        <div className="tbl-wrap" style={{ border: "none", borderRadius: 0 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Repository</th>
                <th>GARDENER.md</th>
                <th>Coverage</th>
                <th className="num">Protected</th>
                <th className="num">Allowed fixes</th>
                <th>Questions</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map(({ constitution, repo }) => (
                <tr
                  className="click"
                  key={repo.id}
                  onClick={() => gotoRepo(navigate, repo.id, "constitution")}
                >
                  <td>
                    <RepoName name={repo.name} />
                  </td>
                  <td>
                    {constitution?.present ? (
                      <Badge icon="FileCheck2" tone="green">
                        present
                      </Badge>
                    ) : (
                      <Badge icon="FileWarning" tone="blue">
                        {constitution ? "missing" : "no scan"}
                      </Badge>
                    )}
                  </td>
                  <td style={{ width: 200 }}>
                    {constitution?.present ? (
                      <div className="row gap10">
                        <div className="meter grow">
                          <span
                            style={{
                              background:
                                constitution.coverage >= 80
                                  ? "var(--green)"
                                  : "var(--amber)",
                              width: constitution.coverage + "%",
                            }}
                          />
                        </div>
                        <span
                          className="mono tiny"
                          style={{
                            color:
                              constitution.coverage >= 80
                                ? "var(--green)"
                                : "var(--amber)",
                            width: 32,
                          }}
                        >
                          {constitution.coverage}%
                        </span>
                      </div>
                    ) : (
                      <span className="faint sm">
                        {constitution ? "inferred mode" : "—"}
                      </span>
                    )}
                  </td>
                  <td className="num">
                    {constitution?.protected.length ? (
                      <span
                        className="row gap6"
                        style={{ justifyContent: "flex-end" }}
                      >
                        <Icon color="var(--amber)" name="Lock" size={11} />
                        {constitution.protected.length}
                      </span>
                    ) : (
                      <span className="faint">0</span>
                    )}
                  </td>
                  <td className="num">
                    {constitution?.allowed.length || (
                      <span className="faint">0</span>
                    )}
                  </td>
                  <td>
                    {constitution && constitution.questions.length > 0 ? (
                      <Badge tone="amber">
                        {constitution.questions.length} open
                      </Badge>
                    ) : constitution?.present ? (
                      <Badge icon="Check" tone="green">
                        clear
                      </Badge>
                    ) : (
                      <span className="faint">—</span>
                    )}
                  </td>
                  <td>
                    <Icon color="var(--fg-4)" name="ChevronRight" size={15} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </PageShell>
  )
}
