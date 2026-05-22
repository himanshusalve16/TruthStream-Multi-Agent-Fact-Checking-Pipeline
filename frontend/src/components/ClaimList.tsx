import { Claim, ClaimVerdict, Source } from '../context/JobContext'
import ClaimCard from './ClaimCard'

interface Props {
  claims: Claim[]
  claimVerdicts: ClaimVerdict[]
  sourcesByClaim: Record<string, Source[]>
}

export default function ClaimList({ claims, claimVerdicts, sourcesByClaim }: Props) {
  const verdictMap = Object.fromEntries(claimVerdicts.map((v) => [v.claim_id, v]))

  if (claims.length === 0) return null

  return (
    <section id="claims-section">
      <h2 style={{
        fontSize: '1.1rem',
        fontWeight: 700,
        color: 'var(--color-text)',
        marginBottom: '16px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
      }}>
        🔍 Extracted Claims
        <span style={{
          background: 'var(--color-accent)',
          color: '#fff',
          borderRadius: '999px',
          padding: '2px 10px',
          fontSize: '0.78rem',
          fontWeight: 700,
        }}>
          {claims.length}
        </span>
      </h2>

      {claims.map((claim) => (
        <ClaimCard
          key={claim.claim_id}
          claim={claim}
          verdict={verdictMap[claim.claim_id]}
          sources={sourcesByClaim[claim.claim_id] || []}
        />
      ))}
    </section>
  )
}
