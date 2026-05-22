import { Source } from '../context/JobContext'

const STANCE_ICONS: Record<string, string> = {
  SUPPORTS: '✅',
  REFUTES: '❌',
  NEUTRAL: '➖',
  UNCLEAR: '❓',
}

const STANCE_LABELS: Record<string, string> = {
  SUPPORTS: 'Supports',
  REFUTES: 'Refutes',
  NEUTRAL: 'Neutral',
  UNCLEAR: 'Unclear',
}

interface Props {
  source: Source
}

export default function SourceCard({ source }: Props) {
  const stance = source.stance || 'UNCLEAR'
  const stanceClass = `stance-${stance.toLowerCase()}`
  const quality = source.quality_score ?? 0
  const qualityPct = Math.round(quality * 100)

  return (
    <div
      className={`glass-card ${stanceClass}`}
      style={{ padding: '14px 16px', marginBottom: '10px', borderRadius: '10px' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <span style={{ fontSize: '1.1rem', flexShrink: 0, marginTop: '2px' }}>
          {STANCE_ICONS[stance]}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                fontWeight: 600,
                fontSize: '0.88rem',
                color: 'var(--color-text)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                maxWidth: '70%',
              }}
              title={source.title || source.url}
            >
              {source.title || source.domain || source.url}
            </a>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
              <span
                className={`badge badge-${stance.toLowerCase() === 'supports' ? 'supported'
                  : stance.toLowerCase() === 'refutes' ? 'refuted'
                  : 'unverifiable'}`}
                style={{ fontSize: '0.68rem' }}
              >
                {STANCE_LABELS[stance]}
              </span>
              <span style={{
                fontSize: '0.7rem',
                color: quality > 0.6 ? 'var(--color-success)' : quality > 0.3 ? 'var(--color-warning)' : 'var(--color-muted)',
                fontFamily: 'var(--font-mono)',
              }}>
                {qualityPct}%
              </span>
            </div>
          </div>
          {source.domain && (
            <p style={{ fontSize: '0.75rem', color: 'var(--color-muted)', marginTop: '2px' }}>
              {source.domain}
            </p>
          )}
          {source.snippet && (
            <p style={{
              fontSize: '0.82rem',
              color: 'var(--color-text-dim)',
              marginTop: '8px',
              lineHeight: 1.5,
              display: '-webkit-box',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}>
              {source.snippet}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
