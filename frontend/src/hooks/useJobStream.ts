import { useEffect, useRef } from 'react'
import { useJobContext } from '../context/JobContext'

export function useJobStream(jobId: string | null) {
  const { dispatch } = useJobContext()
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) return

    const apiBase = import.meta.env.VITE_API_BASE_URL || '';
    const cleanBase = apiBase.endsWith('/') ? apiBase.slice(0, -1) : apiBase;
    const url = `${cleanBase}/api/jobs/${jobId}/stream`;

    const es = new EventSource(url)
    esRef.current = es

    es.addEventListener('status', (e) => {
      const data = JSON.parse(e.data)
      dispatch({ type: 'SET_STAGE', stage: data.stage, message: data.message })
    })

    es.addEventListener('claims_extracted', (e) => {
      const data = JSON.parse(e.data)
      dispatch({ type: 'ADD_CLAIMS', claims: data.claims })
      dispatch({ type: 'SET_STAGE', stage: 'sourcing_claims', message: 'Finding sources...' })
    })

    es.addEventListener('claim_sourced', (e) => {
      const data = JSON.parse(e.data)
      dispatch({ type: 'ADD_SOURCES', claim_id: data.claim_id, sources: data.sources })
    })

    es.addEventListener('bias_scored', (e) => {
      const data = JSON.parse(e.data)
      dispatch({ type: 'SET_BIAS', bias: data })
    })

    es.addEventListener('verdict', (e) => {
      const data = JSON.parse(e.data)
      dispatch({ type: 'SET_VERDICT', verdict: data })
    })

    es.addEventListener('no_claims', (e) => {
      const data = JSON.parse(e.data)
      dispatch({ type: 'SET_STAGE', stage: 'complete', message: data.message })
    })

    es.addEventListener('error', (e) => {
      // Server-sent error event
      try {
        const data = JSON.parse((e as MessageEvent).data)
        dispatch({ type: 'SET_ERROR', error: data.message })
      } catch {
        dispatch({ type: 'SET_ERROR', error: 'Connection error' })
      }
    })

    es.addEventListener('done', () => {
      es.close()
    })

    // Network-level error
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        dispatch({ type: 'SET_STAGE', stage: 'complete' })
      }
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [jobId, dispatch])
}
