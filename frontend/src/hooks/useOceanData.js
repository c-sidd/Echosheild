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

export const sliceStackKey = (id, variable, timeIndex) => [
  'slice-stack',
  id,
  variable,
  timeIndex,
]

export async function fetchSliceStack(queryClient, id, variable, timeIndex) {
  const depths = await queryClient.fetchQuery({
    queryKey: ['depths', id],
    queryFn: ({ signal }) => model.fetchDepths(id, signal),
    staleTime: LONG,
  })
  if (!Array.isArray(depths) || !depths.length) return []
  return Promise.all(
    depths.map((depth) =>
      queryClient.fetchQuery({
        queryKey: sliceKey(id, variable, timeIndex, depth, null),
        queryFn: ({ signal }) =>
          model.fetchSlice(id, variable, timeIndex, depth, null, signal),
        staleTime: SLICE_STALE,
      }),
    ),
  )
}

export function useSliceStack(id, variable, timeIndex) {
  return useQuery({
    queryKey: sliceStackKey(id, variable, timeIndex),
    queryFn: async () => fetchSliceStackInternal(id, variable, timeIndex),
    enabled: !!id && !!variable,
    staleTime: SLICE_STALE,
  })
}

async function fetchSliceStackInternal(id, variable, timeIndex) {
  const depths = await model.fetchDepths(id)
  if (!Array.isArray(depths) || !depths.length) return []
  return Promise.all(
    depths.map((depth) => model.fetchSlice(id, variable, timeIndex, depth, null)),
  )
}

export function prefetchSliceStack(queryClient, id, variable, timeIndex) {
  if (!id || !variable || !Number.isFinite(timeIndex)) return
  void queryClient.prefetchQuery({
    queryKey: sliceStackKey(id, variable, timeIndex),
    queryFn: () => fetchSliceStack(queryClient, id, variable, timeIndex),
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

  // Single-call startup: time range + depth levels arrive together.
  useEffect(() => {
    const ext = extentQuery.data
    if (!ext) return
    const store = useOceanStore.getState()
    if (ext.time_range) store.setTimeRange(ext.time_range)
    if (Array.isArray(ext.depth_levels) && ext.depth_levels.length) {
      store.setDepths(ext.depth_levels)
    }
    if (ext.vertical_kind) store.setVerticalKind(ext.vertical_kind)
    // Extent only carries variable names — seed minimal entries so the UI
    // can render immediately; rich metadata below replaces them.
    const current = useOceanStore.getState().variables
    if (!current.length && Array.isArray(ext.variables) && ext.variables.length) {
      store.setVariables(
        ext.variables.map((v) => (typeof v === 'string' ? { name: v, canonical_name: v } : v)),
      )
    }
  }, [extentQuery.data])

  // Rich variable metadata (units, source names) once available.
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
