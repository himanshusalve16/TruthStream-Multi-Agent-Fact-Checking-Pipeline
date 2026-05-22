import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { jobs } from '../api/client'
import { useJobContext } from '../context/JobContext'

export default function InputForm() {
  const [tab, setTab] = useState<'url' | 'text'>('url')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const { dispatch } = useJobContext()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    if (!localStorage.getItem('access_token')) {
      navigate('/login')
      return
    }

    try {
      dispatch({ type: 'RESET' })
      const res = await jobs.submit({
        input_type: tab,
        url: tab === 'url' ? url : undefined,
        text: tab === 'text' ? text : undefined,
      })
      const jobId = res.data.job_id
      dispatch({ type: 'SET_JOB_ID', jobId })
      navigate(`/jobs/${jobId}`)
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || 'Submission failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form id="fact-check-form" onSubmit={handleSubmit} className="glass-card" style={{ padding: '32px' }}>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
        {(['url', 'text'] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={`btn ${tab === t ? 'btn-primary' : 'btn-secondary'}`}
            style={{ flex: 1, justifyContent: 'center' }}
            onClick={() => setTab(t)}
          >
            {t === 'url' ? '🔗 URL' : '📝 Paste Text'}
          </button>
        ))}
      </div>

      {tab === 'url' ? (
        <input
          id="url-input"
          type="url"
          className="input"
          placeholder="https://example.com/article"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          autoFocus
        />
      ) : (
        <textarea
          id="text-input"
          className="input"
          placeholder="Paste the article text here..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
          rows={6}
        />
      )}

      {error && (
        <p style={{ color: 'var(--color-danger)', marginTop: '12px', fontSize: '0.88rem' }}>
          ⚠ {error}
        </p>
      )}

      <button
        id="submit-btn"
        type="submit"
        className="btn btn-primary"
        disabled={loading || (tab === 'url' ? !url : !text)}
        style={{ width: '100%', marginTop: '20px', padding: '14px', fontSize: '1rem', justifyContent: 'center' }}
      >
        {loading ? (
          <><span className="spinner" /> Analyzing…</>
        ) : (
          '🔍 Fact-Check Now'
        )}
      </button>
    </form>
  )
}
