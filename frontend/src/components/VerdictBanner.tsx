import ConfidenceGauge from './ConfidenceGauge'

interface Props {
  verdict: string
  confidence: number
  summary: string
}

const VERDICT_META: Record<string, { label: string; emoji: string; className: string }> = {
  MOSTLY_TRUE: {
    label: 'Mostly True',
    emoji: '✅',
    className: 'verdict-mostly-true',
  },
  MIXTURE: {
    label: 'Mixture of Fact & Fiction',
    emoji: '⚖️',
    className: 'verdict-mixture',
  },
  MOSTLY_FALSE: {
    label: 'Mostly False',
    emoji: '❌',
    className: 'verdict-mostly-false',
  },
  UNVERIFIABLE: {
    label: 'Unverifiable',
    emoji: '❓',
    className: 'verdict-unverifiable',
  },
}

export default function VerdictBanner({ verdict, confidence, summary }: Props) {
  const meta = VERDICT_META[verdict] || {
    label: verdict,
    emoji: '❓',
    className: 'verdict-unverifiable',
  }

  return (
    <div id="verdict-banner" className="glass-card fade-in" style={{ padding: '28px 32px' }}>
      <div style={{ display: 'flex', gap: '32px', alignItems: 'center', flexWrap: 'wrap' }}>
        {/* Gauge */}
        <div style={{ flexShrink: 0 }}>
          <ConfidenceGauge confidence={confidence} verdict={verdict} size={180} />
        </div>

        {/* Text */}
        <div style={{ flex: 1, minWidth: '240px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <span style={{ fontSize: '2rem' }}>{meta.emoji}</span>
            <h1
              className={`gradient-text`}
              style={{
                fontSize: '1.8rem',
                fontWeight: 800,
                lineHeight: 1.2,
              }}
            >
              {meta.label}
            </h1>
          </div>

          {confidence < 0.4 && (
            <div style={{
              padding: '10px 14px',
              background: 'rgba(245,158,11,.1)',
              border: '1px solid rgba(245,158,11,.3)',
              borderRadius: '8px',
              marginBottom: '12px',
            }}>
              <p style={{ fontSize: '0.82rem', color: 'var(--color-warning)' }}>
                ⚠ Insufficient evidence to reach a high-confidence verdict. Treat this result with caution.
              </p>
            </div>
          )}

          <p style={{
            fontSize: '0.9rem',
            color: 'var(--color-text-dim)',
            lineHeight: 1.7,
          }}>
            {summary}
          </p>
        </div>
      </div>
    </div>
  )
}
