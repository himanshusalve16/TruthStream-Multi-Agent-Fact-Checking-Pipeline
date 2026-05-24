import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { 
  ArrowLeft, 
  History, 
  Cpu, 
  Copy, 
  Check 
} from 'lucide-react'
import { useJobContext } from '../context/JobContext'
import { useJobStream } from '../hooks/useJobStream'
import { useJobHydration } from '../hooks/useJobHydration'
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
  const [copied, setCopied] = useState(false)

  // Ensure jobId is set if navigated to directly
  useEffect(() => {
    if (id && state.jobId !== id) {
      dispatch({ type: 'SET_JOB_ID', jobId: id })
      dispatch({ type: 'SET_STAGE', stage: 'fetching_article', message: 'Connecting to pipeline...' })
    }
  }, [id])

  const streamEnabled = useJobHydration(id)
  useJobStream(streamEnabled ? (id ?? null) : null)

  const isComplete = state.stage === 'complete'
  const isError = state.stage === 'error'
  const hasVerdict = !!state.verdict
  const claimVerdicts = state.verdict?.claim_verdicts ?? []

  const handleCopyId = () => {
    if (id) {
      navigator.clipboard.writeText(id)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  // Determine stage label for top header
  const getStageLabel = () => {
    if (isError) return 'Failed'
    if (isComplete) return 'Complete'
    switch(state.stage) {
      case 'fetching_article': return 'Fetching Article'
      case 'extracting_claims': return 'Extracting Claims'
      case 'sourcing_claims': return 'Sourcing Evidence'
      case 'judging': return 'Judging Veracity'
      default: return 'Queueing'
    }
  }

  return (
    <div className="relative min-h-screen bg-bg text-text overflow-hidden select-none pb-20">
      {/* Background patterns */}
      <div className="grid-bg" />
      <div className="glow-spot -top-[200px] left-[50%] -translate-x-1/2 w-[600px] h-[500px] bg-accent/5 opacity-55 rounded-full" />

      {/* Navigation Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-bg-glass backdrop-blur-md">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-xl font-extrabold tracking-tight group">
            <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-glow">
              ⚡
            </span>
            <span className="bg-gradient-to-r from-white to-text-dim bg-clip-text text-transparent font-bold">
              Truth<span className="text-accent font-black">Stream</span>
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link 
              to="/" 
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg border border-border bg-white/3 hover:bg-white/6 hover:border-border-hover text-text-dim hover:text-white transition-all duration-200"
            >
              <ArrowLeft size={13} />
              <span>New Check</span>
            </Link>
            <Link 
              to="/history" 
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg border border-border bg-white/3 hover:bg-white/6 hover:border-border-hover text-text-dim hover:text-white transition-all duration-200"
            >
              <History size={13} />
              <span>History</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Dashboard Panel */}
      <main className="container mx-auto px-6 pt-10 pb-16 relative z-10 max-w-5xl text-left">
        {/* Top Meta info */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 mb-6 rounded-2xl bg-white/[0.01] border border-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-accent/10 border border-accent/20 text-accent flex items-center justify-center">
              <Cpu size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-text-muted font-bold tracking-widest uppercase">Job Execution Node</span>
                <button 
                  onClick={handleCopyId}
                  className="p-1 hover:bg-white/5 rounded text-text-muted hover:text-white transition-colors duration-150"
                  title="Copy job ID"
                >
                  {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                </button>
              </div>
              <span className="font-mono text-xs text-text-dim">{id}</span>
            </div>
          </div>

          {/* Status Indicator */}
          <div className="flex items-center gap-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-white/[0.04] self-start sm:self-auto">
            <div className={`w-2 h-2 rounded-full ${
              isError ? 'bg-red-500' :
              isComplete ? 'bg-emerald-500' : 'bg-indigo-500 animate-pulse'
            }`} />
            <span className="font-mono text-xs font-bold text-white uppercase tracking-wider">{getStageLabel()}</span>
          </div>
        </div>

        {/* Dynamic Pipeline Details Stack */}
        <div className="flex flex-col gap-6">
          {/* Error Details Banner */}
          {isError && (
            <ErrorBanner
              message={state.error || 'An unexpected error occurred during execution.'}
              onRetry={() => navigate('/')}
            />
          )}

          {/* Sourcing/Processing Loading States */}
          {!isError && !isComplete && (
            <LoadingState stage={state.stage} message={state.stageMessage} />
          )}

          {/* Synthesized Verdict details */}
          {hasVerdict && (
            <VerdictBanner
              verdict={state.verdict!.overall_verdict}
              confidence={state.verdict!.overall_confidence}
              summary={state.verdict!.overall_summary}
            />
          )}

          {/* Flowchart Timeline */}
          {hasVerdict && state.claims.length > 0 && (
            <VerdictTimeline claims={state.claims} verdicts={claimVerdicts} />
          )}

          {/* Split Dashboard: Left: Claims citations list, Right: Media Bias assessment */}
          <div className={`grid grid-cols-1 ${state.bias ? 'lg:grid-cols-3' : 'grid-cols-1'} gap-6`}>
            <div className={state.bias ? 'lg:col-span-2 flex flex-col gap-4' : 'w-full'}>
              <ClaimList
                claims={state.claims}
                claimVerdicts={claimVerdicts}
                sourcesByClaim={state.sourcesByClaim}
              />
            </div>
            {state.bias && (
              <div className="lg:col-span-1 lg:sticky lg:top-24">
                <BiasPanel bias={state.bias} />
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
