import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Link2, FileText, Sparkles, AlertCircle } from 'lucide-react'
import { jobs } from '../api/client'
import { useJobContext } from '../context/JobContext'

export default function InputForm() {
  const [tab, setTab] = useState<'url' | 'text'>('url')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // 'unknown' on first load prevents a flash of "Warming Up" before the
  // first health check resolves. The badge renders nothing meaningful until
  // we have a real answer.
  const [systemStatus, setSystemStatus] = useState<'online' | 'warming_up' | 'capacity_limited' | 'unknown'>('unknown')
  const navigate = useNavigate()
  const { dispatch } = useJobContext()

  useEffect(() => {
    let active = true
    let timerId: ReturnType<typeof setTimeout> | null = null

    /**
     * Attempt one health check with up to `maxRetries` retries.
     *
     * Retry strategy: exponential backoff starting at 1 s.
     * - Handles Render free-tier wake-up latency (typically 3–8 s).
     * - Covers transient network blips without immediately showing
     *   "Warming Up" to the user.
     *
     * Success path  → HTTP 200 from /api/health → ONLINE
     * Degraded path → HTTP 200 with status=degraded → CAPACITY_LIMITED
     * Fail path     → all retries exhausted → WARMING_UP
     */
    const checkWithRetry = async (attempt = 0, maxRetries = 3): Promise<void> => {
      try {
        const res = await jobs.checkHealth()
        if (!active) return
        if (res.data.status === 'ok') {
          setSystemStatus('online')
        } else if (res.data.status === 'degraded') {
          setSystemStatus('capacity_limited')
        } else {
          setSystemStatus('warming_up')
        }
      } catch {
        if (!active) return
        if (attempt < maxRetries) {
          // Exponential backoff: 1 s, 2 s, 4 s
          const delay = 1000 * Math.pow(2, attempt)
          await new Promise(resolve => setTimeout(resolve, delay))
          if (!active) return
          return checkWithRetry(attempt + 1, maxRetries)
        }
        // All retries exhausted — gateway is truly unreachable.
        setSystemStatus('warming_up')
      }
    }

    const scheduledCheck = async () => {
      await checkWithRetry()
      if (active) {
        timerId = setTimeout(scheduledCheck, 30000)
      }
    }

    scheduledCheck()

    return () => {
      active = false
      if (timerId) clearTimeout(timerId)
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      dispatch({ type: 'RESET' })
      const res = await jobs.submit({
        input_type: tab,
        url: tab === 'url' ? url : undefined,
        text: tab === 'text' ? text : undefined,
      })
      const jobId = res.data.job_id
      dispatch({ type: 'SET_JOB_ID', jobId })
      navigate(`/jobs/${jobId}`)
    } catch (err: any) {
      console.error('Submission error:', err)

      const resolveUrl = (configUrl?: string) => {
        const raw = configUrl || ''
        if (raw.startsWith('http')) return raw
        const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
        return base + (raw.startsWith('/') ? raw : `/${raw}`)
      }

      if (err.response) {
        const status = err.response.status as number
        const msg = err.response.data?.message || err.response.data?.error || err.message
        const url = resolveUrl(err.config?.url)
        if (status === 404) {
          setError(`Endpoint not found (404): ${url}. Check that VITE_API_BASE_URL is correct.`)
        } else if (status >= 500) {
          setError(`Server error (${status}): ${msg}`)
        } else {
          setError(`Request failed (${status}): ${msg}`)
        }
      } else if (err.request) {
        const url = resolveUrl(err.config?.url)
        setError(`Cannot reach backend at ${url || 'the configured URL'}. The service may still be starting — please try again in a moment.`)
      } else {
        setError(`Unexpected error: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <form 
      id="fact-check-form" 
      onSubmit={handleSubmit} 
      className="glass-card p-8 border border-border bg-bg-glass backdrop-blur-xl rounded-2xl shadow-card"
    >
      {/* Form Header with Passive Status Pill */}
      <div className="flex items-center justify-between mb-6 border-b border-white/[0.04] pb-4">
        <span className="text-[10px] sm:text-xs font-bold text-text-dim uppercase tracking-widest">
          Fact-Check Analyzer
        </span>
        
        {/* Passive Status Indicator */}
        <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] sm:text-xs font-semibold border transition-colors duration-300 ${
          systemStatus === 'online'
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            : systemStatus === 'capacity_limited'
            ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
            : systemStatus === 'warming_up'
            ? 'bg-slate-500/10 text-text-dim border-slate-500/20'
            : 'bg-transparent border-transparent' // 'unknown' — render nothing visible
        }`}>
          {systemStatus !== 'unknown' && (
            <>
              <span className="relative flex h-2 w-2">
                {systemStatus === 'warming_up' && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-slate-400 opacity-75"></span>
                )}
                <span className={`relative inline-flex rounded-full h-2 w-2 ${
                  systemStatus === 'online'
                    ? 'bg-emerald-500'
                    : systemStatus === 'capacity_limited'
                    ? 'bg-amber-500'
                    : 'bg-slate-500'
                }`} />
              </span>
              <span>
                {systemStatus === 'online' && 'AI Service Online'}
                {systemStatus === 'capacity_limited' && 'AI Capacity Limited'}
                {systemStatus === 'warming_up' && 'Warming Up'}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Sliding Pill Tab Switcher */}
      <div className="relative flex p-1.5 bg-slate-950/80 rounded-xl border border-border mb-6">
        {(['url', 'text'] as const).map((t) => {
          const isActive = tab === t
          return (
            <button
              key={t}
              type="button"
              className={`relative flex-1 py-2 sm:py-2.5 text-[11px] sm:text-sm font-bold rounded-lg cursor-pointer flex items-center justify-center gap-1.5 sm:gap-2 transition-colors duration-200 z-10 px-1 ${
                isActive ? 'text-white' : 'text-text-dim hover:text-white'
              }`}
              onClick={() => {
                setError('')
                setTab(t)
              }}
            >
              {isActive && (
                <motion.div
                  layoutId="activeTab"
                  className="absolute inset-0 bg-gradient-to-r from-indigo-600/80 to-purple-600/80 border border-white/10 rounded-lg -z-10 shadow-glow"
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                />
              )}
              {t === 'url' ? <Link2 size={14} className="flex-shrink-0 sm:w-[15px] sm:h-[15px]" /> : <FileText size={14} className="flex-shrink-0 sm:w-[15px] sm:h-[15px]" />}
              <span className="truncate">{t === 'url' ? 'Check Article URL' : 'Check Text Passage'}</span>
            </button>
          )
        })}
      </div>

      {/* Input Fields with Transition */}
      <div className="min-h-[120px] flex flex-col justify-center">
        <AnimatePresence mode="wait">
          {tab === 'url' ? (
            <motion.div
              key="url-tab"
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.15 }}
            >
              <label className="block text-xs font-bold text-text-dim uppercase tracking-wider mb-2 text-left">
                Enter Web Address
              </label>
              <div className="relative">
                <input
                  id="url-input"
                  type="url"
                  className="glass-input pr-10 focus:ring-2 focus:ring-accent/20"
                  placeholder="https://example.com/news-article-url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  required
                  autoFocus
                />
                <div className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted">
                  <Link2 size={16} />
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="text-tab"
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.15 }}
              className="w-full"
            >
              <label className="block text-xs font-bold text-text-dim uppercase tracking-wider mb-2 text-left">
                Paste Article or Quote Text
              </label>
              <textarea
                id="text-input"
                className="glass-input min-h-[140px] resize-none focus:ring-2 focus:ring-accent/20"
                placeholder="Paste paragraph, editorial, or statement to cross-check..."
                value={text}
                onChange={(e) => setText(e.target.value)}
                required
                rows={5}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Display Error Message */}
      {error && (
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mt-4 flex items-start gap-2.5 p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-red-400 text-xs sm:text-sm text-left"
        >
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <div>
            <span className="font-bold">Fact-check failed:</span> {error}
          </div>
        </motion.div>
      )}

      {/* Submit Button */}
      <button
        id="submit-btn"
        type="submit"
        className="btn-premium-primary w-full mt-6 flex items-center justify-center gap-2 py-3.5 rounded-xl cursor-pointer"
        disabled={loading || (tab === 'url' ? !url : !text)}
      >
        {loading ? (
          <>
            <span className="premium-loader" />
            <span>
              {systemStatus === 'warming_up'
                ? 'Waking AI Service…'
                : 'Verification Running…'}
            </span>
          </>
        ) : (
          <>
            <Sparkles size={16} />
            <span>Analyze Credibility &amp; Bias</span>
          </>
        )}
      </button>
    </form>
  )
}
