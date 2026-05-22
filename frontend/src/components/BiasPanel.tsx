import { useState } from 'react'
import type { BiasData } from '../context/JobContext'

interface Props {
  bias: BiasData
}

const DIRECTION_LABELS: Record<string, string> = {
  left_leaning: 'Left Leaning',
  right_leaning: 'Right Leaning',
  pro_establishment: 'Pro-Establishment',
  anti_establishment: 'Anti-Establishment',
  neutral: 'Neutral',
}

const SEVERITY_COLORS: Record<string, string> = {
  low: 'var(--color-success)',
  medium: 'var(--color-warning)',
  high: 'var(--color-danger)',
}

function getBiasColor(score: number): string {
  if (score < 30) return 'var(--color-success)'
  if (score < 60) return 'var(--color-warning)'
  return 'var(--color-danger)'
}

export default function BiasPanel({ bias }: Props) {
  const [expanded, setExpanded] = useState(false)
  const color = getBiasColor(bias.bias_score)

  return (
    <section id="bias-panel" className="glass-card fade-in" style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 700 }}>🎯 Bias Analysis</h2>
        <div style={{ textAlign: 'right' }}>
          <span style={{ fontSize: '1.8rem', fontWeight: 800, color, fontFamily: 'var(--font-mono)' }}>
            {bias.bias_score}
          </span>
          <span style={{ color: 'var(--color-muted)', fontSize: '0.8rem' }}>/100</span>
        </div>
      </div>

      {/* Bias bar */}
      <div className="confidence-bar-track" style={{ marginBottom: '12px', height: '8px' }}>
        <div
          className="confidence-bar-fill"
          style={{ width: `${bias.bias_score}%`, background: color }}
        />
      </div>

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <span className="badge" style={{ background: 'rgba(255,255,255,.05)', color: 'var(--color-text-dim)' }}>
          {DIRECTION_LABELS[bias.bias_direction] || bias.bias_direction}
        </span>
        {bias.loaded_terms.slice(0, 5).map((t) => (
          <span key={t} className="badge" style={{ background: 'rgba(239,68,68,.1)', color: 'var(--color-danger)', fontFamily: 'var(--font-mono)' }}>
            "{t}"
          </span>
        ))}
      </div>

      <p style={{ fontSize: '0.85rem', color: 'var(--color-text-dim)', lineHeight: 1.6 }}>
        {bias.summary}
      </p>

      {bias.framing_flags.length > 0 && (
        <>
          <button
            className="btn btn-secondary"
            style={{ fontSize: '0.78rem', padding: '5px 12px', marginTop: '12px' }}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? '▲ Hide flags' : `▼ ${bias.framing_flags.length} framing flags`}
          </button>

          {expanded && (
            <div style={{ marginTop: '12px' }} className="fade-in">
              {bias.framing_flags.map((flag, i) => (
                <div
                  key={i}
                  style={{
                    padding: '10px 12px',
                    background: 'rgba(255,255,255,.03)',
                    borderRadius: '8px',
                    marginBottom: '8px',
                    borderLeft: `3px solid ${SEVERITY_COLORS[flag.severity || 'low']}`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>{flag.type}</span>
                    <span style={{
                      fontSize: '0.72rem',
                      color: SEVERITY_COLORS[flag.severity || 'low'],
                      textTransform: 'uppercase',
                      fontWeight: 600,
                    }}>
                      {flag.severity}
                    </span>
                  </div>
                  {flag.description && (
                    <p style={{ fontSize: '0.8rem', color: 'var(--color-text-dim)' }}>{flag.description}</p>
                  )}
                  {flag.examples && flag.examples.length > 0 && (
                    <p style={{ fontSize: '0.76rem', color: 'var(--color-muted)', marginTop: '4px', fontStyle: 'italic' }}>
                      e.g. "{flag.examples.join('", "')}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
