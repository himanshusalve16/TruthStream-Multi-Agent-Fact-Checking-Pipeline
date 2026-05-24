import { useState } from 'react'
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
  const navigate = useNavigate()
  const { dispatch } = useJobContext()

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
      if (err.response) {
        const status = err.response.status;
        const msg = err.response.data?.message || err.response.data?.error || err.message;
        const endpoint = err.config?.url;
        if (status === 404) {
          let absoluteUrl = endpoint || '';
          const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
          if (baseUrl && !absoluteUrl.startsWith('http')) {
            const base = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
            const path = absoluteUrl.startsWith('/') ? absoluteUrl : `/${absoluteUrl}`;
            absoluteUrl = `${base}${path}`;
          } else if (!absoluteUrl.startsWith('http')) {
            absoluteUrl = `${window.location.origin}${absoluteUrl.startsWith('/') ? absoluteUrl : `/${absoluteUrl}`}`;
          }
          setError(`Backend endpoint not found. Check API base URL and route path. Failed to connect to: ${absoluteUrl}`);
        } else if (status >= 500) {
          setError(`500 Backend Error: ${msg} at ${endpoint}`);
        } else {
          setError(`API Error (${status}): ${msg}`);
        }
      } else if (err.request) {
        setError('Network Error or CORS failure. Backend is unreachable.');
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
            <span>Spawning Fact-Check Agents…</span>
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
