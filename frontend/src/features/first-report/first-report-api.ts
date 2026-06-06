import { parseFirstReport, type FirstReport } from "./first-report-contract"

const DEFAULT_API_BASE_URL = "/api/v1"

type FetchFirstReportOptions = {
  apiBaseUrl?: string
  fetcher?: typeof fetch
}

export class FirstReportNotReadyError extends Error {
  constructor() {
    super("The first report is not ready yet.")
    this.name = "FirstReportNotReadyError"
  }
}

export class FirstReportRequestError extends Error {
  readonly status: number

  constructor(status: number, statusText: string) {
    super(`First report request failed with ${status} ${statusText}.`)
    this.name = "FirstReportRequestError"
    this.status = status
  }
}

export class FirstReportContractError extends Error {
  constructor() {
    super("First report response does not match the shared contract.")
    this.name = "FirstReportContractError"
  }
}

export function getFirstReportApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL
}

export function buildApiUrl(
  path: string,
  apiBaseUrl = getFirstReportApiBaseUrl()
) {
  const normalizedBase = apiBaseUrl.replace(/\/+$/, "")
  const normalizedPath = path.startsWith("/") ? path : `/${path}`

  return `${normalizedBase}${normalizedPath}`
}

export async function fetchFirstReport({
  apiBaseUrl,
  fetcher = fetch,
}: FetchFirstReportOptions = {}): Promise<FirstReport> {
  const response = await fetcher(buildApiUrl("/reports/first/", apiBaseUrl), {
    headers: {
      Accept: "application/json",
    },
  })

  if (response.status === 404) {
    throw new FirstReportNotReadyError()
  }

  if (!response.ok) {
    throw new FirstReportRequestError(response.status, response.statusText)
  }

  let payload: unknown

  try {
    payload = await response.json()
  } catch {
    throw new FirstReportContractError()
  }

  try {
    return parseFirstReport(payload)
  } catch {
    throw new FirstReportContractError()
  }
}
