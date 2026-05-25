import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { 
  Terminal as TerminalIcon, 
  CheckCircle, 
  Search, 
  Globe, 
  Scale, 
  Cpu
} from 'lucide-react'
import type { Stage } from '../context/JobContext'

const STAGES: { key: Stage; label: string; icon: React.ReactNode; color: string; description: string }[] = [
  { key: 'fetching',          label: 'Parser Node',      icon: <Globe size={15} />, color: '#818cf8', description: 'Downloads & cleans target content' },
  { key: 'parsing_claims',    label: 'Claim Extractor',  icon: <Search size={15} />, color: '#c084fc', description: 'Isolates verifiable claims' },
  { key: 'verifying_sources', label: 'Sourcing Crawler', icon: <TerminalIcon size={15} />, color: '#38bdf8', description: 'Crawls web indices & stance' },
  { key: 'reasoning',         label: 'Veracity Judge',    icon: <Scale size={15} />, color: '#a855f7', description: 'Synthesizes final verdict' },
  { key: 'completed',         label: 'Synthesized Output',icon: <CheckCircle size={15} />, color: '#34d399', description: 'Results published' },
]

const STAGE_ORDER: Stage[] = [
  'queued',
  'accepted',
  'routing',
  'fetching',
  'extracting',
  'parsing_claims',
  'verifying_sources',
  'reasoning',
  'generating_verdict',
  'completed'
]

const stageMapping: Record<Stage, Stage> = {
  idle: 'queued',
  queued: 'queued',
  accepted: 'accepted',
  spawning_agents: 'routing',
  routing: 'routing',
  fetching_article: 'fetching',
  fetching: 'fetching',
  extracting_content: 'extracting',
  extracting: 'extracting',
  extracting_claims: 'parsing_claims',
  parsing_claims: 'parsing_claims',
  sourcing_claims: 'verifying_sources',
  verifying_sources: 'verifying_sources',
  judging: 'reasoning',
  reasoning: 'reasoning',
  finalizing: 'generating_verdict',
  generating_verdict: 'generating_verdict',
  complete: 'completed',
  completed: 'completed',
  partial_completed: 'completed',
  error: 'completed',
  failed: 'completed'
}

const SUBSTAGE_LOGS: Record<Stage, string[]> = {
  queued: [
    'Job registered at orchestrator gateway...',
    'Assigning pipeline thread worker...',
    'Thread initialized. Queue cleared.'
  ],
  accepted: [
    'Job accepted by background worker thread...',
    'Establishing secure execution context...',
    'Worker resources ready.'
  ],
  routing: [
    'Classifying article features...',
    'Determining pipeline route based on heuristics...',
    'Routing to target execution path.'
  ],
  fetching: [
    'Connecting to target web host...',
    'Extracting raw content...',
    'Content fetched successfully.'
  ],
  extracting: [
    'Sanitizing raw HTML input tags...',
    'Cleaned content body parsed successfully.',
    'Checking text length & complexity metrics...'
  ],
  parsing_claims: [
    'Initializing Claim Extractor Agent...',
    'Isolating checkable factual claims...'
  ],
  verifying_sources: [
    'Deploying Search Agent network...',
    'Scraping corroborating source links...'
  ],
  reasoning: [
    'Spawning Bias Analyst Agent...',
    'Cross-referencing stances with veracity judge...'
  ],
  generating_verdict: [
    'Synthesizing consensus matrix...',
    'Persisting overall and individual claim verdicts...',
    'Done.'
  ],
  completed: [
    'Pipeline complete.',
    'Verdicts verified & persisted.'
  ],
  partial_completed: [
    'Pipeline completed with partial analysis.',
    'Certain verification stages skipped or fallback triggered.'
  ],
  failed: [
    'Pipeline terminated with error.'
  ],
  // backward compatibility
  idle: ['Pipeline idle.'],
  spawning_agents: ['Spawning fact-checking agent pool...'],
  fetching_article: ['Fetching target article content...'],
  extracting_content: ['Parsing and cleaning text content...'],
  extracting_claims: ['Analyzing article for claims...'],
  sourcing_claims: ['Finding sources for each claim...'],
  judging: ['Synthesizing final verdict...'],
  finalizing: ['Saving final verdicts...'],
  complete: ['Pipeline complete.'],
  error: ['Pipeline terminated with error.']
}

interface Props {
  stage: Stage
  message?: string
}

