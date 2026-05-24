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

        if (status === 'FAILED') {
          dispatch({
            type: 'SET_ERROR',
            error: jobRes.data.error_message || 'Job failed',
          })
          return
        }

        const verdictRes = await jobs.getVerdict(jobId)
        if (cancelled) return

        const data = verdictRes.data
        const claims: Claim[] = data.claim_verdicts.map((cv) => ({
          claim_id: cv.claim_id,
          text: cv.text,
          claim_type: cv.claim_type,
          checkability: cv.checkability,
        }))

        const sourcesByClaim: Record<string, Source[]> = {}
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

        const bias: BiasData | null = data.bias
          ? {
              bias_score: data.bias.bias_score,
              bias_direction: data.bias.bias_direction,
              framing_flags: (data.bias.framing_flags || []) as BiasData['framing_flags'],
              loaded_terms: data.bias.loaded_terms || [],
              summary: data.bias.summary || '',
            }
          : null

        const hasOverallVerdict = data.overall_verdict && data.overall_verdict !== 'PENDING'
        const verdict: VerdictData | null = hasOverallVerdict
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

        let mappedStage: Stage = 'fetching_article'
        if (status === 'COMPLETE' || status === 'PARTIAL') {
          mappedStage = 'complete'
        } else if (claims.length > 0) {
          // If we already have claims, advance stage beyond 'fetching'
          mappedStage = 'sourcing_claims'
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
