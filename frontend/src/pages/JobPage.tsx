import { useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useJobContext } from '../context/JobContext'
import { useJobStream } from '../hooks/useJobStream'
import LoadingState from '../components/LoadingState'
import ErrorBanner from '../components/ErrorBanner'
import VerdictBanner from '../components/VerdictBanner'
import VerdictTimeline from '../components/VerdictTimeline'
import ClaimList from '../components/ClaimList'
import BiasPanel from '../components/BiasPanel'

export default function JobPage() {
  const { id } = useParams<{ id: string }>()
  const { state, dispatch } = useJobContext()
  const navigate = useNavigate()

  // Ensure jobId is set if navigated to directly
  useEffect(() => {
    if (id && state.jobId !== id) {
      dispatch({ type: 'SET_JOB_ID', jobId: id })
      dispatch({ type: 'SET_STAGE', stage: 'fetching_article', message: 'Connecting to pipeline...' })
    }
  }, [id])

  // Open SSE stream
  useJobStream(id ?? null)

  const isComplete = state.stage === 'complete'
  const isError = state.stage === 'error'
  const hasVerdict = !!state.verdict
  const claimVerdicts = state.verdict?.claim_verdicts ?? []

  return (
    <div>
      {/* Nav */}
      <nav className="nav">
        <div className="container nav-inner">
          <Link to="/" className="nav-logo" style={{ textDecoration: 'none' }}>⚡ TruthStream</Link>
          <div className="nav-links">
            <Link to="/">New Check</Link>
            <Link to="/history">History</Link>
          </div>
        </div>
      </nav>

      <main className="container" style={{ paddingTop: '32px', paddingBottom: '60px', maxWidth: '900px' }}>
        {/* Job ID */}
        <div style={{ marginBottom: '24px' }}>
          <p style={{ fontSize: '0.78rem', color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
            Job ID: {id}
          </p>
          {state.stage !== 'idle' && state.stage !== 'complete' && state.stage !== 'error' && (
            <p style={{ fontSize: '0.9rem', color: 'var(--color-text-dim)', marginTop: '4px' }}>
              {state.stageMessage}
            </p>
          )}
        </div>

        {/* Error */}
        {isError && (
          <ErrorBanner
            message={state.error || 'An unexpected error occurred.'}
            onRetry={() => navigate('/')}
          />
        )}

        {/* Loading indicator */}
        {!isError && !isComplete && (
          <div style={{ marginBottom: '24px' }}>
            <LoadingState stage={state.stage} message={state.stageMessage} />
          </div>
        )}

        {/* Verdict banner */}
        {hasVerdict && (
          <div style={{ marginBottom: '24px' }}>
            <VerdictBanner
              verdict={state.verdict!.overall_verdict}
              confidence={state.verdict!.overall_confidence}
              summary={state.verdict!.overall_summary}
            />
          </div>
        )}

        {/* Verdict timeline */}
        {hasVerdict && state.claims.length > 0 && (
          <VerdictTimeline claims={state.claims} verdicts={claimVerdicts} />
        )}

        {/* Bias Panel + Claims (two-col on large screens) */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: state.bias ? '1fr 340px' : '1fr',
          gap: '24px',
          alignItems: 'flex-start',
        }}>
          <div>
            <ClaimList
              claims={state.claims}
              claimVerdicts={claimVerdicts}
              sourcesByClaim={state.sourcesByClaim}
            />
          </div>
          {state.bias && (
            <div style={{ position: 'sticky', top: '80px' }}>
              <BiasPanel bias={state.bias} />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
