import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as model from '@/services/modelService'
import * as argo from '@/services/argoService'
import { fetchGliderStatus } from '@/services/gliderService'
import { get } from '@/services/api'
import { useOceanStore } from '@/store/oceanStore'

const MIN = 5 * 60 * 1000
const LONG = 30 * 60 * 1000
export const SLICE_STALE = 10 * 60 * 1000

// Rendering every native depth is unnecessarily expensive on a browser GPU.
// Eight levels give a useful water-column overview while keeping requests and
// texture count bounded. The active depth is always retained.
export const MAX_RENDER_DEPTHS = 8

export function selectRenderDepths(depths, activeDepth, maxDepths = MAX_RENDER_DEPTHS) {
  if (!Array.isArray(depths) || !depths.length) return []
  const unique = [...new Set(depths.filter(Number.isFinite))].sort((a, b) => a - b)
  if (unique.length <= maxDepths) return unique

  const selected = new Set()
  for (let i = 0; i < maxDepths; i += 1) {
    const index = Math.round((i * (unique.length - 1)) / (maxDepths - 1))
    selected.add(unique[index])
  }

  if (Number.isFinite(activeDepth)) {
    const nearest = unique.reduce((best, value) =>
      Math.abs(value - activeDepth) < Math.abs(best - activeDepth) ? value : best,
    unique[0])
    selected.add(nearest)
  }

  const values = [...selected].sort((a, b) => a - b)
  if (values.length <= maxDepths) return values

  // Preserve the active level and remove the least useful interior level.
  const active = values.reduce((best, value) =>
    Math.abs(value - activeDepth) < Math.abs(best - activeDepth) ? value : best,
  values[0])
  while (values.length > maxDepths) {
    let removeAt = 1
    let largestGap = -1
    for (let i = 1; i < values.length - 1; i += 1) {
      if (values[i] === active) continue
      const gap = Math.min(values[i] - values[i - 1], values[i + 1] - values[i])
      if (gap > largestGap) {
        largestGap = gap
        removeAt = i
      }
    }
    if (values[removeAt] === active) removeAt = values.length - 2
    values.splice(removeAt, 1)
  }
  return values
}

export function useDatasets() {
  return useQuery({
    queryKey: ['datasets'],
    queryFn: ({ signal }) => model.fetchDatasets(signal),
    staleTime: MIN,
  })
}

export function useMetadata(id) {
  return useQuery({
    queryKey: ['metadata', id],
    queryFn: ({ signal }) => model.fetchMetadata(id, signal),
    enabled: !!id,
    staleTime: LONG,
  })
}

export function useVariables(id) {
  return useQuery({
    queryKey: ['variables', id],
    queryFn: ({ signal }) => model.fetchVariables(id, signal),
    enabled: !!id,
    staleTime: LONG,
  })
}

export function useTimes(id) {
  return useQuery({
    queryKey: ['times', id],
    queryFn: ({ signal }) => model.fetchTimes(id, signal),
    enabled: !!id,
    staleTime: LONG,
  })
}

export function useDepths(id) {
  return useQuery({
    queryKey: ['depths', id],
    queryFn: ({ signal }) => model.fetchDepths(id, signal),
    enabled: !!id,
    staleTime: LONG,
  })
}

export function useExtent(id) {
  return useQuery({
    queryKey: ['extent', id],
    queryFn: ({ signal }) => model.fetchExtent(id, signal),
    enabled: !!id,
    staleTime: LONG,
  })
}

export function useTimesList(id) {
  return useQuery({
    queryKey: ['times-list', id],
    queryFn: ({ signal }) => model.fetchTimesList(id, signal),
    enabled: !!id,
    staleTime: LONG,
  })
}

export const sliceKey = (id, variable, timeIndex, depth, bbox) => [
  'slice',
  id,
  variable,
  timeIndex,
  depth,
  bbox ?? null,
]

