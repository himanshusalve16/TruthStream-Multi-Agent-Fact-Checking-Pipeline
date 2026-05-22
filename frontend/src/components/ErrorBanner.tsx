interface Props {
  message: string
  onRetry?: () => void
}

export default function ErrorBanner({ message, onRetry }: Props) {
  return (
    <div
      id="error-banner"
      className="glass-card fade-in"
      style={{
        padding: '20px 24px',
        border: '1px solid rgba(239,68,68,.3)',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
      }}
    >
      <span style={{ fontSize: '1.5rem' }}>❌</span>
      <div style={{ flex: 1 }}>
        <p style={{ fontWeight: 600, color: 'var(--color-danger)' }}>Error</p>
        <p style={{ fontSize: '0.88rem', color: 'var(--color-text-dim)', marginTop: '4px' }}>{message}</p>
      </div>
      {onRetry && (
        <button className="btn btn-secondary" onClick={onRetry} style={{ flexShrink: 0 }}>
          Retry
        </button>
      )}
    </div>
  )
}
