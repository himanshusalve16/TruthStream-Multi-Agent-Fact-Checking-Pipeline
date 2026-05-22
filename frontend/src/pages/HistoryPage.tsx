import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { jobs, type JobStatus } from '../api/client'

interface JobsListResponse {
  jobs: JobStatus[]
  total: number
  page: number
  page_size: number
}

const STATUS_COLORS: Record<string, string> = {
  PENDING: 'var(--color-muted)',
  PROCESSING: 'var(--color-accent)',
  COMPLETE: 'var(--color-success)',
  FAILED: 'var(--color-danger)',
  PARTIAL: 'var(--color-warning)',
}

export default function HistoryPage() {
  const [data, setData] = useState<JobsListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    if (!localStorage.getItem('access_token')) {
      navigate('/login')
      return
    }

    jobs
      .list(1, 20)
      .then((res) => setData(res.data as JobsListResponse))
      .catch((err: unknown) => {
        const msg =
          (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
          'Failed to load history'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [navigate])

  return (
    <div>
      <nav className="nav">
        <div className="container nav-inner">
          <Link to="/" className="nav-logo" style={{ textDecoration: 'none' }}>
            ⚡ TruthStream
          </Link>
          <div className="nav-links">
            <Link to="/">New Check</Link>
          </div>
        </div>
      </nav>

      <main className="container" style={{ paddingTop: '40px', paddingBottom: '60px', maxWidth: '800px' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, marginBottom: '8px' }}>History</h1>
        <p style={{ color: 'var(--color-text-dim)', marginBottom: '28px' }}>
          Your past fact-checking jobs
        </p>

        {loading && (
          <p style={{ color: 'var(--color-muted)' }}>
            <span className="spinner" style={{ marginRight: '8px' }} />
            Loading…
          </p>
        )}

        {error && <p style={{ color: 'var(--color-danger)' }}>⚠ {error}</p>}

        {!loading && !error && data?.jobs.length === 0 && (
          <div className="glass-card" style={{ padding: '32px', textAlign: 'center' }}>
            <p style={{ color: 'var(--color-text-dim)', marginBottom: '16px' }}>No jobs yet.</p>
            <Link to="/" className="btn btn-primary" style={{ padding: '10px 20px' }}>
              Run your first check
            </Link>
          </div>
        )}

        {!loading && data && data.jobs.length > 0 && (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {data.jobs.map((job) => (
              <li key={job.job_id}>
                <Link
                  to={`/jobs/${job.job_id}`}
                  className="glass-card"
                  style={{
                    display: 'block',
                    padding: '18px 20px',
                    textDecoration: 'none',
                    color: 'inherit',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p
                        style={{
                          fontWeight: 600,
                          fontSize: '0.95rem',
                          marginBottom: '4px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {job.input_url || 'Pasted text'}
                      </p>
                      <p style={{ fontSize: '0.78rem', color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
                        {job.job_id}
                      </p>
                      <p style={{ fontSize: '0.82rem', color: 'var(--color-text-dim)', marginTop: '6px' }}>
                        {new Date(job.created_at).toLocaleString()}
                      </p>
                    </div>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        padding: '4px 10px',
                        borderRadius: '999px',
                        background: 'rgba(99,120,180,0.15)',
                        color: STATUS_COLORS[job.status] ?? 'var(--color-muted)',
                        flexShrink: 0,
                      }}
                    >
                      {job.status}
                    </span>
                  </div>
                  {job.error_message && (
                    <p style={{ fontSize: '0.82rem', color: 'var(--color-danger)', marginTop: '8px' }}>
                      {job.error_message}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
