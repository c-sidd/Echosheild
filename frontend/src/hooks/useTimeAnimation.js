import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useOceanStore } from '@/store/oceanStore'
import { prefetchSliceStack, SLICE_STALE } from '@/hooks/useOceanData'
import { fetchSliceBatch } from '@/services/modelService'

export function useTimeAnimation() {
  const queryClient = useQueryClient()
  const frameRef = useRef(0)
  const lastStepRef = useRef(0)

  const isPlaying = useOceanStore((s) => s.isPlaying)
  const playSpeed = useOceanStore((s) => s.playSpeed)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const count = useOceanStore((s) => s.timeRange?.count ?? 0)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const variable = useOceanStore((s) => s.activeVariable)
  const depth = useOceanStore((s) => s.activeDepth)
  const viewMode = useOceanStore((s) => s.viewMode)

  useEffect(() => {
    if (!isPlaying || count < 2) return undefined

    let acc = 0
    let prev = performance.now()
    const interval = 1000 / Math.max(playSpeed, 0.05)

    const tick = (now) => {
      acc += now - prev
      prev = now
      const store = useOceanStore.getState()
      while (acc >= interval) {
        acc -= interval
        const next = store.timeIndex + 1
        const wrapped = count > 0 && next > count - 1 ? 0 : next
        store.setTimeIndex(wrapped)
      }
      frameRef.current = requestAnimationFrame(tick)
    }

    frameRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameRef.current)
  }, [isPlaying, playSpeed, count])

  // Prefetch ahead so playback never stalls on the network.
  useEffect(() => {
    if (!datasetId || !variable) return
    const maxIndex = count - 1

    function wrap(i) {
      return count > 0 && i > maxIndex ? i % count : Math.max(0, i)
    }

    if (viewMode === '3D') {
      prefetchSliceStack(queryClient, datasetId, variable, wrap(timeIndex + 1))
    } else if (Number.isFinite(depth)) {
      // One round-trip instead of three parallel slice requests.
      const batch = [timeIndex + 1, timeIndex + 2, timeIndex + 3]
        .map(wrap)
        .map((t) => ({ variable, time_index: t, depth_meters: depth }))
      void queryClient.fetchQuery({
        queryKey: ['slice-batch-prefetch', datasetId, variable, timeIndex, depth],
        queryFn: ({ signal }) => fetchSliceBatch(datasetId, batch, signal),
        staleTime: SLICE_STALE,
      })
    }
  }, [queryClient, datasetId, variable, timeIndex, count, depth, viewMode])

  // Keep the rAF-driven lastStep in sync for external consumers.
  useEffect(() => {
    lastStepRef.current = timeIndex
  }, [timeIndex])

  return { isPlaying, timeIndex }
}
