import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import * as model from '@/services/modelService'
import * as argo from '@/services/argoService'
import { fetchGliderStatus } from '@/services/gliderService'
import { get } from '@/services/api'
import { useOceanStore } from '@/store/oceanStore'

const MIN = 5 * 60 * 1000
const LONG = 30 * 60 * 1000
export const SLICE_STALE = 10 * 60 * 1000
export const MAX_RENDER_DEPTHS = 8

export function selectRenderDepths(depths, activeDepth, maxDepths = MAX_RENDER_DEPTHS) {
  if (!Array.isArray(depths) || !depths.length) return [null]
  const unique = [...new Set(depths.filter(Number.isFinite))].sort((a, b) => a - b)
  if (unique.length <= maxDepths) return unique
  const selected = new Set()
  for (let i = 0; i < maxDepths; i += 1) selected.add(unique[Math.round((i * (unique.length - 1)) / (maxDepths - 1))])
  if (Number.isFinite(activeDepth)) {
    const nearest = unique.reduce((best, value) => Math.abs(value - activeDepth) < Math.abs(best - activeDepth) ? value : best, unique[0])
    selected.add(nearest)
  }
  const values = [...selected].sort((a, b) => a - b)
  while (values.length > maxDepths) {
    let removeAt = -1
    let largestGap = -1
    for (let i = 1; i < values.length - 1; i += 1) {
      if (Number.isFinite(activeDepth) && values[i] === activeDepth) continue
      const gap = Math.min(values[i] - values[i - 1], values[i + 1] - values[i])
      if (gap > largestGap) { largestGap = gap; removeAt = i }
    }
    if (removeAt < 0) removeAt = values.length - 2
    values.splice(removeAt, 1)
  }
  return values
}

export function useDatasets() { return useQuery({ queryKey: ['datasets'], queryFn: ({ signal }) => model.fetchDatasets(signal), staleTime: MIN }) }
export function useMetadata(id) { return useQuery({ queryKey: ['metadata', id], queryFn: ({ signal }) => model.fetchMetadata(id, signal), enabled: !!id, staleTime: LONG }) }
export function useVariables(id) { return useQuery({ queryKey: ['variables', id], queryFn: ({ signal }) => model.fetchVariables(id, signal), enabled: !!id, staleTime: LONG }) }
export function useTimes(id) { return useQuery({ queryKey: ['times', id], queryFn: ({ signal }) => model.fetchTimes(id, signal), enabled: !!id, staleTime: LONG }) }
export function useDepths(id) { return useQuery({ queryKey: ['depths', id], queryFn: ({ signal }) => model.fetchDepths(id, signal), enabled: !!id, staleTime: LONG }) }
export function useExtent(id) { return useQuery({ queryKey: ['extent', id], queryFn: ({ signal }) => model.fetchExtent(id, signal), enabled: !!id, staleTime: LONG }) }
export function useTimesList(id) { return useQuery({ queryKey: ['times-list', id], queryFn: ({ signal }) => model.fetchTimesList(id, signal), enabled: !!id, staleTime: LONG }) }

export const sliceKey = (id, variable, timeIndex, depth, bbox) => ['slice', id, variable, timeIndex, depth, bbox ?? null]
export function useSlice(id, variable, timeIndex, depth, bbox) {
  return useQuery({ queryKey: sliceKey(id, variable, timeIndex, depth, bbox), queryFn: ({ signal }) => model.fetchSlice(id, variable, timeIndex, depth, bbox, signal), enabled: !!id && !!variable, staleTime: SLICE_STALE, placeholderData: (prev) => prev })
}
export const sliceStackKey = (id, variable, timeIndex, depths = null) => ['slice-stack', id, variable, timeIndex, depths]

export async function fetchSliceStack(queryClient, id, variable, timeIndex, activeDepth = null, signal) {
  const depths = await queryClient.fetchQuery({ queryKey: ['depths', id], queryFn: ({ signal: depthSignal }) => model.fetchDepths(id, depthSignal), staleTime: LONG })
  const renderDepths = selectRenderDepths(depths, activeDepth)
  const results = []
  for (let offset = 0; offset < renderDepths.length; offset += 10) {
    const chunk = renderDepths.slice(offset, offset + 10).map((depth) => ({ variable, time_index: timeIndex, depth_meters: depth }))
    const batch = await model.fetchSliceBatch(id, chunk, signal)
    results.push(...(Array.isArray(batch) ? batch : []))
  }
  return results
}

export function useSliceStack(id, variable, timeIndex, activeDepth = null) {
  const queryClient = useQueryClient()
  const depths = useOceanStore((s) => s.depths)
  const renderDepths = selectRenderDepths(depths, activeDepth)
  return useQuery({ queryKey: sliceStackKey(id, variable, timeIndex, renderDepths), queryFn: ({ signal }) => fetchSliceStack(queryClient, id, variable, timeIndex, activeDepth, signal), enabled: !!id && !!variable, staleTime: SLICE_STALE })
}

