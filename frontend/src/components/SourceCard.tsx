import { ExternalLink, Check, HelpCircle } from 'lucide-react'
import type { Source } from '../context/JobContext'

const STANCE_META: Record<string, {
  label: string;
  icon: React.ReactNode;
  badgeClass: string;
}> = {
  SUPPORTS: {
    label: 'Supports',
    icon: <Check size={12} className="text-emerald-400" />,
    badgeClass: 'tag-success',
  },
  REFUTES: {
    label: 'Refutes',
    icon: <ExternalLink size={12} className="text-rose-400" />, // Wait, let's use a nice Alert or X icon
    badgeClass: 'tag-danger',
  },
  NEUTRAL: {
    label: 'Neutral',
    icon: <HelpCircle size={12} className="text-slate-400" />,
    badgeClass: 'tag-muted',
  },
  UNCLEAR: {
    label: 'Unclear',
    icon: <HelpCircle size={12} className="text-slate-400" />,
    badgeClass: 'tag-muted',
  },
}

interface Props {
  source: Source
}

export default function SourceCard({ source }: Props) {
  const stance = source.stance || 'UNCLEAR'
  const meta = STANCE_META[stance] || STANCE_META.UNCLEAR
  const quality = source.quality_score ?? 0
  const qualityPct = Math.round(quality * 100)

  // Stance borders compatibility
  const borderClass = 
    stance === 'SUPPORTS' ? 'stance-supports' : 
    stance === 'REFUTES' ? 'stance-refutes' : 
    stance === 'NEUTRAL' ? 'stance-neutral' : 'stance-unclear'

  return (
    <div
      className={`glass-card ${borderClass} p-4 bg-slate-950/20 hover:bg-slate-950/40 rounded-xl transition-all duration-200 border-l-4`}
    >
      <div className="flex flex-col gap-2.5">
        {/* Title, Stance, Quality Header */}
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          {/* External Citation Link */}
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-sm font-bold text-white hover:text-accent transition-colors duration-150 min-w-0 max-w-[70%]"
            title={source.title || source.url}
          >
            <span className="truncate">{source.title || source.url}</span>
            <ExternalLink size={13} className="opacity-40 hover:opacity-100 flex-shrink-0" />
          </a>

          {/* Stance Tag and Quality Metric */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className={`premium-tag ${meta.badgeClass} flex items-center gap-1 py-0.5 px-2.5 text-[9px]`}>
              {meta.icon}
              <span>{meta.label}</span>
            </span>
            <span 
              className={`text-xs font-mono font-bold ${
                quality > 0.7 ? 'text-emerald-400' :
                quality > 0.4 ? 'text-amber-400' : 'text-slate-400'
              }`}
              title="Source Quality Score"
            >
              Q: {qualityPct}%
            </span>
          </div>
        </div>

        {/* Source Domain Name */}
        {source.domain && (
          <div className="text-[10px] font-mono text-text-muted">
            source: <span className="text-indigo-400/80 font-bold">{source.domain}</span>
          </div>
        )}

        {/* Context Snippet Quotation */}
        {source.snippet && (
          <p className="text-xs text-text-dim leading-relaxed bg-slate-950/50 p-2.5 rounded-lg border border-white/[0.01]">
            "{source.snippet}"
          </p>
        )}
      </div>
    </div>
  )
}
