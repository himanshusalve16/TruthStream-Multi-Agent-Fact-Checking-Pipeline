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
  const [systemStatus, setSystemStatus] = useState<'checking' | 'sleeping' | 'waking' | 'ready' | 'degraded'>('checking')
  const [statusDetail, setStatusDetail] = useState<string>('Checking AI Service status...')
  const navigate = useNavigate()
  const { dispatch } = useJobContext()

  useEffect(() => {
    let active = true
    let timerId: any = null

    const checkStatus = async () => {
      try {
        const res = await jobs.checkReady()
        if (!active) return
        
        const status = res.data.status
        const details = res.data.details
        
        if (status === 'ready') {
          setSystemStatus('ready')
          setStatusDetail('Ready')
        } else if (status === 'waking') {
          setSystemStatus('waking')
          setStatusDetail(details || 'Initializing Runtime...')
          timerId = setTimeout(checkStatus, 3000)
        } else if (status === 'degraded') {
          setSystemStatus('degraded')
          setStatusDetail(details || 'AI Capacity Limited: Provider Cooling Down. Retry Available Soon.')
          timerId = setTimeout(checkStatus, 3000)
        } else {
          setSystemStatus('sleeping')
          setStatusDetail(details || 'Waking AI Service...')
          timerId = setTimeout(checkStatus, 3000)
        }
      } catch (err: any) {
        if (!active) return
        const responseData = err.response?.data
        if (responseData && responseData.status === 'waking') {
          setSystemStatus('waking')
          setStatusDetail(responseData.details || 'Initializing Runtime...')
        } else if (responseData && responseData.status === 'degraded') {
          setSystemStatus('degraded')
          setStatusDetail(responseData.details || 'AI Capacity Limited: Provider Cooling Down. Retry Available Soon.')
        } else {
          setSystemStatus('sleeping')
          setStatusDetail('Waking AI Service...')
        }
        timerId = setTimeout(checkStatus, 3000)
      }
    }

    checkStatus()

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
      console.error('Submission error:', err);
      if (err.message && (err.message.includes('Backend API URL') || err.message.includes('Invalid backend API base URL'))) {
        setError(err.message);
      } else if (err.response) {
        const status = err.response.status;
        const msg = err.response.data?.message || err.response.data?.error || err.message;
        const endpoint = err.config?.url;
        
        let absoluteUrl = endpoint || '';
        const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
        if (baseUrl && !absoluteUrl.startsWith('http')) {
          const base = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
          const path = absoluteUrl.startsWith('/') ? absoluteUrl : `/${absoluteUrl}`;
          absoluteUrl = `${base}${path}`;
        }

        if (status === 404) {
          setError(`Backend API URL is not configured correctly. Failed to resolve endpoint at: ${absoluteUrl} (Status: 404).`);
        } else if (status >= 500) {
          setError(`500 Backend Error: ${msg} at ${absoluteUrl}`);
        } else {
          setError(`API Error (${status}): ${msg} at ${absoluteUrl}`);
        }
      } else if (err.request) {
        const endpoint = err.config?.url || '';
        let absoluteUrl = endpoint;
        const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
        if (baseUrl && !absoluteUrl.startsWith('http')) {
          const base = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
          const path = absoluteUrl.startsWith('/') ? absoluteUrl : `/${absoluteUrl}`;
          absoluteUrl = `${base}${path}`;
        }
        setError(`Backend API URL is not configured correctly or is unreachable. Failed to connect to: ${absoluteUrl || 'N/A'}`);
      } else {
        setError(`Error: ${err.message}`);
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
      {/* Sliding Pill Tab Switcher */}
      <div className="relative flex p-1.5 bg-slate-950/80 rounded-xl border border-border mb-6">
        {(['url', 'text'] as const).map((t) => {
          const isActive = tab === t
          return (
            <button
              key={t}
              type="button"
              className={`relative flex-1 py-2.5 text-xs sm:text-sm font-bold rounded-lg cursor-pointer flex items-center justify-center gap-2 transition-colors duration-200 z-10 ${
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
              {t === 'url' ? <Link2 size={15} /> : <FileText size={15} />}
              <span>{t === 'url' ? 'Check Article URL' : 'Check Text Passage'}</span>
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

      {/* Display System Status banner when not ready */}
      {systemStatus !== 'ready' && (
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`mt-4 flex items-start gap-2.5 p-3.5 rounded-xl border text-xs sm:text-sm text-left ${
            systemStatus === 'degraded' 
              ? 'border-amber-500/20 bg-amber-500/5 text-amber-300' 
              : 'border-indigo-500/20 bg-indigo-500/5 text-indigo-300'
          }`}
        >
          <div className="flex-shrink-0 mt-0.5">
            {systemStatus === 'degraded' ? (
              <AlertCircle size={16} className="text-amber-400" />
            ) : (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
              </span>
            )}
          </div>
          <div>
            <span className={`font-bold uppercase tracking-wider text-[10px] block mb-0.5 ${
              systemStatus === 'degraded' ? 'text-amber-400' : 'text-white'
            }`}>
              {systemStatus === 'degraded' ? 'AI Capacity Limited' : 'AI Service Status'}
            </span>
            <p className="opacity-90">
              {systemStatus === 'checking' && 'Verifying runtime status...'}
              {systemStatus === 'sleeping' && 'Waking AI Service... (Render free-tier cold start, this may take 15–30 seconds)'}
              {systemStatus === 'waking' && `${statusDetail}...`}
              {systemStatus === 'degraded' && `${statusDetail}`}
            </p>
          </div>
        </motion.div>
      )}

      {/* Submit Button */}
      <button
        id="submit-btn"
        type="submit"
        className="btn-premium-primary w-full mt-6 flex items-center justify-center gap-2 py-3.5 rounded-xl cursor-pointer"
        disabled={loading || (systemStatus !== 'ready' && systemStatus !== 'degraded') || (tab === 'url' ? !url : !text)}
      >
        {systemStatus !== 'ready' && systemStatus !== 'degraded' ? (
          <>
            <span className="premium-loader" />
            <span>
              {systemStatus === 'checking' && 'Checking System Status...'}
              {systemStatus === 'sleeping' && 'Waking AI Service...'}
              {systemStatus === 'waking' && statusDetail}
            </span>
          </>
        ) : loading ? (
          <>
            <span className="premium-loader" />
            <span>Verification Running…</span>
          </>
        ) : systemStatus === 'degraded' ? (
          <>
            <Sparkles size={16} />
            <span>Run Limited Verification</span>
          </>
        ) : (
          <>
            <Sparkles size={16} />
            <span>Analyze Credibility & Bias</span>
          </>
        )}
      </button>
    </form>
  )
}
