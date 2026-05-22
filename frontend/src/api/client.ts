import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client

// ── API helpers ────────────────────────────────────────────────

export const auth = {
  register: (email: string, password: string) =>
    client.post('/api/auth/register', { email, password }),
  login: (email: string, password: string) =>
    client.post<{ access_token: string; token_type: string; expires_in: number }>(
      '/api/auth/login', { email, password }
    ),
}

export const jobs = {
  submit: (payload: { input_type: 'url' | 'text'; url?: string; text?: string }) =>
    client.post<{ job_id: string; status: string; created_at: string }>('/api/jobs', payload),
  get: (jobId: string) =>
    client.get<JobStatus>(`/api/jobs/${jobId}`),
  list: (page = 1, size = 20) =>
    client.get(`/api/jobs?page=${page}&size=${size}`),
  getVerdict: (jobId: string) =>
    client.get(`/api/jobs/${jobId}/verdict`),
}

export interface JobStatus {
  job_id: string
  status: 'PENDING' | 'PROCESSING' | 'COMPLETE' | 'FAILED' | 'PARTIAL'
  created_at: string
  updated_at: string
  input_url?: string
  error_message?: string
}
