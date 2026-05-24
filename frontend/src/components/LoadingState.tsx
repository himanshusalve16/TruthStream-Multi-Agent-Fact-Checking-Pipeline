import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Terminal, CheckCircle, Search, Globe, Scale } from 'lucide-react'
import type { Stage } from '../context/JobContext'

const STAGES: { key: Stage; label: string; icon: React.ReactNode; color: string }[] = [
  { key: 'fetching_article',  label: 'Fetching',   icon: <Globe size={18} />, color: '#818cf8' },
  { key: 'extracting_claims', label: 'Extracting', icon: <Search size={18} />, color: '#c084fc' },
  { key: 'sourcing_claims',   label: 'Sourcing',   icon: <Terminal size={18} />, color: '#38bdf8' },
  { key: 'judging',           label: 'Judging',    icon: <Scale size={18} />, color: '#a855f7' },
  { key: 'complete',          label: 'Complete',   icon: <CheckCircle size={18} />, color: '#34d399' },
]

const STAGE_ORDER: Stage[] = [
  'fetching_article', 'extracting_claims', 'sourcing_claims', 'judging', 'complete'
]

const SUBSTAGE_LOGS: Record<Stage, string[]> = {
  fetching_article: [
    'Connecting to target web host...',
    'Bypassing Paywalls & Content Scrapers...',
    'Extracting raw article body content...',
    'Sanitizing markup and filtering advertisements...',
    'Payload isolated (Text content extracted).'
  ],
  extracting_claims: [
    'Initializing Claim Extractor Agent...',
    'Tokenizing input texts & parsing syntax...',
    'Isolating checkable factual claims...',
    'Filtering subjective opinions & hyperbole...',
    'Identified checkable assertions.'
  ],
  sourcing_claims: [
    'Deploying Search Agent network...',
    'Querying semantic indices and news archives...',
    'Scraping corroborating articles & citation text...',
    'Filtering for reliable journalistic domains...',
    'Calculating source stances (Supports/Refutes/Neutral)...'
  ],
  judging: [
    'Spawning Bias Analyst Agent...',
    'Scoring sentiment levels & emotional framing...',
    'Cross-referencing claims against source stances...',
    'Compiling final confidence-weighted verdict matrix...',
    'Packaging results...'
  ],
  complete: [
    'Pipeline complete.',
    'Verdicts verified & persisted.'
  ],
  error: [
    'Pipeline terminated with error.'
  ],
  idle: [
    'Pipeline idle.'
  ]
}

interface Props {
  stage: Stage
  message?: string
}

