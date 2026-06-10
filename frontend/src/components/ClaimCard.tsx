import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  CheckCircle2, 
  XCircle, 
  Scale, 
  HelpCircle, 
  ChevronDown, 
  BookOpen, 
  Sparkles 
} from 'lucide-react'
import type { Claim, ClaimVerdict, Source } from '../context/JobContext'
import SourceCard from './SourceCard'

const VERDICT_THEME: Record<string, {
  color: string;
  borderColor: string;
  glowColor: string;
  icon: React.ReactNode;
  label: string;
}> = {
  SUPPORTED: {
    color: '#10b981',
    borderColor: 'rgba(16, 185, 129, 0.2)',
    glowColor: 'rgba(16, 185, 129, 0.03)',
    icon: <CheckCircle2 className="text-emerald-400" size={18} />,
    label: 'Supported',
  },
  REFUTED: {
    color: '#ef4444',
    borderColor: 'rgba(239, 68, 68, 0.2)',
    glowColor: 'rgba(239, 68, 68, 0.03)',
    icon: <XCircle className="text-rose-400" size={18} />,
    label: 'Refuted',
  },
  CONTESTED: {
    color: '#f59e0b',
    borderColor: 'rgba(245, 158, 11, 0.2)',
    glowColor: 'rgba(245, 158, 11, 0.03)',
    icon: <Scale className="text-amber-400" size={18} />,
    label: 'Contested',
  },
  UNVERIFIABLE: {
    color: '#64748b',
    borderColor: 'rgba(100, 116, 139, 0.2)',
    glowColor: 'rgba(100, 116, 139, 0.03)',
    icon: <HelpCircle className="text-slate-400" size={18} />,
    label: 'Unverifiable',
  },
}

interface Props {
  claim: Claim
  verdict?: ClaimVerdict
  sources: Source[]
  index?: number
}

export default function ClaimCard({ claim, verdict, sources, index }: Props) {
  const [expanded, setExpanded] = useState(false)
  const hasVerdict = !!verdict
  
  const theme = hasVerdict 
    ? VERDICT_THEME[verdict!.verdict] 
    : {
        color: '#6366f1',
        borderColor: 'rgba(99, 102, 241, 0.12)',
        glowColor: 'rgba(99, 102, 241, 0.02)',
        icon: <span className="premium-loader" style={{ width: 15, height: 15 }} />,
        label: 'Processing',
      }

  const confidence = verdict?.confidence ?? 0
  const pct = Math.round(confidence * 100)

  return (
    <div
      id={`claim-${claim.claim_id}`}
      className="glass-card p-5 border rounded-2xl bg-bg-glass backdrop-blur-xl shadow-card hover:border-border-hover transition-all duration-300"
      style={{
        borderColor: theme.borderColor,
        boxShadow: `0 10px 30px -10px rgba(0, 0, 0, 0.5), 0 0 15px ${theme.glowColor}`
      }}
    >
      {/* Claim Body Layout */}
      <div className="flex gap-4 items-start">
        {/* Status Indicator Icon */}
        <div className="flex-shrink-0 mt-1 w-8 h-8 rounded-lg bg-white/[0.02] border border-white/[0.04] flex items-center justify-center">
          {theme.icon}
        </div>

        {/* Text and Badges */}
        <div className="flex-1 text-left min-w-0">
          <p className="text-sm sm:text-base font-bold text-white leading-relaxed">
            {claim.text}
          </p>

          {/* Badges and Tags row */}
          <div className="flex flex-wrap gap-2 mt-3.5">
            {index !== undefined && (
              <span className="premium-tag text-[10px] bg-indigo-950/60 text-indigo-300 border border-indigo-500/20">
                Priority Rank #{index + 1}
              </span>
            )}
            {claim.claim_type && (
              <span className={`premium-tag tag-info text-[10px]`}>
                {claim.claim_type}
              </span>
            )}
            {claim.checkability && (
              <span className="premium-tag tag-muted text-[10px]">
                Checkability: {claim.checkability}
              </span>
            )}
            {hasVerdict && (
              <span className={`premium-tag ${
                verdict!.verdict === 'SUPPORTED' ? 'tag-success' :
                verdict!.verdict === 'REFUTED' ? 'tag-danger' :
                verdict!.verdict === 'CONTESTED' ? 'tag-warning' : 'tag-muted'
              } text-[10px]`}>
                {theme.label}
              </span>
            )}
          </div>

          {/* Source Overlap / Consensus Indicator */}
          {sources.length > 0 && (
            <div className="mt-3.5 bg-slate-950/20 p-2.5 rounded-lg border border-white/[0.01] flex flex-wrap items-center justify-between gap-2.5 text-xs text-text-dim">
              <span className="text-[10px] text-text-muted font-bold tracking-wider">SOURCE CONSENSUS</span>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5 font-bold font-mono text-[10px] text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  {sources.filter(s => s.stance === 'SUPPORTS').length} Support
                </span>
                <span className="flex items-center gap-1.5 font-bold font-mono text-[10px] text-rose-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  {sources.filter(s => s.stance === 'REFUTES').length} Refute
                </span>
                <span className="flex items-center gap-1.5 font-bold font-mono text-[10px] text-slate-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  {sources.filter(s => s.stance === 'NEUTRAL' || s.stance === 'UNCLEAR').length} Neutral
                </span>
              </div>
            </div>
          )}

          {/* Credibility Confidence slider */}
          {hasVerdict && (
            <div className="mt-4 bg-slate-950/40 p-3 rounded-lg border border-white/[0.02]">
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-[10px] text-text-muted font-bold tracking-wider">VERDICT CONFIDENCE</span>
                <span 
                  className="text-xs font-bold font-mono"
                  style={{ color: theme.color }}
                >
                  {pct}%
                </span>
              </div>
              <div className="confidence-bar-track h-1.5 bg-slate-900 rounded-full">
                <motion.div
                  className="confidence-bar-fill h-full rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.6, ease: "easeOut" }}
                  style={{ background: theme.color }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Expand Accordion Controls */}
      {(hasVerdict) && (
        <div className="mt-4 pt-3 border-t border-border/40 text-left">
          <button
            className="flex items-center gap-1.5 text-xs font-bold text-accent hover:text-indigo-400 cursor-pointer transition-colors duration-200"
            onClick={() => setExpanded(!expanded)}
          >
            <BookOpen size={13} />
            <span>
              {expanded
                ? 'Hide verification breakdown'
                : sources.length > 0
                  ? `Show details (${sources.length} source${sources.length === 1 ? '' : 's'})`
                  : 'Show verification details'}
            </span>
            <motion.div
              animate={{ rotate: expanded ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronDown size={14} />
            </motion.div>
          </button>

          {/* Smooth accordion panel using Framer Motion */}
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <div className="pt-4 flex flex-col gap-3">
                  {/* Citations List */}
                  {sources.length > 0 ? (
                    <div>
                      <span className="text-[10px] text-text-muted font-bold tracking-wider block mb-2 px-1">CORROBORATING CITATIONS</span>
                      <div className="flex flex-col gap-2">
                        {sources.map((s) => (
                          <SourceCard key={s.url} source={s} claimText={claim.text} />
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2.5 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-text-muted text-xs">
                      <span className="text-amber-500/70 mt-0.5 flex-shrink-0">⚠</span>
                      <span className="text-amber-200/60">No external verification source found for this claim.</span>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
