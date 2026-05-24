import { motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, XCircle, HelpCircle, Scale } from 'lucide-react'
import ConfidenceGauge from './ConfidenceGauge'

interface Props {
  verdict: string
  confidence: number
  summary: string
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

export default function VerdictBanner({ verdict, confidence, summary }: Props) {
  const meta = VERDICT_META[verdict] || {
    label: verdict,
    icon: <HelpCircle className="text-slate-400" size={28} />,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    glowColor: 'rgba(255, 255, 255, 0.02)',
    textColor: 'text-slate-400',
    badgeStyle: 'tag-muted',
  }

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
        <div className="flex-1 text-left min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              {meta.icon}
            </div>
            <div>
              <span className="text-[10px] text-text-muted font-bold uppercase tracking-widest block">Overall Consensus Verdict</span>
              <h2 className={`text-2xl font-black tracking-tight leading-none ${meta.textColor}`}>
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
          <div className="p-4 bg-slate-950/40 rounded-xl border border-white/[0.02]">
            <p className="text-sm sm:text-base text-text-dim leading-relaxed font-medium">
              {summary}
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  )
}
