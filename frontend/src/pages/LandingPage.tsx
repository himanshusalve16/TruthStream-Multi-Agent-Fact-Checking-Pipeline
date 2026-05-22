import { Link, useNavigate } from 'react-router-dom'
import InputForm from '../components/InputForm'

export default function LandingPage() {
  const token = localStorage.getItem('access_token')
  const navigate = useNavigate()

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    navigate('/')
  }

  return (
    <div>
      {/* Nav */}
      <nav className="nav">
        <div className="container nav-inner">
          <span className="nav-logo">⚡ TruthStream</span>
          <div className="nav-links">
            {token ? (
              <>
                <Link to="/history">History</Link>
                <button className="btn btn-secondary" style={{ padding: '7px 18px', fontSize: '0.85rem' }} onClick={handleLogout}>
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link to="/login">Sign in</Link>
                <Link to="/register" className="btn btn-primary" style={{ padding: '7px 18px', fontSize: '0.85rem' }}>
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Hero */}
      <main>
        <div className="container" style={{ paddingTop: '80px', paddingBottom: '48px', textAlign: 'center' }}>
          {/* Glow orbs */}
          <div style={{ position: 'relative', marginBottom: '40px' }}>
            <div style={{
              position: 'absolute',
              top: '-80px',
              left: '50%',
              transform: 'translateX(-50%)',
              width: '400px',
              height: '300px',
              background: 'radial-gradient(ellipse at center, rgba(91,141,239,.18) 0%, transparent 70%)',
              pointerEvents: 'none',
            }} />
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 16px',
              background: 'rgba(91,141,239,.12)',
              border: '1px solid rgba(91,141,239,.3)',
              borderRadius: '999px',
              marginBottom: '24px',
              fontSize: '0.82rem',
              color: 'var(--color-accent)',
              fontWeight: 600,
            }}>
              <span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} />
              Powered by GPT-4o · Live SSE Streaming
            </div>

            <h1 style={{ fontSize: 'clamp(2.2rem, 5vw, 3.8rem)', fontWeight: 800, lineHeight: 1.15, marginBottom: '20px' }}>
              AI-Powered{' '}
              <span className="gradient-text">Fact-Checking</span>
              <br />
              in Real Time
            </h1>

            <p style={{
              fontSize: '1.1rem',
              color: 'var(--color-text-dim)',
              maxWidth: '560px',
              margin: '0 auto 40px',
              lineHeight: 1.7,
            }}>
              Submit any article URL. Our multi-agent system extracts claims, finds corroborating
              sources, scores media bias, and delivers a verdict — streamed live as it happens.
            </p>
          </div>

          {/* Form */}
          <div style={{ maxWidth: '620px', margin: '0 auto 64px' }}>
            <InputForm />
          </div>

          {/* Features */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
            maxWidth: '860px',
            margin: '0 auto',
          }}>
            {[
              { icon: '🔍', title: 'Claim Extraction', desc: 'Identifies checkable factual assertions from any article' },
              { icon: '🌐', title: 'Source Finder', desc: 'Searches trusted sources to corroborate or refute each claim' },
              { icon: '🎯', title: 'Bias Scoring', desc: 'Detects loaded language and framing bias 0–100' },
              { icon: '⚖️', title: 'Judge Agent', desc: 'Synthesizes all evidence into a confidence-weighted verdict' },
            ].map((f) => (
              <div key={f.title} className="glass-card" style={{ padding: '20px', textAlign: 'left' }}>
                <span style={{ fontSize: '1.8rem', display: 'block', marginBottom: '10px' }}>{f.icon}</span>
                <h3 style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: '6px' }}>{f.title}</h3>
                <p style={{ fontSize: '0.82rem', color: 'var(--color-text-dim)', lineHeight: 1.5 }}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
