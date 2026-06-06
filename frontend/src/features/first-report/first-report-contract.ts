import * as v from "valibot"

const stringArraySchema = v.array(v.string())
const unknownArraySchema = v.array(v.unknown())
const ratioSchema = v.pipe(v.number(), v.minValue(0), v.maxValue(1))
const schemaVersionSchema = v.literal("1.0")

const evidenceReferenceSchema = v.object({
  source_type: v.string(),
  path: v.string(),
  section: v.string(),
  line_start: v.number(),
  line_end: v.number(),
  summary: v.string(),
})

const protectedModuleSchema = v.object({
  name: v.string(),
  paths: stringArraySchema,
  reason: v.string(),
})

const neverTouchSchema = v.object({
  path: v.string(),
  reason: v.string(),
})

const openQuestionSchema = v.object({
  question_id: v.string(),
  severity: v.string(),
  question: v.string(),
  evidence: v.array(evidenceReferenceSchema),
})

const repositoryConstitutionSchema = v.object({
  schema_version: schemaVersionSchema,
  repository_id: v.string(),
  commit_sha: v.string(),
  completeness_score: ratioSchema,
  protected_modules: v.array(protectedModuleSchema),
  never_touch: v.array(neverTouchSchema),
  allowed_fixes: v.object({
    autonomous: stringArraySchema,
    assisted: stringArraySchema,
    advisory: stringArraySchema,
  }),
  architecture_boundaries: unknownArraySchema,
  ignored_paths: stringArraySchema,
  open_questions: v.array(openQuestionSchema),
})

const logicalSystemSchema = v.object({
  logical_system_id: v.string(),
  name: v.string(),
  paths: stringArraySchema,
})

const analysisSnapshotSchema = v.object({
  schema_version: schemaVersionSchema,
  analysis_snapshot_id: v.string(),
  repository_id: v.string(),
  commit_sha: v.string(),
  created_at: v.string(),
  logical_systems: v.array(logicalSystemSchema),
  signals: v.object({
    dependency_cycles: unknownArraySchema,
    hotspots: unknownArraySchema,
    dead_code_candidates: unknownArraySchema,
    ownership_risks: unknownArraySchema,
    test_gaps: unknownArraySchema,
    dependency_risks: unknownArraySchema,
    ci_failures: unknownArraySchema,
  }),
  constitution_id: v.string(),
})

const entropyContributorSchema = v.object({
  kind: v.string(),
  summary: v.string(),
  impact: v.number(),
  evidence: v.array(evidenceReferenceSchema),
})

const entropyReportSchema = v.object({
  schema_version: schemaVersionSchema,
  entropy_report_id: v.string(),
  repository_id: v.string(),
  analysis_snapshot_id: v.string(),
  commit_sha: v.string(),
  score: v.object({
    overall: v.number(),
    classification: v.string(),
    components: v.object({
      architecture: v.number(),
      maintainability: v.number(),
      knowledge: v.number(),
      testing: v.number(),
      dependency: v.number(),
      operational: v.number(),
    }),
  }),
  scopes: v.array(
    v.object({
      scope_type: v.string(),
      scope_id: v.string(),
      name: v.string(),
      overall: v.number(),
      classification: v.string(),
    })
  ),
  top_contributors: v.array(entropyContributorSchema),
  forecast: v.object({
    horizon_days: v.number(),
    predicted_overall: v.number(),
    confidence: ratioSchema,
    summary: v.string(),
  }),
})

const gardeningSessionResultSchema = v.object({
  schema_version: schemaVersionSchema,
  gardening_session_id: v.string(),
  repository_id: v.string(),
  trigger: v.object({
    type: v.string(),
    actor: v.string(),
  }),
  status: v.string(),
  started_at: v.string(),
  finished_at: v.string(),
  phase_results: v.array(
    v.object({
      phase: v.string(),
      status: v.string(),
      summary: v.string(),
    })
  ),
  opportunities_selected: stringArraySchema,
  opportunities_deferred: v.array(
    v.object({
      maintenance_opportunity_id: v.string(),
      reason: v.string(),
    })
  ),
  maintenance_pr_plans: stringArraySchema,
  errors: unknownArraySchema,
})

const maintenanceOpportunitySchema = v.object({
  schema_version: schemaVersionSchema,
  maintenance_opportunity_id: v.string(),
  repository_id: v.string(),
  analysis_snapshot_id: v.string(),
  category: v.string(),
  risk_tier: v.string(),
  confidence: ratioSchema,
  title: v.string(),
  summary: v.string(),
  affected_paths: stringArraySchema,
  blocked_by: stringArraySchema,
  expected_entropy_delta: v.number(),
  required_checks: stringArraySchema,
  evidence: v.array(evidenceReferenceSchema),
})

const maintenancePrPlanSchema = v.object({
  schema_version: schemaVersionSchema,
  maintenance_pr_plan_id: v.string(),
  repository_id: v.string(),
  gardening_session_id: v.string(),
  maintenance_opportunity_ids: stringArraySchema,
  branch_name: v.string(),
  title: v.string(),
  risk_tier: v.string(),
  confidence: ratioSchema,
  changed_paths: stringArraySchema,
  pr_body_sections: v.object({
    goal: v.string(),
    evidence: v.string(),
    entropy_impact: v.string(),
    verification: v.string(),
  }),
  required_checks: stringArraySchema,
  blocked: v.boolean(),
  block_reason: v.nullable(v.string()),
})

export const firstReportSchema = v.object({
  repository_constitution: repositoryConstitutionSchema,
  analysis_snapshot: analysisSnapshotSchema,
  entropy_report: entropyReportSchema,
  gardening_session_result: gardeningSessionResultSchema,
  maintenance_opportunities: v.array(maintenanceOpportunitySchema),
  maintenance_pr_plans: v.array(maintenancePrPlanSchema),
})

export function parseFirstReport(input: unknown) {
  return v.parse(firstReportSchema, input)
}

export type FirstReport = v.InferOutput<typeof firstReportSchema>
