import { motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, XCircle, HelpCircle, Scale, Globe, TrendingUp } from 'lucide-react'
import ConfidenceGauge from './ConfidenceGauge'

interface SourceStats {
  total: number
  supporting: number
  refuting: number
  neutral: number
}

interface Props {
  verdict: string
  confidence: number
  summary: string
  sourceStats?: SourceStats
}

const VERDICT_META: Record<string, { 
  label: string; 
  icon: React.ReactNode; 
  borderColor: string;
  glowColor: string;
  textColor: string;
  badgeStyle: string;
}> = {
  MOSTLY_TRUE: {
    label: 'Mostly True',
    icon: <CheckCircle2 className="text-emerald-400" size={28} />,
    borderColor: 'rgba(16, 185, 129, 0.25)',
    glowColor: 'rgba(16, 185, 129, 0.05)',
    textColor: 'text-emerald-400',
    badgeStyle: 'tag-success',
  },
  MIXTURE: {
    label: 'Mixture of Fact & Fiction',
    icon: <Scale className="text-amber-400" size={28} />,
    borderColor: 'rgba(245, 158, 11, 0.25)',
    glowColor: 'rgba(245, 158, 11, 0.05)',
    textColor: 'text-amber-400',
    badgeStyle: 'tag-warning',
  },
  MOSTLY_FALSE: {
    label: 'Mostly False',
    icon: <XCircle className="text-rose-400" size={28} />,
    borderColor: 'rgba(239, 68, 68, 0.25)',
    glowColor: 'rgba(239, 68, 68, 0.05)',
    textColor: 'text-rose-400',
    badgeStyle: 'tag-danger',
  },
  UNVERIFIABLE: {
    label: 'Unverifiable Statement',
    icon: <HelpCircle className="text-slate-400" size={28} />,
    borderColor: 'rgba(100, 116, 139, 0.25)',
    glowColor: 'rgba(100, 116, 139, 0.05)',
    textColor: 'text-slate-400',
    badgeStyle: 'tag-muted',
  },
}

export default function VerdictBanner({ verdict, confidence, summary, sourceStats }: Props) {
  const meta = VERDICT_META[verdict] || {
    label: verdict,
    icon: <HelpCircle className="text-slate-400" size={28} />,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    glowColor: 'rgba(255, 255, 255, 0.02)',
    textColor: 'text-slate-400',
    badgeStyle: 'tag-muted',
  }

  const hasSourceStats = sourceStats !== undefined
  const hasSources = hasSourceStats && sourceStats!.total > 0

  return (
    <motion.div 
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      id="verdict-banner" 
      className="glass-card p-6 sm:p-8 rounded-2xl border bg-bg-glass backdrop-blur-xl shadow-card"
      style={{ 
        borderColor: meta.borderColor,
        boxShadow: `0 10px 30px -10px rgba(0, 0, 0, 0.7), 0 0 25px ${meta.glowColor}`
      }}
    >
      <div className="flex flex-col md:flex-row gap-8 items-center">
        {/* Animated Confidence Gauge */}
        <div className="flex-shrink-0 relative">
          <ConfidenceGauge confidence={confidence} verdict={verdict} size={170} />
        </div>

        {/* Verdict Details */}
        <div className="flex-1 text-center sm:text-left min-w-0 w-full">
          <div className="flex flex-col sm:flex-row items-center gap-3 mb-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-white/[0.02] border border-white/[0.04] flex-shrink-0">
              {meta.icon}
            </div>
            <div>
              <span className="text-[10px] text-text-muted font-bold uppercase tracking-widest block">Overall Consensus Verdict</span>
              <h2 className={`text-xl sm:text-2xl font-black tracking-tight leading-none ${meta.textColor}`}>
                {meta.label}
              </h2>
            </div>
          </div>

          {/* Low Confidence Warning Notice */}
          {confidence < 0.4 && (
            <div className="flex items-start gap-2.5 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-amber-400 text-xs mb-4">
              <AlertTriangle size={15} className="mt-0.5 flex-shrink-0" />
              <div>
                <span className="font-bold">Caution:</span> Low verification confidence. Information sources are limited or highly contested.
              </div>
            </div>
          )}

          {/* Verdict Description Summary */}
          <div className="p-4 bg-slate-950/40 rounded-xl border border-white/[0.02] mb-4">
            <p className="text-sm sm:text-base text-text-dim leading-relaxed font-medium">
              {summary}
            </p>
          </div>

          {/* Verification Sources Summary Row */}
          <div className="mt-1">
            <span className="text-[10px] text-text-muted font-bold tracking-wider uppercase flex items-center gap-1.5 mb-2">
              <Globe size={11} className="text-indigo-400" />
              Verification Sources
            </span>

            {hasSources ? (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25, duration: 0.3 }}
                className="grid grid-cols-4 gap-2"
              >
                {/* Total */}
                <div className="bg-slate-950/50 border border-white/[0.04] rounded-lg px-3 py-2 text-center">
                  <span className="text-[9px] text-text-muted font-bold tracking-wider block mb-0.5">TOTAL</span>
                  <span className="text-sm font-black font-mono text-white">{sourceStats!.total}</span>
                </div>
                {/* Supporting */}
                <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg px-3 py-2 text-center">
                  <span className="text-[9px] text-emerald-500/70 font-bold tracking-wider block mb-0.5">SUPPORT</span>
                  <span className="text-sm font-black font-mono text-emerald-400">{sourceStats!.supporting}</span>
                </div>
                {/* Refuting */}
                <div className="bg-rose-500/5 border border-rose-500/20 rounded-lg px-3 py-2 text-center">
                  <span className="text-[9px] text-rose-500/70 font-bold tracking-wider block mb-0.5">REFUTE</span>
                  <span className="text-sm font-black font-mono text-rose-400">{sourceStats!.refuting}</span>
                </div>
                {/* Neutral */}
                <div className="bg-slate-500/5 border border-slate-500/20 rounded-lg px-3 py-2 text-center">
                  <span className="text-[9px] text-slate-400/70 font-bold tracking-wider block mb-0.5">NEUTRAL</span>
                  <span className="text-sm font-black font-mono text-slate-400">{sourceStats!.neutral}</span>
                </div>
              </motion.div>
            ) : hasSourceStats ? (
              /* No sources found — explicit empty state */
              <div className="flex items-center gap-2.5 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-text-muted text-xs">
                <TrendingUp size={14} className="text-amber-500/60 flex-shrink-0" />
                <span className="text-amber-200/60">No external verification sources found. Verdict is based on AI reasoning only.</span>
              </div>
            ) : (
              /* Still loading sources */
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <span className="w-3 h-3 border-2 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin flex-shrink-0" />
                <span>Fetching verification sources…</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
