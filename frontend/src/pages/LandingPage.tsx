import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { Variants } from 'framer-motion'
import { 
  Sparkles, 
  Search, 
  Globe, 
  Scale, 
  ShieldAlert, 
  TrendingUp, 
  Activity 
} from 'lucide-react'
import InputForm from '../components/InputForm'
import TutorialCard from '../components/TutorialCard'

export default function LandingPage() {
  // Stagger animation container
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.05,
      }
    }
  }

  const itemVariants: Variants = {
    hidden: { opacity: 0, y: 20 },
    show: { 
      opacity: 1, 
      y: 0, 
      transition: { type: "spring", stiffness: 100, damping: 15 } 
    }
  }

  return (
    <div className="relative min-h-screen bg-bg text-text overflow-hidden select-none">
      {/* Dynamic Background Effects */}
      <div className="grid-bg" />
      <div className="glow-spot -top-[100px] left-[15%] w-[500px] h-[500px] bg-accent/8 opacity-60 rounded-full" />
      <div className="glow-spot top-[20%] right-[10%] w-[600px] h-[600px] bg-purple-500/5 opacity-50 rounded-full" />

      {/* Modern Sticky Navigation */}
      <header className="sticky top-0 z-50 w-full border-b border-white/[0.04] bg-bg-glass backdrop-blur-md shadow-[0_4px_30px_rgba(0,0,0,0.4),0_1px_3px_rgba(99,102,241,0.05)] transition-all duration-300">
        <div className="container mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-1.5 text-xl font-extrabold tracking-tight group">
            <span className="bg-gradient-to-r from-white to-text-dim bg-clip-text text-transparent font-black">
              Truth<span className="bg-gradient-to-r from-indigo-400 to-purple-500 bg-clip-text text-transparent">Stream</span>
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 shadow-glow" />
          </Link>
          <nav className="flex items-center gap-4">
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <main className="container mx-auto px-6 pt-16 pb-24 relative z-10 max-w-5xl text-center">
        <motion.div 
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="flex flex-col items-center"
        >
          {/* Animated Tech Chip */}
          <motion.div 
            variants={itemVariants}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent/20 bg-accent/8 text-accent text-xs font-semibold tracking-wide uppercase mb-8 shadow-glow/10"
          >
            <Sparkles size={13} className="animate-pulse" />
            <span>AI Agentic Pipeline v2.5 Live</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping ml-1" />
          </motion.div>

          {/* Premium Headline */}
          <motion.h1 
            variants={itemVariants}
            className="text-4xl sm:text-6xl font-black tracking-tight leading-tight max-w-3xl mb-6"
          >
            Real-time AI{' '}
            <span className="gradient-text font-black">Fact-Checking</span>
            <br />
            & Veracity Pipeline
          </motion.h1>

          {/* Subtitle */}
          <motion.p 
            variants={itemVariants}
            className="text-base sm:text-lg text-text-dim leading-relaxed max-w-xl mb-10 font-medium"
          >
            Submit any article URL or text passage. Our multi-agent network isolates claims, corroborates sources, scores media bias, and streams live verdicts as it runs.
          </motion.p>

          {/* Fact Check Input & Walkthrough Grid */}
          <motion.div 
            variants={itemVariants}
            className="w-full grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-8 mb-16 items-stretch text-left"
          >
            <div className="lg:col-span-7 relative flex flex-col justify-center">
              <div className="absolute -inset-1.5 rounded-2xl bg-gradient-to-r from-accent to-purple-500 opacity-20 blur-xl group-focus-within:opacity-40 transition duration-1000 pointer-events-none" />
              <InputForm />
            </div>
            
            <div className="lg:col-span-5 flex">
              <TutorialCard />
            </div>
          </motion.div>

          {/* Live Activity Ticker / Stats */}
          <motion.div 
            variants={itemVariants}
            className="grid grid-cols-2 md:grid-cols-3 gap-4 w-full max-w-3xl mb-20 text-left border-y border-border py-6 px-4 bg-white/[0.01] backdrop-blur-sm rounded-xl"
          >
            <div className="flex flex-col gap-1">
              <span className="text-xs text-text-muted font-semibold uppercase tracking-wider flex items-center gap-1.5">
                <Activity size={12} className="text-accent" /> Pipeline Load
              </span>
              <span className="text-lg font-bold text-white font-mono flex items-center gap-2">
                Optimal <span className="text-xs text-emerald-500 font-semibold bg-emerald-500/10 px-2 py-0.5 rounded-md border border-emerald-500/20">99.8%</span>
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-text-muted font-semibold uppercase tracking-wider flex items-center gap-1.5">
                <Globe size={12} className="text-purple-400" /> Trusted Databases
              </span>
              <span className="text-lg font-bold text-white font-mono">140+ Sources</span>
            </div>
            <div className="flex flex-col gap-1 col-span-2 md:col-span-1">
              <span className="text-xs text-text-muted font-semibold uppercase tracking-wider flex items-center gap-1.5">
                <TrendingUp size={12} className="text-indigo-400" /> Avg processing time
              </span>
              <span className="text-lg font-bold text-white font-mono">35 seconds</span>
            </div>
          </motion.div>

          {/* Features Grid */}
          <motion.div 
            variants={itemVariants}
            className="w-full"
          >
            <h2 className="text-2xl font-bold tracking-tight text-white mb-8 text-center flex items-center justify-center gap-2">
              <span>Coordinated Multi-Agent Architecture</span>
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-left max-w-4xl mx-auto">
              {[
                { 
                  icon: <Search size={22} className="text-accent" />, 
                  title: 'Claim Isolation', 
                  desc: 'NLP agents automatically extract checkable assertions, filter noise, and index factual points.' 
                },
                { 
                  icon: <Globe size={22} className="text-purple-400" />, 
                  title: 'Search & Corroboration', 
                  desc: 'Search agents query cross-referenced indexes, academic archives, and reputable media outlets.' 
                },
                { 
                  icon: <Scale size={22} className="text-emerald-400" />, 
                  title: 'Bias & Tone Assessment', 
                  desc: 'Monitors emotional framing, loaded wording, and systematic bias structures across the context.' 
                },
                { 
                  icon: <ShieldAlert size={22} className="text-rose-400" />, 
                  title: 'Synthesized Judge Agent', 
                  desc: 'Cross-verifies credibility weight, resolves conflicting stance claims, and reaches a final confidence score.' 
                },
              ].map((f) => (
                <div 
                  key={f.title} 
                  className="glass-card p-6 flex gap-4 hover:border-border-hover hover:shadow-glow/10 hover:-translate-y-0.5 transition-all duration-300"
                >
                  <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-white/[0.03] border border-border flex-shrink-0">
                    {f.icon}
                  </div>
                  <div>
                    <h3 className="font-bold text-white text-base mb-1.5 flex items-center gap-1.5">
                      {f.title}
                    </h3>
                    <p className="text-sm text-text-dim leading-relaxed">{f.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      </main>

      {/* Elegant Footer */}
      <footer className="w-full border-t border-border/60 py-8 mt-12 bg-bg-glass backdrop-blur-sm relative z-10 text-center">
        <p className="text-xs text-text-muted">
          &copy; {new Date().getFullYear()} TruthStream AI Platform. Developed for premium production fact-checking.
        </p>
      </footer>
    </div>
  )
}
