import type { Stage } from '../context/JobContext'

const STAGES: { key: Stage; label: string; icon: string }[] = [
  { key: 'fetching_article',  label: 'Fetching',   icon: '🌐' },
  { key: 'extracting_claims', label: 'Extracting', icon: '🔍' },
  { key: 'sourcing_claims',   label: 'Sourcing',   icon: '📚' },
  { key: 'judging',           label: 'Judging',    icon: '⚖️' },
  { key: 'complete',          label: 'Complete',   icon: '✅' },
]

const STAGE_ORDER: Stage[] = [
  'fetching_article', 'extracting_claims', 'sourcing_claims', 'judging', 'complete'
]

interface Props {
  stage: Stage
  message?: string
}

export default function LoadingState({ stage, message }: Props) {
  const currentIdx = STAGE_ORDER.indexOf(stage)

  return (
    <div id="loading-state" className="glass-card fade-in" style={{ padding: '28px 32px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
        {stage !== 'complete' && <span className="spinner" />}
        <div>
          <p style={{ fontWeight: 600, fontSize: '0.95rem' }}>
            {message || 'Processing your article...'}
          </p>
          <p style={{ color: 'var(--color-text-dim)', fontSize: '0.82rem', marginTop: '2px' }}>
            This typically takes 30–90 seconds
          </p>
        </div>
      </div>

      {/* Stage dots */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        {STAGES.map((s, i) => {
          const isDone = i < currentIdx
          const isActive = i === currentIdx
          return (
            <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1 }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '1.1rem' }}>{s.icon}</span>
                <div
                  className={`stage-dot ${isDone ? 'done' : isActive ? 'active' : ''}`}
                />
                <span style={{
                  fontSize: '0.7rem',
                  color: isDone ? 'var(--color-success)' : isActive ? 'var(--color-accent)' : 'var(--color-muted)',
                  fontWeight: isActive ? 600 : 400,
                  whiteSpace: 'nowrap',
                }}>
                  {s.label}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <div style={{
                  flex: 1,
                  height: '1px',
                  background: isDone ? 'var(--color-success)' : 'var(--color-border)',
                  marginBottom: '20px',
                  transition: 'background 0.4s',
                }} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