export default function LoadingState({ stage, message }: Props) {
  const normalizedStage = stageMapping[stage] || stage
  const currentIdx = STAGE_ORDER.indexOf(normalizedStage)
  const isTerminalState = stage === 'complete' || stage === 'completed' || stage === 'partial_completed' || stage === 'failed' || stage === 'error'

  const [logs, setLogs] = useState<string[]>([])
  const [currentLogIdx, setCurrentLogIdx] = useState(0)
  const [stageTimer, setStageTimer] = useState(0)
  const [totalTimer, setTotalTimer] = useState(0)

  // Reset stage timer on stage transitions
  useEffect(() => {
    setStageTimer(0)
  }, [stage])

  // Count seconds elapsed for live indicators
  useEffect(() => {
    if (isTerminalState || stage === 'idle') return

    const interval = setInterval(() => {
      setStageTimer(prev => prev + 1)
      setTotalTimer(prev => prev + 1)
    }, 1000)

    return () => clearInterval(interval)
  }, [stage, isTerminalState])

  // Append new logs corresponding to the current stage
  useEffect(() => {
    const stageLogs = SUBSTAGE_LOGS[stage] || []
    if (stageLogs.length > 0) {
      setLogs(prev => [...prev, `[sys] > ${stageLogs[0]}`])
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
    }, 1200)

    return () => clearTimeout(timer)
  }, [stage, currentLogIdx])

  const nodes = [
    { name: 'Parser', x: 60,   y: 60, stages: ['fetching', 'extracting'], color: '#818cf8' },
    { name: 'Extractor', x: 200,  y: 60, stages: ['parsing_claims'], color: '#c084fc' },
    { name: 'Crawler', x: 340,  y: 60, stages: ['verifying_sources'],   color: '#38bdf8' },
    { name: 'Judge', x: 480,  y: 60, stages: ['reasoning', 'generating_verdict'], color: '#a855f7' },
    { name: 'Output', x: 620,  y: 60, stages: ['completed'],          color: '#34d399' },
  ]

  // Formats system log tags with color-coding
  const formatLog = (logText: string) => {
    if (logText.startsWith('[sys]')) {
      return (
        <span>
          <span className="text-indigo-400 font-bold">[system]</span> {logText.slice(7)}
        </span>
      )
    }
    if (logText.startsWith('[agent]')) {
      return (
        <span>
          <span className="text-sky-400 font-bold">[agent]</span> {logText.slice(9)}
        </span>
      )
    }
    return logText
  }

  return (
    <div id="loading-state" className="flex flex-col gap-6 w-full">
      {/* Fallback Warning Alert Banner */}
      {message && message.includes('⚠️ Fallback') && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-500/20 bg-amber-500/5 text-amber-300 text-xs font-medium animate-pulse text-left">
          <span className="text-base select-none">⚠️</span>
          <div className="flex-1">
            <p className="font-bold text-amber-200">Active Fallback Protocol</p>
            <p className="opacity-90 mt-0.5">{message}</p>
          </div>
        </div>
      )}

      {/* Dynamic Multi-Agent Orchestration Map */}
      <div className="glass-card p-6 border border-border bg-bg-glass backdrop-blur-xl rounded-2xl shadow-card relative">
        <div className="flex items-center justify-between mb-6">
          <div className="text-left">
            <h3 className="text-xs font-bold text-text-dim uppercase tracking-wider flex items-center gap-1.5">
              <Cpu size={13} className="text-accent animate-spin" style={{ animationDuration: '3s' }} /> Multi-Agent Orchestration Board
            </h3>
            <p className="text-[10px] text-text-muted mt-0.5">Live routing & packet tracking metrics</p>
          </div>
          <div className="flex items-center gap-4 text-[10px] text-text-muted font-mono bg-slate-950/80 px-3 py-1.5 rounded-lg border border-white/[0.04]">
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full bg-emerald-500 ${!isTerminalState ? 'animate-ping' : ''}`} />
              <span>DIAG: {isTerminalState ? 'COMPLETE' : 'ONLINE'}</span>
            </div>
            <div>ELAPSED: {totalTimer}s</div>
          </div>
        </div>

        {/* Scaled Flowchart SVG */}
        <div className="overflow-x-auto scrollbar pb-4 mb-4">
          <svg viewBox="0 0 680 120" className="mx-auto block w-full h-auto min-w-[580px]">
            {/* SVG Glowing Filter */}
            <defs>
              <filter id="agent-active-glow" x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="5" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Connection Lines with Dash offset animations */}
            {nodes.slice(0, -1).map((node, idx) => {
              const nextNode = nodes[idx + 1]
              const maxCurrentNodeStageIdx = Math.max(...node.stages.map(s => STAGE_ORDER.indexOf(s as Stage)))
              const isPassed = currentIdx > maxCurrentNodeStageIdx
              const isActive = node.stages.includes(normalizedStage)
              
              return (
                <path
                  key={`line-${idx}`}
                  d={`M ${node.x + 20} ${node.y} L ${nextNode.x - 20} ${nextNode.y}`}
                  stroke={isPassed ? '#10b981' : isActive ? '#6366f1' : 'rgba(255, 255, 255, 0.05)'}
                  strokeWidth={2}
                  className={isActive ? 'svg-flow-path' : ''}
                  style={{ transition: 'stroke 0.4s ease' }}
                />
              )
            })}

            {/* Agent Nodes rendering */}
            {nodes.map((node) => {
              const stageIdxs = node.stages.map(s => STAGE_ORDER.indexOf(s as Stage))
              const maxStageIdx = Math.max(...stageIdxs)
              const isFinished = currentIdx > maxStageIdx || (isTerminalState && node.stages.includes('completed'))
              const isActive = node.stages.includes(normalizedStage)

              const activeColor = node.color
              
              return (
                <g key={node.name} transform={`translate(${node.x}, ${node.y})`}>
                  {/* Outer Pulsating halo */}
                  {isActive && (
                    <circle
                      r={26}
                      fill="none"
                      stroke={activeColor}
                      strokeWidth={1.5}
                      className="animate-ping opacity-25"
                      style={{ animationDuration: '2s' }}
                    />
                  )}

                  {/* Node Circle */}
                  <circle
                    r={20}
                    fill={isFinished ? '#10b981' : isActive ? activeColor : 'rgba(15, 23, 42, 0.8)'}
                    stroke={isFinished ? '#10b981' : isActive ? '#ffffff' : 'rgba(255, 255, 255, 0.08)'}
                    strokeWidth={isActive ? 2 : 1.5}
                    filter={isActive ? 'url(#agent-active-glow)' : 'none'}
                    style={{ transition: 'fill 0.4s ease, stroke 0.4s ease' }}
                  />

                  {/* Icon */}
                  <g fill="#ffffff" stroke="#ffffff" className="text-white">
                    <foreignObject x="-8" y="-8" width="16" height="16">
                      <div className="text-white flex items-center justify-center">
                        {STAGES.find(s => s.key === node.stages[0])?.icon || <Globe size={15} />}
                      </div>
                    </foreignObject>
                  </g>

                  {/* Label */}
                  <text
                    y={36}
                    textAnchor="middle"
                    fill={isFinished ? '#10b981' : isActive ? '#ffffff' : '#6b7280'}
                    fontSize={10}
                    fontWeight="700"
                    fontFamily="Inter, sans-serif"
                    style={{ transition: 'fill 0.4s ease' }}
                  >
                    {node.name}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>

        {/* Live Diagnostics Metrics Ticker */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/60 p-4 border border-white/[0.03] rounded-xl text-left">
          <div className="flex flex-col">
            <span className="text-[9px] text-text-muted font-bold tracking-wider uppercase">Active Stage</span>
            <span className="text-xs font-bold text-white font-mono flex items-center gap-1.5 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full ${isTerminalState ? 'bg-emerald-500' : 'bg-indigo-500 animate-pulse'}`} />
              <span className="capitalize">{stage.replace('_', ' ')}</span>
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-text-muted font-bold tracking-wider uppercase">Stage Timer</span>
            <span className="text-xs font-bold text-white font-mono mt-0.5">
              {isTerminalState ? '0.0s' : `${stageTimer}s`}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-text-muted font-bold tracking-wider uppercase">Pipeline Engine</span>
            <span className="text-xs font-bold text-indigo-400 font-mono mt-0.5">gemini-2.5-flash-lite</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] text-text-muted font-bold tracking-wider uppercase">Active Claim ID</span>
            <span className="text-xs font-bold text-white font-mono mt-0.5 truncate">
              {isTerminalState ? 'none' : 'claim_idx_0' + (currentIdx + 1)}
            </span>
          </div>
        </div>
      </div>

      {/* Cyber Terminal Console */}
      <div className="text-left w-full">
        <div className="flex items-center justify-between mb-2 px-1">
          <label className="text-[10px] font-bold text-text-dim uppercase tracking-wider flex items-center gap-1.5">
            <TerminalIcon size={12} className="text-accent" /> Agent Consensus Output
          </label>
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-mono text-text-muted">stdout // stream-event</span>
            <div className={`w-2 h-2 rounded-full bg-indigo-500 ${!isTerminalState ? 'animate-pulse' : ''}`} />
          </div>
        </div>
        
        {/* Terminal Box with CRT Scanline Effect */}
        <div className="scanlines bg-slate-950 border border-border p-4 rounded-2xl font-mono text-xs text-text-dim leading-relaxed h-[160px] overflow-y-auto scrollbar shadow-inner relative">
          <div className="flex flex-col gap-1 relative z-20">
            {logs.map((log, index) => (
              <motion.div 
                key={index}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.15 }}
                className="font-medium"
              >
                <span className="text-text-muted/60 select-none">[{new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}] </span>
                {formatLog(log)}
              </motion.div>
            ))}
            
            {/* Blinking block terminal cursor */}
            {!isTerminalState && (
              <div className="flex items-center gap-1 mt-1 font-bold text-accent">
                <span>[pipeline] &gt; {message || 'awaiting consensus...'}</span>
                <span className="terminal-cursor" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modern Shimmering Skeleton Loader */}
      {!isTerminalState && (
        <div className="glass-card p-6 border border-border bg-bg-glass backdrop-blur-xl rounded-2xl shadow-card">
          <div className="flex justify-between items-center mb-4">
            <div className="h-4 w-28 skeleton" />
            <div className="h-6 w-16 skeleton" />
          </div>
          <div className="space-y-3">
            <div className="h-16 w-full skeleton opacity-30" />
            <div className="h-12 w-full skeleton opacity-15" />
          </div>
        </div>
      )}
    </div>
  )
}
