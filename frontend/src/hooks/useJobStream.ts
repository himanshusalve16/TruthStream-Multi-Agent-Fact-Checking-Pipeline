import { useEffect, useRef } from 'react'
import { useJobContext } from '../context/JobContext'
import { API_BASE } from '../api/client'

export function useJobStream(jobId: string | null) {
  const { dispatch } = useJobContext()
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) return

    const actionQueue: any[] = []
    let isProcessing = false
    let lastTransitionTime = 0
    const MIN_STAGE_DURATION = 1200 // 1.2 seconds in milliseconds

    const processQueue = async () => {
      if (isProcessing || actionQueue.length === 0) return
      isProcessing = true

      while (actionQueue.length > 0) {
        const nextAction = actionQueue.shift()
        
        // Enforce visual dwell time for stage transitions
        if (
          nextAction.type === 'SET_STAGE' || 
          nextAction.type === 'SET_VERDICT' || 
          nextAction.type === 'SET_ERROR'
        ) {
          const now = Date.now()
          const timeSinceLast = now - lastTransitionTime
          const waitTime = MIN_STAGE_DURATION - timeSinceLast
          if (waitTime > 0) {
            await new Promise(resolve => setTimeout(resolve, waitTime))
          }
          lastTransitionTime = Date.now()
        }

        dispatch(nextAction)
      }
      isProcessing = false
    }

    const enqueue = (action: any) => {
      actionQueue.push(action)
      processQueue()
    }

    const cleanBase = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
    const url = `${cleanBase}/api/jobs/${jobId}/stream`;

    const es = new EventSource(url)
    esRef.current = es

    es.addEventListener('status', (e) => {
      const data = JSON.parse(e.data)
      enqueue({ type: 'SET_STAGE', stage: data.stage, message: data.message })
    })

    es.addEventListener('claims_extracted', (e) => {
      const data = JSON.parse(e.data)
      enqueue({ type: 'ADD_CLAIMS', claims: data.claims })
      enqueue({ type: 'SET_STAGE', stage: 'sourcing_claims', message: 'Finding sources...' })
    })

    es.addEventListener('claim_sourced', (e) => {
      const data = JSON.parse(e.data)
      enqueue({ type: 'ADD_SOURCES', claim_id: data.claim_id, sources: data.sources })
    })

    es.addEventListener('bias_scored', (e) => {
      const data = JSON.parse(e.data)
      enqueue({ type: 'SET_BIAS', bias: data })
    })

    es.addEventListener('verdict', (e) => {
      const data = JSON.parse(e.data)
      enqueue({ type: 'SET_VERDICT', verdict: data })
    })

    es.addEventListener('no_claims', (e) => {
      const data = JSON.parse(e.data)
      enqueue({ type: 'SET_STAGE', stage: 'complete', message: data.message })
    })

    es.addEventListener('error', (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data)
        enqueue({ type: 'SET_ERROR', error: data.message })
      } catch {
        enqueue({ type: 'SET_ERROR', error: 'Connection error' })
      }
    })

    es.addEventListener('done', () => {
      es.close()
    })

    // Network-level error
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        enqueue({ type: 'SET_STAGE', stage: 'complete' })
      }
    }

    return () => {
      es.close()
      esRef.current = null
      actionQueue.length = 0
    }
  }, [jobId, dispatch])
}
