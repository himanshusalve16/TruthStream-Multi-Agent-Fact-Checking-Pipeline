import { useState } from 'react'
import { Claim, ClaimVerdict, Source } from '../context/JobContext'
import SourceCard from './SourceCard'

const VERDICT_COLORS: Record<string, string> = {
  SUPPORTED: 'var(--color-success)',
  REFUTED: 'var(--color-danger)',
  CONTESTED: 'var(--color-warning)',
  UNVERIFIABLE: 'var(--color-muted)',
}

const VERDICT_ICONS: Record<string, string> = {
  SUPPORTED: '✅',
  REFUTED: '❌',
  CONTESTED: '⚖️',
  UNVERIFIABLE: '❓',
}

interface Props {
  claim: Claim
  verdict?: ClaimVerdict
  sources: Source[]
}

export default function ClaimCard({ claim, verdict, sources }: Props) {
  const [expanded, setExpanded] = useState(false)
  const hasVerdict = !!verdict
  const verdictColor = hasVerdict ? VERDICT_COLORS[verdict!.verdict] : 'var(--color-muted)'
  const confidence = verdict?.confidence ?? 0
  const pct = Math.round(confidence * 100)

  return (
    <div
      id={`claim-${claim.claim_id}`}
      className="glass-card fade-in"
      style={{
        padding: '20px',
        marginBottom: '16px',
        border: hasVerdict
          ? `1px solid ${verdictColor}33`
          : '1px solid var(--color-border)',
        transition: 'border-color 0.4s',
      }}
    >
      {/* Claim header */}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        <span style={{ fontSize: '1.2rem', flexShrink: 0, marginTop: '1px' }}>
          {hasVerdict ? VERDICT_ICONS[verdict!.verdict] : <span className="spinner" style={{ width: 16, height: 16 }} />}
        </span>
        <div style={{ flex: 1 }}>
          <p style={{ fontWeight: 500, lineHeight: 1.5, fontSize: '0.94rem' }}>
            {claim.text}
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
            {claim.claim_type && (
              <span className={`badge badge-${claim.claim_type}`}>{claim.claim_type}</span>
            )}
            {claim.checkability && (
              <span className="badge" style={{ background: 'rgba(255,255,255,.06)', color: 'var(--color-text-dim)' }}>
                {claim.checkability} checkability
              </span>
            )}
            {hasVerdict && (
              <span className={`badge badge-${verdict!.verdict.toLowerCase()}`}>
                {verdict!.verdict}
              </span>
            )}
          </div>

          {/* Confidence bar */}
          {hasVerdict && (
            <div style={{ marginTop: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>Confidence</span>
                <span style={{
                  fontSize: '0.75rem',
                  fontFamily: 'var(--font-mono)',
                  color: verdictColor,
                  fontWeight: 600,
                }}>
                  {pct}%
                </span>
              </div>
              <div className="confidence-bar-track">
                <div
                  className="confidence-bar-fill"
                  style={{ width: `${pct}%`, background: verdictColor }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Expandable section */}
      {(verdict?.reasoning || sources.length > 0) && (
        <div style={{ marginTop: '16px' }}>
          <button
            className="btn btn-secondary"
            style={{ fontSize: '0.8rem', padding: '6px 14px' }}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? '▲ Hide details' : `▼ Show details (${sources.length} sources)`}
          </button>

          {expanded && (
            <div style={{ marginTop: '16px' }} className="fade-in">
              {verdict?.reasoning && (
                <div style={{
                  padding: '12px',
                  background: 'rgba(255,255,255,.03)',
                  borderRadius: '8px',
                  marginBottom: '12px',
                }}>
                  <p style={{ fontSize: '0.8rem', color: 'var(--color-text-dim)', fontStyle: 'italic' }}>
                    {verdict.reasoning}
                  </p>
                </div>
              )}
              {sources.map((s) => (
                <SourceCard key={s.url} source={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
