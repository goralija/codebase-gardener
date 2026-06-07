import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ArchitectureConstitutionPanels } from "./architecture-constitution-panels"

describe("ArchitectureConstitutionPanels", () => {
  it("renders protected modules with repeated names without React key warnings", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})

    try {
      render(
        <ArchitectureConstitutionPanels
          architecture={{
            boundaryRuleCount: 0,
            dependencyCycleCount: 0,
            hasViolations: false,
            violationCount: 0,
          }}
          constitution={{
            allowedFixes: {
              advisory: [],
              assisted: [],
              autonomous: [],
            },
            completeness: "100%",
            hasOpenQuestions: false,
            ignoredPaths: [],
            neverTouch: [],
            openQuestionCount: 0,
            openQuestions: [],
            protectedModules: [
              {
                name: "because it appears security-sensitive or business-critical",
                paths: ["backend/app/**"],
                reason: "it appears security-sensitive or business-critical.",
              },
              {
                name: "because it appears security-sensitive or business-critical",
                paths: ["frontend/src/**"],
                reason: "it appears security-sensitive or business-critical.",
              },
            ],
          }}
        />
      )

      expect(screen.getByText("backend/app/**")).toBeInTheDocument()
      expect(screen.getByText("frontend/src/**")).toBeInTheDocument()
      expect(errorSpy).not.toHaveBeenCalled()
    } finally {
      errorSpy.mockRestore()
    }
  })
})
