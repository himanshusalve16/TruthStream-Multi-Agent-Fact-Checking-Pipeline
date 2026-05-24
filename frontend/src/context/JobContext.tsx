import React, { createContext, useContext, useReducer } from 'react'
import type { ReactNode } from 'react'

// ── Types ──────────────────────────────────────────────────────
export interface Claim {
  claim_id: string
  text: string
  claim_type?: string
  checkability?: string
}

export interface Source {
  source_id: string
  url: string
  title?: string
  domain?: string
  snippet?: string
  stance?: 'SUPPORTS' | 'REFUTES' | 'NEUTRAL' | 'UNCLEAR'
  quality_score?: number
  fetch_status?: string
}

export interface ClaimVerdict {
  claim_id: string
  verdict: 'SUPPORTED' | 'REFUTED' | 'CONTESTED' | 'UNVERIFIABLE'
  confidence: number
  reasoning: string
}

export interface FramingFlag {
  type: string
  description?: string
  examples?: string[]
  severity?: string
}

export interface BiasData {
  bias_score: number
  bias_direction: string
  framing_flags: FramingFlag[]
  loaded_terms: string[]
  summary: string
}

export interface VerdictData {
  overall_verdict: string
  overall_confidence: number
  overall_summary: string
  claim_verdicts: ClaimVerdict[]
}

export type Stage =
  | 'idle'
  | 'fetching_article'
  | 'extracting_claims'
  | 'sourcing_claims'
  | 'judging'
  | 'complete'
  | 'error'

export interface JobState {
  jobId: string | null
  stage: Stage
  stageMessage: string
  claims: Claim[]
  sourcesByClaim: Record<string, Source[]>
  bias: BiasData | null
  verdict: VerdictData | null
  error: string | null
}

// ── Actions ────────────────────────────────────────────────────
type Action =
  | { type: 'SET_JOB_ID'; jobId: string }
  | { type: 'SET_STAGE'; stage: Stage; message?: string }
  | { type: 'ADD_CLAIMS'; claims: Claim[] }
  | { type: 'ADD_SOURCES'; claim_id: string; sources: Source[] }
  | { type: 'SET_BIAS'; bias: BiasData }
  | { type: 'SET_VERDICT'; verdict: VerdictData }
  | { type: 'SET_ERROR'; error: string }
  | { type: 'HYDRATE'; payload: HydratePayload }
  | { type: 'RESET' }

export interface HydratePayload {
  claims: Claim[]
  sourcesByClaim: Record<string, Source[]>
  bias: BiasData | null
  verdict: VerdictData | null
  stage?: Stage
}

const initialState: JobState = {
  jobId: null,
  stage: 'idle',
  stageMessage: '',
  claims: [],
  sourcesByClaim: {},
  bias: null,
  verdict: null,
  error: null,
}

function reducer(state: JobState, action: Action): JobState {
  switch (action.type) {
    case 'SET_JOB_ID':
      return { ...state, jobId: action.jobId }
    case 'SET_STAGE':
      return { ...state, stage: action.stage, stageMessage: action.message ?? '' }
    case 'ADD_CLAIMS':
      return { ...state, claims: action.claims }
    case 'ADD_SOURCES':
      return {
        ...state,
        sourcesByClaim: {
          ...state.sourcesByClaim,
          [action.claim_id]: action.sources,
        },
      }
    case 'SET_BIAS':
      return { ...state, bias: action.bias }
    case 'SET_VERDICT':
      return { ...state, verdict: action.verdict, stage: 'complete' }
    case 'SET_ERROR':
      return { ...state, error: action.error, stage: 'error' }
    case 'HYDRATE':
      return {
        ...state,
        claims: action.payload.claims,
        sourcesByClaim: action.payload.sourcesByClaim,
        bias: action.payload.bias,
        verdict: action.payload.verdict,
        stage: action.payload.stage ?? (action.payload.verdict ? 'complete' : 'fetching_article'),
        stageMessage: action.payload.stage === 'complete' ? '' : (state.stageMessage || 'Processing pipeline...'),
        error: null,
      }
    case 'RESET':
      return initialState
    default:
      return state
  }
}

// ── Context ────────────────────────────────────────────────────
interface JobContextValue {
  state: JobState
  dispatch: React.Dispatch<Action>
}

const JobContext = createContext<JobContextValue | undefined>(undefined)

export function JobProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  return (
    <JobContext.Provider value={{ state, dispatch }}>
      {children}
    </JobContext.Provider>
  )
}

export function useJobContext(): JobContextValue {
  const ctx = useContext(JobContext)
  if (!ctx) throw new Error('useJobContext must be used inside JobProvider')
  return ctx
}
