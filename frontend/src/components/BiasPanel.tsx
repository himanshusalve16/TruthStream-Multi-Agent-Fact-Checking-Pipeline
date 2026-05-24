import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Target, Compass, ChevronDown } from 'lucide-react'
import type { BiasData } from '../context/JobContext'

interface Props {
  bias: BiasData
}

const DIRECTION_LABELS: Record<string, string> = {
  left_leaning: 'Left Leaning',
  right_leaning: 'Right Leaning',
  pro_establishment: 'Pro-Establishment',
  anti_establishment: 'Anti-Establishment',
  neutral: 'Neutral Bias',
}

const SEVERITY_THEMES: Record<string, { border: string; text: string; bg: string }> = {
  low: {
    border: 'border-emerald-500/20 border-l-emerald-500',
    text: 'text-emerald-400',
    bg: 'bg-emerald-500/5',
  },
  medium: {
    border: 'border-amber-500/20 border-l-amber-500',
    text: 'text-amber-400',
    bg: 'bg-amber-500/5',
  },
  high: {
    border: 'border-rose-500/20 border-l-rose-500',
    text: 'text-rose-400',
    bg: 'bg-rose-500/5',
  },
}

function getBiasColor(score: number): string {
  if (score < 30) return '#10b981' // Green
  if (score < 60) return '#f59e0b' // Amber
  return '#ef4444' // Rose
}

export default function BiasPanel({ bias }: Props) {
  const [expanded, setExpanded] = useState(false)
  const biasColor = getBiasColor(bias.bias_score)

  return (
    <section 
      id="bias-panel" 
      className="glass-card p-6 bg-bg-glass backdrop-blur-xl border border-border rounded-2xl shadow-card text-left"
    >
      {/* Title & Score Header */}
      <div className="flex justify-between items-start mb-4">
        <h3 className="text-xs font-bold text-text-dim uppercase tracking-wider flex items-center gap-1.5">
          <Target size={13} className="text-accent" /> Bias Assessment
        </h3>
        <div className="text-right">
          <span 
            className="text-2xl font-black font-mono leading-none"
            style={{ color: biasColor }}
          >
            {bias.bias_score}
          </span>
          <span className="text-[10px] text-text-muted font-bold">/100</span>
        </div>
      </div>

      {/* Horizontal Bias Scale Bar */}
      <div className="confidence-bar-track h-2 bg-slate-900 rounded-full mb-4">
        <motion.div
          className="confidence-bar-fill h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${bias.bias_score}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          style={{ background: biasColor }}
        />
      </div>

      {/* Bias Direction Capsule */}
      <div className="flex flex-wrap gap-2 mb-4">
        <span className="premium-tag tag-info text-[9px] flex items-center gap-1">
          <Compass size={11} />
          <span>{DIRECTION_LABELS[bias.bias_direction] || bias.bias_direction}</span>
        </span>
      </div>

      {/* Summary Narrative */}
      <p className="text-xs sm:text-sm text-text-dim leading-relaxed mb-4 bg-slate-950/40 p-3.5 rounded-xl border border-white/[0.01]">
        {bias.summary}
      </p>

      {/* Loaded language terms pills */}
      {bias.loaded_terms && bias.loaded_terms.length > 0 && (
        <div className="mb-4">
          <span className="text-[10px] text-text-muted font-bold tracking-wider block mb-2">LOADED LANGUAGE</span>
          <div className="flex flex-wrap gap-1.5">
            {bias.loaded_terms.slice(0, 6).map((t) => (
              <span 
                key={t} 
                className="px-2 py-0.5 rounded bg-rose-500/5 text-rose-400 border border-rose-500/10 font-mono text-[10px] font-bold"
              >
                "{t}"
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Framing Flags collapsible block */}
      {bias.framing_flags && bias.framing_flags.length > 0 && (
        <div className="pt-3 border-t border-border/40">
          <button
            className="flex items-center gap-1.5 text-xs font-bold text-accent hover:text-indigo-400 cursor-pointer transition-colors duration-200"
            onClick={() => setExpanded(!expanded)}
          >
            <span>
              {expanded ? 'Hide framing details' : `Show framing details (${bias.framing_flags.length})`}
            </span>
            <motion.div
              animate={{ rotate: expanded ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronDown size={14} />
            </motion.div>
          </button>

          {/* Smooth accordion with Framer Motion */}
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <div className="pt-3 flex flex-col gap-2">
                  {bias.framing_flags.map((flag, i) => {
                    const theme = SEVERITY_THEMES[flag.severity || 'low'] || SEVERITY_THEMES.low
                    return (
                      <div
                        key={i}
                        className={`p-3 border rounded-lg border-l-4 ${theme.border} ${theme.bg} text-left`}
                      >
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-xs font-bold text-white">{flag.type}</span>
                          <span className={`text-[9px] font-extrabold uppercase tracking-wide ${theme.text}`}>
                            {flag.severity}
                          </span>
                        </div>
                        {flag.description && (
                          <p className="text-xs text-text-dim leading-relaxed">{flag.description}</p>
                        )}
                        {flag.examples && flag.examples.length > 0 && (
                          <p className="text-[10px] text-text-muted mt-1.5 italic">
                            e.g. "{flag.examples.join('", "')}"
                          </p>
                        )}
                      </div>
                    )
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </section>
  )
}
