import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Copy, 
  Link2, 
  Cpu, 
  ShieldAlert, 
  CheckCircle2, 
  ChevronRight,
  Clipboard,
  Terminal,
  MousePointerClick
} from 'lucide-react'

interface Step {
  title: string
  desc: string
  icon: React.ReactNode
}

export default function TutorialCard() {
  const [currentStep, setCurrentStep] = useState(0)
  const [isCopied, setIsCopied] = useState(false)

  const steps: Step[] = [
    {
      title: 'Copy Article Link',
      desc: 'Grab the URL of any news story from your browser address bar.',
      icon: <Copy size={16} />
    },
    {
      title: 'Paste & Trigger',
      desc: 'Paste it in the URL input and click "Analyze Credibility".',
      icon: <Link2 size={16} />
    },
    {
      title: 'Agent Processing',
      desc: 'Watch the agentic network isolate claims & cross-reference sources.',
      icon: <Cpu size={16} />
    },
    {
      title: 'Stream Verdicts',
      desc: 'Explore real-time corroborations and credibility weights.',
      icon: <CheckCircle2 size={16} />
    }
  ]

  // Autoplay steps
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentStep((prev) => (prev + 1) % steps.length)
    }, 4500)
    return () => clearInterval(interval)
  }, [])

  // Trigger copied state animation on step 0
  useEffect(() => {
    if (currentStep === 0) {
      setIsCopied(false)
      const timer = setTimeout(() => setIsCopied(true), 1500)
      return () => clearTimeout(timer)
    } else {
      setIsCopied(false)
    }
  }, [currentStep])

  return (
    <div className="glass-card border border-border bg-bg-glass backdrop-blur-xl rounded-2xl p-6 sm:p-8 flex flex-col justify-between h-full shadow-card relative overflow-hidden select-none">
      {/* Background ambient glow inside card */}
      <div className="absolute -right-16 -top-16 w-32 h-32 bg-accent/10 rounded-full blur-2xl pointer-events-none" />
      <div className="absolute -left-16 -bottom-16 w-32 h-32 bg-purple-500/10 rounded-full blur-2xl pointer-events-none" />

      <div>
        {/* Header */}
        <div className="flex items-center gap-2 mb-5 pb-3 border-b border-white/[0.04]">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-accent/10 border border-accent/20 text-accent">
            <Terminal size={14} className="animate-pulse" />
          </div>
          <span className="text-xs font-bold text-text uppercase tracking-widest">
            Pipeline Walkthrough
          </span>
        </div>

        {/* Step Indicators */}
        <div className="grid grid-cols-4 gap-2 mb-6">
          {steps.map((step, idx) => {
            const isActive = currentStep === idx
            return (
              <button
                key={idx}
                onClick={() => setCurrentStep(idx)}
                className={`h-1.5 rounded-full transition-all duration-300 relative cursor-pointer ${
                  isActive 
                    ? 'bg-gradient-to-r from-accent to-purple-500 shadow-glow' 
                    : 'bg-white/[0.08] hover:bg-white/[0.15]'
                }`}
                title={step.title}
              />
            )
          })}
        </div>

        {/* Interactive Interactive Animation Canvas */}
        <div className="relative w-full h-[140px] rounded-xl bg-slate-950/70 border border-border/80 flex items-center justify-center overflow-hidden mb-6 p-4">
          <div className="absolute inset-0 bg-grid-white/[0.02] pointer-events-none" />
          
          <AnimatePresence mode="wait">
            {currentStep === 0 && (
              <motion.div
                key="step-0"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="w-full flex flex-col items-center gap-3"
              >
                {/* Simulated Browser Address Bar */}
                <div className="w-full max-w-xs bg-slate-900 border border-white/[0.06] rounded-lg p-2 flex items-center justify-between shadow-lg relative">
                  <div className="flex items-center gap-2 overflow-hidden w-[75%]">
                    <div className="flex gap-1 flex-shrink-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500/60" />
                      <span className="w-1.5 h-1.5 rounded-full bg-yellow-500/60" />
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500/60" />
                    </div>
                    <div className="text-[10px] text-text-dim truncate font-mono bg-black/40 px-2 py-0.5 rounded border border-white/[0.03]">
                      https://news.com/agent-report
                    </div>
                  </div>
                  
                  {/* Copy button state */}
                  <motion.div 
                    animate={{ scale: isCopied ? [1, 1.2, 1] : 1 }}
                    className={`flex items-center gap-1 text-[9px] font-bold px-2 py-0.5 rounded border ${
                      isCopied 
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                        : 'bg-white/[0.04] text-text-dim border-white/[0.08]'
                    }`}
                  >
                    {isCopied ? <CheckCircle2 size={9} /> : <Clipboard size={9} />}
                    <span>{isCopied ? 'Copied' : 'Copy'}</span>
                  </motion.div>
                </div>
                
                {/* Hand/Cursor element */}
                <motion.div 
                  initial={{ x: 60, y: 30, opacity: 0 }}
                  animate={{ 
                    x: [60, 110, 110], 
                    y: [30, 0, 0], 
                    opacity: [0, 1, 1, 0] 
                  }}
                  transition={{ duration: 2, times: [0, 0.5, 0.8, 1], repeat: Infinity, repeatDelay: 1 }}
                  className="absolute text-accent pointer-events-none"
                >
                  <MousePointerClick size={18} className="drop-shadow-[0_2px_8px_rgba(99,102,241,0.5)]" />
                </motion.div>

                <span className="text-[11px] text-text-muted font-medium">Step 1: Copy news URL</span>
              </motion.div>
            )}

            {currentStep === 1 && (
              <motion.div
                key="step-1"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="w-full flex flex-col items-center gap-3"
              >
                {/* Simulated Input field & Submit */}
                <div className="w-full max-w-xs flex flex-col gap-2">
                  <div className="bg-slate-900 border border-accent/20 rounded-lg p-2 text-[10px] text-white truncate font-mono shadow-inner">
                    <motion.span
                      initial={{ width: 0 }}
                      animate={{ width: "auto" }}
                      transition={{ duration: 1.5 }}
                      className="inline-block overflow-hidden whitespace-nowrap border-r border-accent/80 pr-1 animate-pulse"
                    >
                      https://news.com/agent-report
                    </motion.span>
                  </div>
                  
                  <motion.div 
                    animate={{ scale: [1, 0.96, 1] }}
                    transition={{ delay: 2, duration: 0.2 }}
                    className="w-full bg-gradient-to-r from-accent to-purple-500 text-[10px] font-bold text-center py-1.5 rounded-lg text-white shadow-md border border-white/10"
                  >
                    Analyze Credibility
                  </motion.div>
                </div>

                <span className="text-[11px] text-text-muted font-medium">Step 2: Paste and run analysis</span>
              </motion.div>
            )}

            {currentStep === 2 && (
              <motion.div
                key="step-2"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="w-full flex flex-col items-center justify-center"
              >
                {/* Agent Network Nodes animation */}
                <div className="flex items-center gap-3 relative z-10">
                  <motion.div 
                    animate={{ 
                      borderColor: ["rgba(99,102,241,0.2)", "rgba(99,102,241,1)", "rgba(99,102,241,0.2)"],
                      backgroundColor: ["rgba(99,102,241,0.02)", "rgba(99,102,241,0.15)", "rgba(99,102,241,0.02)"]
                    }}
                    transition={{ duration: 1.5, repeat: Infinity, repeatDelay: 0.5 }}
                    className="w-10 h-10 rounded-xl border flex flex-col items-center justify-center text-accent"
                  >
                    <span className="text-[8px] font-bold">Claim</span>
                  </motion.div>

                  <ChevronRight size={10} className="text-text-muted" />

                  <motion.div 
                    animate={{ 
                      borderColor: ["rgba(139,92,246,0.2)", "rgba(139,92,246,1)", "rgba(139,92,246,0.2)"],
                      backgroundColor: ["rgba(139,92,246,0.02)", "rgba(139,92,246,0.15)", "rgba(139,92,246,0.02)"]
                    }}
                    transition={{ duration: 1.5, delay: 0.6, repeat: Infinity, repeatDelay: 0.5 }}
                    className="w-10 h-10 rounded-xl border flex flex-col items-center justify-center text-purple-400"
                  >
                    <span className="text-[8px] font-bold">Search</span>
                  </motion.div>

                  <ChevronRight size={10} className="text-text-muted" />

                  <motion.div 
                    animate={{ 
                      borderColor: ["rgba(16,185,129,0.2)", "rgba(16,185,129,1)", "rgba(16,185,129,0.2)"],
                      backgroundColor: ["rgba(16,185,129,0.02)", "rgba(16,185,129,0.15)", "rgba(16,185,129,0.02)"]
                    }}
                    transition={{ duration: 1.5, delay: 1.2, repeat: Infinity, repeatDelay: 0.5 }}
                    className="w-10 h-10 rounded-xl border flex flex-col items-center justify-center text-emerald-400"
                  >
                    <span className="text-[8px] font-bold">Judge</span>
                  </motion.div>
                </div>

                {/* Flow SVG line */}
                <div className="absolute top-[48px] w-[140px] h-[2px] overflow-hidden pointer-events-none">
                  <div className="w-full h-full bg-gradient-to-r from-accent via-purple-500 to-emerald-500 opacity-20" />
                </div>

                <span className="text-[11px] text-text-muted font-medium mt-4">Step 3: Multi-agent coordination</span>
              </motion.div>
            )}

            {currentStep === 3 && (
              <motion.div
                key="step-3"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="w-full flex flex-col items-center gap-2"
              >
                {/* Result report card */}
                <div className="w-full max-w-xs bg-slate-900 border border-emerald-500/20 rounded-lg p-2.5 flex flex-col gap-1.5 shadow-lg">
                  <div className="flex items-center justify-between border-b border-white/[0.04] pb-1.5">
                    <span className="text-[8px] font-bold text-text-dim uppercase tracking-wider">Credibility Report</span>
                    <span className="px-1.5 py-0.5 rounded-full text-[8px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      94% Match
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-text-muted">Final Verdict:</span>
                    <span className="font-extrabold text-emerald-400">SUPPORTED</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px]">
                    <span className="text-text-muted">Bias Rating:</span>
                    <span className="font-bold text-indigo-400">NEUTRAL</span>
                  </div>
                </div>

                <span className="text-[11px] text-text-muted font-medium">Step 4: Live verdict report generated</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Textual Description of current active step */}
        <div className="min-h-[60px] mb-6">
          <h4 className="text-sm font-bold text-white mb-1 flex items-center gap-1.5">
            <span className="text-accent">{steps[currentStep].icon}</span>
            <span>{steps[currentStep].title}</span>
          </h4>
          <p className="text-xs text-text-dim leading-relaxed">
            {steps[currentStep].desc}
          </p>
        </div>
      </div>

      {/* Premium Alert Warning for Firewalls & Paywalls */}
      <div className="border border-amber-500/15 bg-amber-500/5 rounded-xl p-3.5 flex gap-2.5 items-start">
        <ShieldAlert size={16} className="text-amber-500 mt-0.5 flex-shrink-0" />
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-bold text-amber-400 uppercase tracking-wider">
            Important Notice
          </span>
          <p className="text-[10.5px] text-text-dim leading-relaxed">
            Some news sites employ strict anti-scraper firewalls (e.g. Cloudflare) or paywalls that block automated agents.
          </p>
          <p className="text-[10px] text-text-muted font-medium mt-1">
            💡 If a URL times out, copy the article text and use the <span className="text-indigo-300 font-semibold">Check Text Passage</span> tab!
          </p>
        </div>
      </div>
    </div>
  )
}