export function prefetchSliceStack(queryClient, id, variable, timeIndex, activeDepth = null) {
  if (!id || !variable || !Number.isFinite(timeIndex)) return
  const depths = selectRenderDepths(useOceanStore.getState().depths, activeDepth ?? useOceanStore.getState().activeDepth)
  void queryClient.prefetchQuery({ queryKey: sliceStackKey(id, variable, timeIndex, depths), queryFn: ({ signal }) => fetchSliceStack(queryClient, id, variable, timeIndex, activeDepth, signal), staleTime: SLICE_STALE })
}
export function prefetchSlices(queryClient, id, variable, timeIndexes, depth, bbox) {
  if (!id || !variable || !Number.isFinite(depth)) return
  for (const t of timeIndexes) if (Number.isFinite(t)) void queryClient.prefetchQuery({ queryKey: sliceKey(id, variable, t, depth, bbox), queryFn: ({ signal }) => model.fetchSlice(id, variable, t, depth, bbox, signal), staleTime: SLICE_STALE })
}

export function useProfile(id, variable, lat, lon, timeIndex) { return useQuery({ queryKey: ['profile', id, variable, lat, lon, timeIndex], queryFn: ({ signal }) => model.fetchProfile(id, variable, lat, lon, timeIndex, signal), enabled: !!id && !!variable && Number.isFinite(lat) && Number.isFinite(lon), staleTime: SLICE_STALE }) }
export function usePoint(id, variables, lat, lon, timeIndex, depth, enabled = true) { return useQuery({ queryKey: ['point', id, variables, lat, lon, timeIndex, depth], queryFn: ({ signal }) => model.fetchPoint(id, variables, lat, lon, timeIndex, depth, signal), enabled: enabled && !!id && Array.isArray(variables) && variables.length > 0 && Number.isFinite(lat) && Number.isFinite(lon), staleTime: SLICE_STALE }) }
export function useCurrents(id, timeIndex, depth, bbox) { return useQuery({ queryKey: ['currents', id, timeIndex, depth, bbox], queryFn: ({ signal }) => model.fetchCurrents(id, timeIndex, depth, bbox, signal), enabled: !!id, staleTime: SLICE_STALE }) }
export function useServices(id) { return useQuery({ queryKey: ['services', id], queryFn: ({ signal }) => model.fetchServices(id, signal), enabled: !!id, staleTime: LONG, retry: false }) }
export function useArgoFloats(bounds) { return useQuery({ queryKey: ['argo-floats', bounds ?? null], queryFn: ({ signal }) => argo.fetchArgoFloats(bounds, undefined, signal), staleTime: MIN, refetchInterval: MIN, retry: (count, err) => !(err?.permanent ?? false) && count < 2 }) }
export function useArgoDetail(wmo) { return useQuery({ queryKey: ['argo-detail', wmo], queryFn: ({ signal }) => argo.fetchArgoDetail(wmo, signal), enabled: wmo != null, staleTime: MIN, retry: false }) }
export function useArgoProfile(wmo) { return useQuery({ queryKey: ['argo-profile', wmo], queryFn: ({ signal }) => argo.fetchArgoProfile(wmo, undefined, signal), enabled: wmo != null, staleTime: MIN, retry: false }) }
export function useGliderStatus() { return useQuery({ queryKey: ['glider-status'], queryFn: ({ signal }) => fetchGliderStatus(signal), staleTime: LONG, retry: false }) }
export function useHealth() { return useQuery({ queryKey: ['health'], queryFn: ({ signal }) => fetchHealth('/health', signal), refetchInterval: 60_000, staleTime: 30_000, retry: false }) }
export function useReadiness() { return useQuery({ queryKey: ['health-ready'], queryFn: ({ signal }) => fetchHealth('/health/ready', signal), refetchInterval: 60_000, staleTime: 30_000, retry: false }) }
async function fetchHealth(path, signal) { return get(path, { signal, noStore: true }) }

export function useDatasetSync() {
  const id = useOceanStore((s) => s.activeDatasetId)
  useMetadata(id)
  const extentQuery = useExtent(id)
  const timesListQuery = useTimesList(id)
  const variablesQuery = useVariables(id)
  useEffect(() => {
    const ext = extentQuery.data
    if (!ext) return
    const store = useOceanStore.getState()
    if (ext.time_range) store.setTimeRange(ext.time_range)
    if (Array.isArray(ext.depth_levels)) store.setDepths(ext.depth_levels)
    if (ext.vertical_kind) store.setVerticalKind(ext.vertical_kind)
    if (!useOceanStore.getState().variables.length && Array.isArray(ext.variables) && ext.variables.length) store.setVariables(ext.variables.map((v) => (typeof v === 'string' ? { name: v, canonical_name: v } : v)))
  }, [extentQuery.data])
  useEffect(() => { if (Array.isArray(variablesQuery.data) && variablesQuery.data.length) useOceanStore.getState().setVariables(variablesQuery.data) }, [variablesQuery.data])
  useEffect(() => { if (Array.isArray(timesListQuery.data)) useOceanStore.getState().setTimestampsList(timesListQuery.data) }, [timesListQuery.data])
}