export default function LoadingState({ stage, message }: Props) {
  const currentIdx = STAGE_ORDER.indexOf(stage)
  const [logs, setLogs] = useState<string[]>([])
  const [currentLogIdx, setCurrentLogIdx] = useState(0)

  // Append new logs corresponding to the current stage
  useEffect(() => {
    const stageLogs = SUBSTAGE_LOGS[stage] || []
    if (stageLogs.length > 0) {
      // Seed first log of new stage immediately
      setLogs(prev => [...prev, `[system] > ${stageLogs[0]}`])
      setCurrentLogIdx(1)
    }
  }, [stage])

  // Cycle through logs of the active stage to simulate real-time agent output
  useEffect(() => {
    const stageLogs = SUBSTAGE_LOGS[stage] || []
    if (currentLogIdx >= stageLogs.length) return

    const timer = setTimeout(() => {
      setLogs(prev => [...prev, `[agent] > ${stageLogs[currentLogIdx]}`])
      setCurrentLogIdx(prev => prev + 1)
    }, 1800)

    return () => clearTimeout(timer)
  }, [stage, currentLogIdx])

  return (
    <div id="loading-state" className="glass-card p-8 border border-border bg-bg-glass backdrop-blur-xl rounded-2xl shadow-card relative overflow-hidden">
      {/* Decorative background glow */}
      <div className="absolute -top-12 -right-12 w-32 h-32 bg-accent/5 rounded-full blur-2xl pointer-events-none" />

      {/* Main loading status header */}
      <div className="flex items-center gap-4 mb-8">
        {stage !== 'complete' ? (
          <div className="relative flex items-center justify-center">
            <span className="premium-loader" />
            <div className="absolute w-1.5 h-1.5 rounded-full bg-accent animate-ping" />
          </div>
        ) : (
          <div className="w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center">
            <CheckCircle size={18} />
          </div>
        )}
        <div className="text-left">
          <p className="font-extrabold text-white text-base tracking-tight">
            {message || 'Fact-check in progress'}
          </p>
          <p className="text-xs text-text-dim mt-0.5 font-medium">
            Multi-agent consensus typically takes 30–60 seconds
          </p>
        </div>
      </div>

      {/* Visual Steps Progress Bar */}
      <div className="flex flex-col sm:flex-row gap-6 sm:gap-0 justify-between items-start sm:items-center mb-8 bg-slate-950/40 p-4 sm:p-5 rounded-xl border border-border">
        {STAGES.map((s, i) => {
          const isDone = i < currentIdx
          const isActive = i === currentIdx
          
          return (
            <div key={s.key} className="flex flex-row sm:flex-col items-center gap-3 sm:gap-2 flex-1 w-full last:flex-initial">
              {/* Dot & Icon */}
              <div className="flex items-center gap-3 sm:flex-col sm:gap-2 relative">
                <div 
                  className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-300 ${
                    isDone 
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                      : isActive 
                        ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 shadow-glow'
                        : 'bg-white/[0.02] text-text-muted border border-border'
                  }`}
                  style={isActive ? { boxShadow: `0 0 15px ${s.color}25` } : {}}
                >
                  {s.icon}
                </div>
                
                {/* Visual state dot */}
                <div className={`stage-dot absolute -bottom-1 sm:-bottom-1 sm:left-1/2 sm:-translate-x-1/2 hidden ${isDone ? 'done' : isActive ? 'active' : ''}`} />
              </div>

              {/* Text label */}
              <div className="flex flex-col sm:items-center text-left sm:text-center">
                <span className={`text-xs font-bold ${
                  isDone 
                    ? 'text-emerald-400' 
                    : isActive 
                      ? 'text-indigo-300' 
                      : 'text-text-muted'
                }`}>
                  {s.label}
                </span>
                <span className="text-[10px] text-text-muted hidden sm:inline">
                  {isDone ? 'Finished' : isActive ? 'Active' : 'Pending'}
                </span>
              </div>

              {/* Connection Line */}
              {i < STAGES.length - 1 && (
                <div className="hidden sm:block flex-1 h-[2px] bg-border mx-4 relative min-w-[30px]">
                  <motion.div 
                    className="absolute top-0 left-0 h-full bg-gradient-to-r from-indigo-500 to-purple-500" 
                    initial={{ width: '0%' }}
                    animate={{ width: isDone ? '100%' : '0%' }}
                    transition={{ duration: 0.4 }}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Agent Log Terminal */}
      <div className="text-left">
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-bold text-text-dim uppercase tracking-wider flex items-center gap-1.5">
            <Terminal size={13} className="text-accent" /> Live Agent Execution Feed
          </label>
          <span className="text-[10px] font-mono text-text-muted">stdout // channel-sse</span>
        </div>
        
        <div className="bg-slate-950 border border-border p-4 rounded-xl font-mono text-xs text-text-dim leading-relaxed h-[130px] overflow-y-auto scrollbar">
          <div className="flex flex-col gap-1">
            {logs.map((log, index) => (
              <motion.div 
                key={index}
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }}
                className={log.includes('[system]') ? 'text-indigo-400' : 'text-text-dim'}
              >
                <span className="text-text-muted select-none">[{new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}] </span>
                {log}
              </motion.div>
            ))}
            {/* Pulsing prompt caret if processing */}
            {stage !== 'complete' && (
              <div className="flex items-center gap-1 text-accent mt-1">
                <span>[pipeline] &gt; awaiting consensus...</span>
                <span className="w-1.5 h-3.5 bg-accent animate-pulse" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Skeletons to hint at final layout */}
      {stage !== 'complete' && (
        <div className="mt-8 pt-6 border-t border-border/60">
          <div className="flex justify-between items-center mb-4">
            <div className="h-4 w-32 skeleton" />
            <div className="h-6 w-12 skeleton" />
          </div>
          <div className="space-y-3">
            <div className="h-16 w-full skeleton opacity-40" />
            <div className="h-12 w-full skeleton opacity-20" />
          </div>
        </div>
      )}
    </div>
  )
}
