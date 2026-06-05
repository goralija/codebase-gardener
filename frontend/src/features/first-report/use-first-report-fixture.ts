import { useQuery } from "@tanstack/react-query"

import firstReportFixture from "../../../../fixtures/contracts/first_report_fixture.json"
import type { FirstReportFixture } from "./first-report-view-model"

export { firstReportFixture }

export function useFirstReportFixture() {
  return useQuery<FirstReportFixture>({
    queryKey: ["first-report-fixture"],
    queryFn: () => Promise.resolve(firstReportFixture),
  })
}
