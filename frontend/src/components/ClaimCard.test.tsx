import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ClaimCard from './ClaimCard'
import type { Claim } from '../context/JobContext'

const claim: Claim = {
  claim_id: 'c1',
  text: 'Unemployment fell to 3.4% in January 2024.',
  claim_type: 'statistic',
  checkability: 'high',
}

describe('ClaimCard', () => {
  it('renders claim text and type badge', () => {
    render(<ClaimCard claim={claim} sources={[]} />)
    expect(screen.getByText(/Unemployment fell to 3.4%/)).toBeInTheDocument()
    expect(screen.getByText(/statistic/i)).toBeInTheDocument()
  })

  it('shows verdict badge when verdict is provided', () => {
    render(
      <ClaimCard
        claim={claim}
        sources={[]}
        verdict={{
          claim_id: 'c1',
          verdict: 'SUPPORTED',
          confidence: 0.91,
          reasoning: 'Confirmed by official data.',
        }}
      />
    )
    expect(screen.getByText(/SUPPORTED/i)).toBeInTheDocument()
  })
})
