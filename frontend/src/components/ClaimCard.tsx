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
}

export default function ClaimCard({ claim, verdict, sources }: Props) {
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
      {(verdict?.reasoning || sources.length > 0) && (
        <div className="mt-4 pt-3 border-t border-border/40 text-left">
          <button
            className="flex items-center gap-1.5 text-xs font-bold text-accent hover:text-indigo-400 cursor-pointer transition-colors duration-200"
            onClick={() => setExpanded(!expanded)}
          >
            <BookOpen size={13} />
            <span>
              {expanded ? 'Hide verification breakdown' : `Show details (${sources.length} sources)`}
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
                  {/* AI Agent Reasoning block */}
                  {verdict?.reasoning && (
                    <div className="p-4 bg-slate-950/60 rounded-xl border border-white/[0.02] flex gap-2.5">
                      <Sparkles size={16} className="text-purple-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <span className="text-[10px] text-text-muted font-bold tracking-wider block mb-1">AGENT REASONING</span>
                        <p className="text-xs sm:text-sm text-text-dim leading-relaxed font-medium">
                          {verdict.reasoning}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Citations List */}
                  {sources.length > 0 && (
                    <div>
                      <span className="text-[10px] text-text-muted font-bold tracking-wider block mb-2 px-1">CORROBORATING CITATIONS</span>
                      <div className="flex flex-col gap-2">
                        {sources.map((s) => (
                          <SourceCard key={s.url} source={s} />
                        ))}
                      </div>
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
