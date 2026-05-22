import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { auth } from '../api/client'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await auth.login(email, password)
      localStorage.setItem('access_token', res.data.access_token)
      navigate('/')
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        'Login failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <nav className="nav">
        <div className="container nav-inner">
          <Link to="/" className="nav-logo" style={{ textDecoration: 'none' }}>
            ⚡ TruthStream
          </Link>
        </div>
      </nav>

      <main className="container" style={{ maxWidth: '420px', paddingTop: '80px', paddingBottom: '60px' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, marginBottom: '8px' }}>Sign in</h1>
        <p style={{ color: 'var(--color-text-dim)', marginBottom: '28px', fontSize: '0.95rem' }}>
          Access your fact-checking history and submit new jobs.
        </p>

        <form onSubmit={handleSubmit} className="glass-card" style={{ padding: '28px' }}>
          <label style={{ display: 'block', marginBottom: '16px' }}>
            <span style={{ fontSize: '0.82rem', color: 'var(--color-muted)', display: 'block', marginBottom: '6px' }}>
              Email
            </span>
            <input
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </label>

          <label style={{ display: 'block', marginBottom: '20px' }}>
            <span style={{ fontSize: '0.82rem', color: 'var(--color-muted)', display: 'block', marginBottom: '6px' }}>
              Password
            </span>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>

          {error && (
            <p style={{ color: 'var(--color-danger)', fontSize: '0.88rem', marginBottom: '16px' }}>⚠ {error}</p>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
          >
            {loading ? <><span className="spinner" /> Signing in…</> : 'Sign in'}
          </button>
        </form>

        <p style={{ textAlign: 'center', marginTop: '20px', fontSize: '0.9rem', color: 'var(--color-text-dim)' }}>
          No account? <Link to="/register">Create one</Link>
        </p>
      </main>
    </div>
  )
}
