import { motion } from 'framer-motion'
import type { Variants } from 'framer-motion'
import { CheckSquare } from 'lucide-react'
import type { Claim, ClaimVerdict, Source } from '../context/JobContext'
import ClaimCard from './ClaimCard'

interface Props {
  claims: Claim[]
  claimVerdicts: ClaimVerdict[]
  sourcesByClaim: Record<string, Source[]>
}

export default function ClaimList({ claims, claimVerdicts, sourcesByClaim }: Props) {
  const verdictMap = Object.fromEntries(claimVerdicts.map((v) => [v.claim_id, v]))

  if (claims.length === 0) return null

  // Framer Motion Stagger Config
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.12,
      }
    }
  }

  const cardItemVariants: Variants = {
    hidden: { opacity: 0, y: 15 },
    show: { 
      opacity: 1, 
      y: 0, 
      transition: { type: "spring", stiffness: 100, damping: 15 } 
    }
  }

  const count = claims.length
  const headerLabel = count <= 5 ? `Top ${count} Verified Claims` : `Top 5 Verified Claims`

  return (
    <section id="claims-section" className="text-left">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-bold text-text-dim uppercase tracking-wider flex items-center gap-1.5">
          <CheckSquare size={13} className="text-accent" /> {headerLabel}
        </h3>
      </div>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="flex flex-col gap-4"
      >
        {claims.map((claim, index) => (
          <motion.div key={claim.claim_id} variants={cardItemVariants}>
            <ClaimCard
              claim={claim}
              verdict={verdictMap[claim.claim_id]}
              sources={sourcesByClaim[claim.claim_id] || []}
              index={index}
            />
          </motion.div>
        ))}
      </motion.div>
    </section>
  )
}
