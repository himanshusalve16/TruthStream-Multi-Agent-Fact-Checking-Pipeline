import { useEffect, useState } from 'react'
import { jobs } from '../api/client'
import { useJobContext } from '../context/JobContext'
import type { Claim, Source, BiasData, VerdictData, Stage } from '../context/JobContext'

/**
 * Loads completed/failed job state from REST when opening /jobs/:id directly.
 * Returns whether SSE streaming should be enabled for in-flight jobs.
 */
export function useJobHydration(jobId: string | undefined): boolean {
  const { dispatch } = useJobContext()
  const [streamEnabled, setStreamEnabled] = useState(false)

  useEffect(() => {
    if (!jobId) return
    let cancelled = false

    const load = async () => {
      try {
        const jobRes = await jobs.get(jobId)
        if (cancelled) return

        const status = jobRes.data.status
        let mappedStage: Stage = 'fetching'
        if (status === 'COMPLETE') {
          mappedStage = 'completed'
        } else if (status === 'PARTIAL') {
          mappedStage = 'partial_completed'
        } else if (status === 'FAILED') {
          mappedStage = 'failed'
        }

        let claims: Claim[] = []
        let sourcesByClaim: Record<string, Source[]> = {}
        let bias: BiasData | null = null
        let verdict: VerdictData | null = null

        try {
          const verdictRes = await jobs.getVerdict(jobId)
          if (cancelled) return

          const data = verdictRes.data
          claims = data.claim_verdicts.map((cv) => ({
            claim_id: cv.claim_id,
            text: cv.text,
            claim_type: cv.claim_type,
            checkability: cv.checkability,
          }))

          for (const cv of data.claim_verdicts) {
            sourcesByClaim[cv.claim_id] = (cv.sources || []).map((s) => ({
              source_id: s.source_id,
              url: s.url,
              title: s.title,
              domain: s.domain,
              snippet: s.snippet,
              stance: s.stance as Source['stance'],
              quality_score: s.quality_score,
              fetch_status: s.fetch_status,
            }))
          }

          bias = data.bias
            ? {
                bias_score: data.bias.bias_score,
                bias_direction: data.bias.bias_direction,
                framing_flags: (data.bias.framing_flags || []) as BiasData['framing_flags'],
                loaded_terms: data.bias.loaded_terms || [],
                summary: data.bias.summary || '',
              }
            : null

          const hasOverallVerdict = data.overall_verdict && data.overall_verdict !== 'PENDING'
          verdict = hasOverallVerdict
            ? {
                overall_verdict: data.overall_verdict,
                overall_confidence: Number(data.overall_confidence),
                overall_summary: data.overall_summary,
                claim_verdicts: data.claim_verdicts.map((cv) => ({
                  claim_id: cv.claim_id,
                  verdict: cv.verdict as VerdictData['claim_verdicts'][0]['verdict'],
                  confidence: Number(cv.confidence),
                  reasoning: cv.reasoning,
                })),
              }
            : null
        } catch (e) {
          console.warn('Failed to load partial verdict details, using defaults', e)
        }

        if (cancelled) return

        if (status === 'PENDING') {
          mappedStage = 'accepted'
        } else if (status === 'PROCESSING') {
          if (verdict && verdict.overall_verdict && verdict.overall_verdict !== 'PENDING') {
            mappedStage = 'completed'
          } else if (claims.length > 0) {
            const hasSources = Object.values(sourcesByClaim).some(sources => sources.length > 0)
            if (hasSources) {
              mappedStage = 'reasoning'
            } else {
              mappedStage = 'verifying_sources'
            }
          } else {
            mappedStage = 'routing'
          }
        }

        if (status === 'FAILED') {
          dispatch({
            type: 'SET_ERROR',
            error: jobRes.data.error_message || 'Job failed',
          })
          return
        }

        dispatch({
          type: 'HYDRATE',
          payload: { claims, sourcesByClaim, bias, verdict, stage: mappedStage },
        })

        if (status === 'COMPLETE' || status === 'PARTIAL') {
          return
        }

        setStreamEnabled(true)
      } catch {
        if (!cancelled) {
          setStreamEnabled(true)
        }
      }
    }

    load()
    return () => {
      cancelled = true
      setStreamEnabled(false)
    }
  }, [jobId, dispatch])

  return streamEnabled
}
