import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { 
  History, 
  ArrowLeft, 
  Link2, 
  Calendar, 
  CheckCircle, 
  Clock, 
  XCircle, 
  AlertTriangle 
} from 'lucide-react'
import { jobs, type JobStatus } from '../api/client'

interface JobsListResponse {
  jobs: JobStatus[]
  total: number
  page: number
  page_size: number
}

const STATUS_CONFIG: Record<string, { 
  label: string; 
  icon: React.ReactNode; 
  badgeClass: string; 
}> = {
  PENDING: { label: 'Pending', icon: <Clock size={12} className="animate-pulse" />, badgeClass: 'tag-muted' },
  PROCESSING: { label: 'Processing', icon: <Clock size={12} className="animate-spin" />, badgeClass: 'tag-info shadow-glow' },
  COMPLETE: { label: 'Complete', icon: <CheckCircle size={12} />, badgeClass: 'tag-success' },
  FAILED: { label: 'Failed', icon: <XCircle size={12} />, badgeClass: 'tag-danger' },
  PARTIAL: { label: 'Partial', icon: <AlertTriangle size={12} />, badgeClass: 'tag-warning' },
}

export default function HistoryPage() {
  const [data, setData] = useState<JobsListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    // API is public, fetch jobs immediately
    jobs
      .list(1, 20)
      .then((res) => setData(res.data as JobsListResponse))
      .catch((err: unknown) => {
        const msg =
          (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
          'Failed to load history'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="relative min-h-screen bg-bg text-text overflow-hidden select-none pb-20">
      {/* Background patterns */}
      <div className="grid-bg" />
      <div className="glow-spot -top-[200px] left-[50%] -translate-x-1/2 w-[600px] h-[500px] bg-accent/5 opacity-50 rounded-full" />

      {/* Navigation Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-bg-glass backdrop-blur-md">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-xl font-extrabold tracking-tight group">
            <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-glow">
              ⚡
            </span>
            <span className="bg-gradient-to-r from-white to-text-dim bg-clip-text text-transparent font-bold">
              Truth<span className="text-accent font-black">Stream</span>
            </span>
          </Link>
          <Link 
            to="/" 
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg border border-border bg-white/3 hover:bg-white/6 hover:border-border-hover text-text-dim hover:text-white transition-all duration-200"
          >
            <ArrowLeft size={14} />
            <span>Back to Check</span>
          </Link>
        </div>
      </header>

      {/* Main Panel */}
      <main className="container mx-auto px-6 pt-12 relative z-10 max-w-3xl text-left">
        <div className="flex items-center gap-2.5 mb-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center">
            <History size={16} />
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight text-white leading-none">Pipeline Archive</h1>
            <p className="text-xs text-text-dim mt-1 font-medium">History of submitted analysis jobs</p>
          </div>
        </div>

        {/* Loading Spinner */}
        {loading && (
          <div className="flex items-center gap-3 py-12 justify-center">
            <span className="premium-loader" />
            <span className="text-xs text-text-muted font-bold tracking-wider font-mono">RETRIEVING JOBS LIST...</span>
          </div>
        )}

        {/* Error Notification */}
        {error && (
          <div className="flex items-center gap-2.5 p-4 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 text-xs sm:text-sm mt-6">
            <AlertTriangle size={16} className="flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && (!data || data.jobs.length === 0) && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card p-12 mt-6 text-center border border-border bg-bg-glass backdrop-blur-xl rounded-2xl"
          >
            <History size={40} className="mx-auto text-text-muted mb-4 opacity-50" />
            <p className="text-sm text-text-dim mb-6 font-medium">No fact-check jobs indexed on this client.</p>
            <Link to="/" className="btn-premium-primary inline-flex py-2.5 px-6 rounded-xl text-sm">
              Verify your first claim
            </Link>
          </motion.div>
        )}

        {/* Jobs List Grid */}
        {!loading && data && data.jobs.length > 0 && (
          <motion.ul 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col gap-3 mt-8"
          >
            {data.jobs.map((job) => {
              const status = STATUS_CONFIG[job.status] || STATUS_CONFIG.PENDING
              
              return (
                <motion.li 
                  key={job.job_id}
                  whileHover={{ y: -1 }}
                  transition={{ duration: 0.15 }}
                >
                  <Link
                    to={`/jobs/${job.job_id}`}
                    className="glass-card block p-5 bg-bg-glass backdrop-blur-xl border border-border rounded-xl hover:border-border-hover transition-all duration-300"
                  >
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                      {/* Job Metadata details */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1.5">
                          <Link2 size={13} className="text-text-muted flex-shrink-0" />
                          <p className="font-bold text-white text-sm sm:text-base truncate">
                            {job.input_url || 'Pasted text passage'}
                          </p>
                        </div>
                        
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-text-dim">
                          <span className="font-mono text-[10px] bg-slate-950 px-2 py-0.5 rounded border border-white/[0.04] text-text-muted">
                            ID: {job.job_id.slice(0, 18)}...
                          </span>
                          <span className="flex items-center gap-1.5 text-[10px] text-text-muted font-bold uppercase tracking-wider">
                            <Calendar size={11} />
                            {new Date(job.created_at).toLocaleDateString()} at {new Date(job.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                          </span>
                        </div>
                      </div>

                      {/* Status Tag badge */}
                      <span className={`premium-tag ${status.badgeClass} flex items-center gap-1 py-1 px-3 text-[10px]`}>
                        {status.icon}
                        <span>{status.label}</span>
                      </span>
                    </div>

                    {/* Display Job Error Message if any */}
                    {job.error_message && (
                      <div className="mt-3 flex items-start gap-1.5 text-xs text-red-400 bg-red-500/5 p-2 rounded-lg border border-red-500/10">
                        <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
                        <span>{job.error_message}</span>
                      </div>
                    )}
                  </Link>
                </motion.li>
              )
            })}
          </motion.ul>
        )}
      </main>
    </div>
  )
}
