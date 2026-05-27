import axios from 'axios'

// ── Base URL resolution ────────────────────────────────────────────────────
// When VITE_API_BASE_URL is set (e.g. production with a separate backend
// host) use it. When it is empty or absent the app is served from the same
// origin as the backend (nginx proxy, Vercel rewrites, etc.) and relative
// paths work fine.
export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

if (API_BASE && !API_BASE.startsWith('http')) {
  console.warn(
    `[TruthStream] VITE_API_BASE_URL looks wrong: "${API_BASE}". ` +
    `It should start with http:// or https://. Falling back to relative paths.`
  )
}

const client = axios.create({
  // Empty string → relative URLs, which works when the frontend and backend
  // share the same origin. Non-empty → absolute URLs for cross-origin setups.
  baseURL: API_BASE || undefined,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor ────────────────────────────────────────────────────
// Logs every outgoing request for diagnostics. No longer throws on missing
// VITE_API_BASE_URL — relative paths are a valid production configuration
// when served through nginx/Vercel reverse proxies.
client.interceptors.request.use(
  (config) => {
    const base = config.baseURL || ''
    const path = config.url || ''
    const resolvedUrl =
      path.startsWith('http') ? path : `${base}${path.startsWith('/') ? path : `/${path}`}`
    console.debug(`[API] ${config.method?.toUpperCase()} → ${resolvedUrl}`)
    return config
  },
  (error) => Promise.reject(error)
)

export default client

// ── API helpers ────────────────────────────────────────────────────────────

export const jobs = {
  submit: (payload: { input_type: 'url' | 'text'; url?: string; text?: string }) =>
    client.post<{ job_id: string; status: string; created_at: string }>('/api/jobs', payload),

  get: (jobId: string) =>
    client.get<JobStatus>(`/api/jobs/${jobId}`),

  list: (page = 1, size = 20) =>
    client.get(`/api/jobs?page=${page}&size=${size}`),

  getVerdict: (jobId: string) =>
    client.get<FullVerdictResponse>(`/api/jobs/${jobId}/verdict`),

  getSources: (jobId: string) =>
    client.get<{ job_id: string; sources_by_claim: Record<string, SourceDto[]> }>(
      `/api/jobs/${jobId}/sources`
    ),

  cancel: (jobId: string) =>
    client.post<JobStatus>(`/api/jobs/${jobId}/cancel`),

  /**
   * Lightweight gateway health check.
   *
   * Calls GET /api/health which returns immediately from the gateway
   * without probing the AI service, Redis, DB, or Eureka.
   *
   * Response: { status: "ok" | "degraded" }
   *
   * Uses a dedicated axios instance (no shared interceptors that could
   * throw on missing VITE_API_BASE_URL) and a short timeout so the
   * status badge updates quickly rather than hanging.
   */
  checkHealth: () =>
    client.get<{ status: 'ok' | 'degraded' }>(
      '/api/health',
      { timeout: 8000 }   // 8 s — covers Render free-tier wake-up latency
    ),
}

// ── Type declarations ──────────────────────────────────────────────────────

export interface SourceDto {
  source_id: string
  url: string
  title?: string
  domain?: string
  snippet?: string
  stance?: string
  quality_score?: number
  fetch_status?: string
}

export interface FullVerdictResponse {
  job_id: string
  overall_verdict: string
  overall_confidence: number
  overall_summary: string
  bias: {
    bias_score: number
    bias_direction: string
    framing_flags: unknown[]
    loaded_terms: string[]
    summary: string
  } | null
  article?: { id: string; url: string; truncated: boolean } | null
  claim_verdicts: Array<{
    claim_id: string
    text: string
    claim_type?: string
    checkability?: string
    verdict: string
    confidence: number
    reasoning: string
    sources: SourceDto[]
  }>
}

export interface JobStatus {
  job_id: string
  status: 'PENDING' | 'PROCESSING' | 'COMPLETE' | 'FAILED' | 'PARTIAL'
  created_at: string
  updated_at: string
  input_url?: string
  error_message?: string
}
