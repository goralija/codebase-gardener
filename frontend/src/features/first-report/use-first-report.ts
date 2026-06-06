import { useQuery } from "@tanstack/react-query"

import { fetchFirstReport } from "./first-report-api"

export function useFirstReport() {
  return useQuery({
    queryKey: ["first-report"],
    queryFn: () => fetchFirstReport(),
    retry: false,
  })
}
