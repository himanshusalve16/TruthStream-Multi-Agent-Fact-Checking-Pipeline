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
    icon: <ExternalLink size={12} className="text-rose-400" />,
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
  claimText?: string
}

function getFreshness(snippet?: string): string {
  if (!snippet) return 'N/A'
  // Match "15 hours ago", "3 days ago", "Oct 12, 2024", "2024-10-12", "12 Oct 2024"
  const regexes = [
    /\b\d{1,2}\s+(?:hours?|days?|weeks?|months?|years?)\s+ago\b/i,
    /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b/i,
    /\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b/i,
    /\b\d{4}-\d{2}-\d{2}\b/
  ]
  for (const r of regexes) {
    const m = snippet.match(r)
    if (m) return m[0]
  }
  return 'Recent'
}

function calculateRelevance(claimText?: string, snippet?: string): number {
  if (!claimText || !snippet) return 0
  const stopWords = new Set(['the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'that', 'this', 'it', 'as', 'from', 'at'])
  
  const getWords = (text: string) => {
    const words = text.toLowerCase().match(/\b\w{2,}\b/g) || []
    return new Set(words.filter(w => !stopWords.has(w)))
  }
  
  const claimWords = getWords(claimText)
  const snippetWords = getWords(snippet)
  
  if (claimWords.size === 0 || snippetWords.size === 0) return 0
  
  let intersectionSize = 0
  claimWords.forEach(w => {
    if (snippetWords.has(w)) {
      intersectionSize++
    }
  })
  
  const unionSize = claimWords.size + snippetWords.size - intersectionSize
  return unionSize > 0 ? intersectionSize / unionSize : 0
}

export default function SourceCard({ source, claimText }: Props) {
  const stance = source.stance || 'UNCLEAR'
  const meta = STANCE_META[stance] || STANCE_META.UNCLEAR
  const quality = source.quality_score ?? 0
  const qualityPct = Math.round(quality * 100)
  
  const freshness = getFreshness(source.snippet)
  const relevanceScore = calculateRelevance(claimText, source.snippet)
  const relevancePct = Math.round(relevanceScore * 100)

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
        {/* Title, Stance Header */}
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          {/* External Citation Link */}
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-sm font-bold text-white hover:text-accent transition-colors duration-150 min-w-0 max-w-full sm:max-w-[70%]"
            title={source.title || source.url}
          >
            <span className="truncate">{source.title || source.url}</span>
            <ExternalLink size={13} className="opacity-40 hover:opacity-100 flex-shrink-0" />
          </a>

          {/* Stance Tag */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className={`premium-tag ${meta.badgeClass} flex items-center gap-1 py-0.5 px-2.5 text-[9px]`}>
              {meta.icon}
              <span>{meta.label}</span>
            </span>
          </div>
        </div>

        {/* Source Domain Name */}
        {source.domain && (
          <div className="text-[10px] font-mono text-text-muted">
            source: <span className="text-indigo-400/80 font-bold">{source.domain}</span>
          </div>
        )}

        {/* Structured 3-column metadata grid for comparison */}
        <div className="grid grid-cols-3 gap-2 bg-slate-950/40 p-2 rounded-lg border border-white/[0.02]">
          {/* Credibility Column */}
          <div className="text-center">
            <span className="text-[9px] text-text-muted font-bold tracking-wider block mb-0.5">CREDIBILITY</span>
            <span className={`text-xs font-mono font-bold ${
              quality > 0.7 ? 'text-emerald-400' :
              quality > 0.4 ? 'text-amber-400' : 'text-slate-400'
            }`}>
              {qualityPct}%
            </span>
          </div>

          {/* Freshness Column */}
          <div className="text-center border-x border-white/[0.04]">
            <span className="text-[9px] text-text-muted font-bold tracking-wider block mb-0.5">FRESHNESS</span>
            <span className="text-xs font-mono font-bold text-indigo-300">
              {freshness}
            </span>
          </div>

          {/* Relevance Column */}
          <div className="text-center">
            <span className="text-[9px] text-text-muted font-bold tracking-wider block mb-0.5">RELEVANCE</span>
            <span className={`text-xs font-mono font-bold ${
              relevancePct > 40 ? 'text-emerald-400' :
              relevancePct > 20 ? 'text-amber-400' : 'text-slate-400'
            }`}>
              {relevancePct}%
            </span>
          </div>
        </div>

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
