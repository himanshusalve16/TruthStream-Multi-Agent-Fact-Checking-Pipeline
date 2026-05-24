import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL;

console.log(`[TruthStream Startup] Resolved VITE_API_BASE_URL: "${API_BASE || 'NOT_CONFIGURED'}"`);

const client = axios.create({
  baseURL: API_BASE || '',
  headers: { 'Content-Type': 'application/json' },
})

// Request diagnostic logger & Fail-fast check
client.interceptors.request.use((config) => {
  if (!API_BASE || !API_BASE.startsWith('http')) {
    const errorMsg = "Invalid backend API base URL configured. VITE_API_BASE_URL is missing or invalid.";
    console.error(`[TruthStream API Error] ${errorMsg}`);
    throw new Error(errorMsg);
  }

  let absoluteUrl = config.url || '';
  if (!absoluteUrl.startsWith('http://') && !absoluteUrl.startsWith('https://')) {
    const baseVal = config.baseURL || API_BASE || '';
    const base = baseVal.endsWith('/') ? baseVal.slice(0, -1) : baseVal;
    const path = absoluteUrl.startsWith('/') ? absoluteUrl : `/${absoluteUrl}`;
    absoluteUrl = `${base}${path}`;
  }
  console.log(`[TruthStream API Diagnostic] requesting ${config.method?.toUpperCase()} -> ${absoluteUrl}`);
  return config;
}, (error) => {
  return Promise.reject(error);
})

export default client

// ── API helpers ────────────────────────────────────────────────

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
}

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