export function useSlice(id, variable, timeIndex, depth, bbox) {
  return useQuery({
    queryKey: sliceKey(id, variable, timeIndex, depth, bbox),
    queryFn: ({ signal }) =>
      model.fetchSlice(id, variable, timeIndex, depth, bbox, signal),
    enabled: !!id && !!variable && Number.isFinite(depth),
    staleTime: SLICE_STALE,
    placeholderData: (prev) => prev,
  })
}

export const sliceStackKey = (id, variable, timeIndex, depths = null) => [
  'slice-stack',
  id,
  variable,
  timeIndex,
  depths,
]

async function fetchDepthsForStack(queryClient, id, signal) {
  return queryClient.fetchQuery({
    queryKey: ['depths', id],
    queryFn: () => model.fetchDepths(id, signal),
    staleTime: LONG,
  })
}

export async function fetchSliceStack(queryClient, id, variable, timeIndex, activeDepth = null, signal) {
  const depths = await fetchDepthsForStack(queryClient, id, signal)
  const renderDepths = selectRenderDepths(depths, activeDepth)
  if (!renderDepths.length) return []

  // The backend accepts up to 10 slices per batch. Keep the chunking here so
  // the frontend remains safe if MAX_RENDER_DEPTHS is raised later.
  const results = []
  for (let offset = 0; offset < renderDepths.length; offset += 10) {
    const chunk = renderDepths.slice(offset, offset + 10).map((depth) => ({
      variable,
      time_index: timeIndex,
      depth_meters: depth,
    }))
    const batch = await model.fetchSliceBatch(id, chunk, signal)
    results.push(...(Array.isArray(batch) ? batch : []))
  }
  return results
}

export function useSliceStack(id, variable, timeIndex, activeDepth = null) {
  const depths = useOceanStore((s) => s.depths)
  const renderDepths = useMemoRenderDepths(depths, activeDepth)
  return useQuery({
    queryKey: sliceStackKey(id, variable, timeIndex, renderDepths),
    queryFn: ({ signal }) => fetchSliceStack(
      queryClientFromContext(),
      id,
      variable,
      timeIndex,
      activeDepth,
      signal,
    ),
    enabled: !!id && !!variable && renderDepths.length > 0,
    staleTime: SLICE_STALE,
  })
}

// React Query does not expose the QueryClient from queryFn context, so use the
// client hook in the public hook and keep the lower-level helper reusable.
function useMemoRenderDepths(depths, activeDepth) {
  return selectRenderDepths(depths, activeDepth)
}

// Kept as a small indirection so callers outside React can continue using
// fetchSliceStack. The actual React hook is implemented below.
let activeQueryClient = null
function queryClientFromContext() {
  if (!activeQueryClient) throw new Error('QueryClient not initialised')
  return activeQueryClient
}

export function prefetchSliceStack(queryClient, id, variable, timeIndex, activeDepth = null) {
  if (!id || !variable || !Number.isFinite(timeIndex)) return
  const depths = selectRenderDepths(
    useOceanStore.getState().depths,
    activeDepth ?? useOceanStore.getState().activeDepth,
  )
  void queryClient.prefetchQuery({
    queryKey: sliceStackKey(id, variable, timeIndex, depths),
    queryFn: ({ signal }) => fetchSliceStack(queryClient, id, variable, timeIndex, activeDepth, signal),
    staleTime: SLICE_STALE,
  })
}

export function prefetchSlices(queryClient, id, variable, timeIndexes, depth, bbox) {
  if (!id || !variable || !Number.isFinite(depth)) return
  for (const t of timeIndexes) {
    if (!Number.isFinite(t)) continue
    void queryClient.prefetchQuery({
      queryKey: sliceKey(id, variable, t, depth, bbox),
      queryFn: ({ signal }) =>
        model.fetchSlice(id, variable, t, depth, bbox, signal),
      staleTime: SLICE_STALE,
    })
  }
}

