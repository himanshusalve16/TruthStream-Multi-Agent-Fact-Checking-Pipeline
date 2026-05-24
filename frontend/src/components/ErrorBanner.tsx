import { AlertCircle } from 'lucide-react'

interface Props {
  message: string
  onRetry?: () => void
}

export default function ErrorBanner({ message, onRetry }: Props) {
  return (
    <div
      id="error-banner"
      className="glass-card p-5 border border-red-500/20 bg-red-500/5 text-left flex items-start gap-4 rounded-xl shadow-card"
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
        <AlertCircle size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="font-bold text-white text-sm">Pipeline Execution Fault</h4>
        <p className="text-xs sm:text-sm text-text-dim mt-1 leading-relaxed">
          {message}
        </p>
      </div>
      {onRetry && (
        <button 
          className="btn-premium-secondary py-1.5 px-4 text-xs flex-shrink-0" 
          onClick={onRetry}
        >
          New Analysis
        </button>
      )}
    </div>
  )
}
