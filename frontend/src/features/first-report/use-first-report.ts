import { useQuery } from "@tanstack/react-query"

import { fetchFirstReport } from "./first-report-api"

export function useFirstReport() {
  const searchParams = new URLSearchParams(window.location.search)
  const repositoryId = searchParams.get("repositoryId")
  const baseline = searchParams.get("baseline") === "1"

  return useQuery({
    queryKey: ["first-report", repositoryId, baseline],
    queryFn: () => fetchFirstReport({ baseline, repositoryId }),
    retry: false,
  })
}