export function useProfile(id, variable, lat, lon, timeIndex) {
  return useQuery({
    queryKey: ['profile', id, variable, lat, lon, timeIndex],
    queryFn: ({ signal }) =>
      model.fetchProfile(id, variable, lat, lon, timeIndex, signal),
    enabled:
      !!id &&
      !!variable &&
      Number.isFinite(lat) &&
      Number.isFinite(lon),
    staleTime: SLICE_STALE,
  })
}

export function usePoint(id, variables, lat, lon, timeIndex, depth, enabled = true) {
  return useQuery({
    queryKey: ['point', id, variables, lat, lon, timeIndex, depth],
    queryFn: ({ signal }) =>
      model.fetchPoint(id, variables, lat, lon, timeIndex, depth, signal),
    enabled:
      enabled &&
      !!id &&
      Array.isArray(variables) &&
      variables.length > 0 &&
      Number.isFinite(lat) &&
      Number.isFinite(lon),
    staleTime: SLICE_STALE,
  })
}

export function useCurrents(id, timeIndex, depth, bbox) {
  return useQuery({
    queryKey: ['currents', id, timeIndex, depth, bbox],
    queryFn: ({ signal }) => model.fetchCurrents(id, timeIndex, depth, bbox, signal),
    enabled: !!id,
    staleTime: SLICE_STALE,
  })
}

export function useServices(id) {
  return useQuery({
    queryKey: ['services', id],
    queryFn: ({ signal }) => model.fetchServices(id, signal),
    enabled: !!id,
    staleTime: LONG,
    retry: false,
  })
}

export function useArgoFloats(bounds) {
  return useQuery({
    queryKey: ['argo-floats', bounds ?? null],
    queryFn: ({ signal }) => argo.fetchArgoFloats(bounds, undefined, signal),
    staleTime: MIN,
    refetchInterval: MIN,
    retry: (count, err) => !(err?.permanent ?? false) && count < 2,
  })
}

export function useArgoDetail(wmo) {
  return useQuery({
    queryKey: ['argo-detail', wmo],
    queryFn: ({ signal }) => argo.fetchArgoDetail(wmo, signal),
    enabled: wmo != null,
    staleTime: MIN,
    retry: false,
  })
}

export function useArgoProfile(wmo) {
  return useQuery({
    queryKey: ['argo-profile', wmo],
    queryFn: ({ signal }) => argo.fetchArgoProfile(wmo, undefined, signal),
    enabled: wmo != null,
    staleTime: MIN,
    retry: false,
  })
}

export function useGliderStatus() {
  return useQuery({
    queryKey: ['glider-status'],
    queryFn: ({ signal }) => fetchGliderStatus(signal),
    staleTime: LONG,
    retry: false,
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchHealth('/health', signal),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  })
}

export function useReadiness() {
  return useQuery({
    queryKey: ['health-ready'],
    queryFn: ({ signal }) => fetchHealth('/health/ready', signal),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  })
}

async function fetchHealth(path, signal) {
  return get(path, { signal, noStore: true })
}

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
    if (Array.isArray(ext.depth_levels) && ext.depth_levels.length) {
      store.setDepths(ext.depth_levels)
    }
    if (ext.vertical_kind) store.setVerticalKind(ext.vertical_kind)
    const current = useOceanStore.getState().variables
    if (!current.length && Array.isArray(ext.variables) && ext.variables.length) {
      store.setVariables(
        ext.variables.map((v) => (typeof v === 'string' ? { name: v, canonical_name: v } : v)),
      )
    }
  }, [extentQuery.data])

  useEffect(() => {
    if (Array.isArray(variablesQuery.data) && variablesQuery.data.length) {
      useOceanStore.getState().setVariables(variablesQuery.data)
    }
  }, [variablesQuery.data])

  useEffect(() => {
    if (Array.isArray(timesListQuery.data)) {
      useOceanStore.getState().setTimestampsList(timesListQuery.data)
    }
  }, [timesListQuery.data])
}
