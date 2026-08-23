import { create } from 'zustand'

export const DEFAULT_DATASET_PREFERENCE = 'incois_argo_mnt_VAM'
export const DEFAULT_TIME_INDEX = 130

export const useOceanStore = create((set, get) => ({
  datasets: [],
  activeDatasetId: null,

  variables: [],
  activeVariable: 'temperature',

  timeRange: null,
  timestampsList: [],
  timeIndex: DEFAULT_TIME_INDEX,
  isPlaying: false,
  playSpeed: 1,

  depths: [],
  activeDepth: 5.0,
  verticalKind: 'depth',

  bbox: null,

  viewMode: '3D',
  showVolume: true,
  showCurrents: true,
  showArgoFloats: true,
  showGlider: false,
  verticalExaggeration: 50,

  colormap: 'viridis',
  colorMin: null,
  colorMax: null,
  logScale: false,
  opacity: 0.85,

  selectedFloat: null,
  selectedProfile: null,
  profileVariable: 'temperature',

  upstream503: false,
  upstream503Message: '',

  dataLoadedAt: null,
  setDataLoadedAt: (ts) => set({ dataLoadedAt: ts }),

  setDatasets: (datasets) => {
    set({ datasets })
    const { activeDatasetId } = get()
    if (!activeDatasetId && datasets.length) {
      get().setActiveDataset(pickPreferred(datasets))
    }
  },

  setActiveDataset: (id) => {
    if (get().activeDatasetId === id) return
    set({
      activeDatasetId: id,
      variables: [],
      timeRange: null,
      timestampsList: [],
      depths: [],
      activeDepth: 5.0,
      timeIndex: DEFAULT_TIME_INDEX,
      isPlaying: false,
      colorMin: null,
      colorMax: null,
      bbox: null,
      selectedFloat: null,
      selectedProfile: null,
    })
  },

  setVariables: (variables) => set({ variables }),

  setActiveVariable: (variable) =>
    set({
      activeVariable: variable,
      colorMin: null,
      colorMax: null,
      colormap: defaultColormapFor(variable),
    }),

  setTimeRange: (timeRange) => {
    const prev = get().timeRange
    set({ timeRange })
    if (prev?.count !== timeRange?.count) {
      clampTimeIndex()
    }
  },

  setTimestampsList: (timestampsList) => {
    if (!Array.isArray(timestampsList)) return
    if (timestampsList.length === get().timestampsList.length) return
    set({ timestampsList })
  },

  stepTime: (delta) => {
    const { timeIndex } = get()
    set({ timeIndex: Math.max(0, timeIndex + delta) })
    clampTimeIndex()
  },

  setTimeIndex: (index) => {
    set({ timeIndex: Math.max(0, index) })
    clampTimeIndex()
  },

  togglePlay: () => set((s) => ({ isPlaying: !s.isPlaying })),
  setPlaying: (playing) => set({ isPlaying: playing }),
  setPlaySpeed: (speed) => set({ playSpeed: speed }),

  setDepths: (depths) => {
    set({ depths })
    const { activeDepth } = get()
    if (!depths.length) return
    if (!depths.includes(activeDepth)) {
      set({ activeDepth: nearestDepth(depths, activeDepth ?? 5.0) })
    }
  },

  setActiveDepth: (depth) => set({ activeDepth: depth }),
  setVerticalKind: (verticalKind) => set({ verticalKind }),
  setBbox: (bbox) => set({ bbox }),

  setViewMode: (viewMode) => set({ viewMode }),
  toggleShowVolume: () => set((s) => ({ showVolume: !s.showVolume })),
  toggleShowCurrents: () => set((s) => ({ showCurrents: !s.showCurrents })),
  toggleShowArgoFloats: () => set((s) => ({ showArgoFloats: !s.showArgoFloats })),
  toggleShowGlider: () => set((s) => ({ showGlider: !s.showGlider })),
  setVerticalExaggeration: (v) => set({ verticalExaggeration: v }),

  setColormap: (colormap) => set({ colormap }),
  setColorRange: (min, max) => set({ colorMin: min, colorMax: max }),
  resetColorRange: () => set({ colorMin: null, colorMax: null }),
  setLogScale: (logScale) => set({ logScale }),
  setOpacity: (opacity) => set({ opacity }),

  setSelectedFloat: (selectedFloat) => set({ selectedFloat, selectedProfile: null }),
  setSelectedProfile: (selectedProfile) => set({ selectedProfile }),
  setProfileVariable: (profileVariable) => set({ profileVariable }),
  closeFloatPanel: () => set({ selectedFloat: null, selectedProfile: null }),

  setUpstream503: (upstream503, message = '') => {
    const cur = get()
    if (cur.upstream503 === upstream503 && cur.upstream503Message === message) return
    set({ upstream503, upstream503Message: message })
  },
}))

function pickPreferred(datasets) {
  const local = datasets.filter((d) => d.source_type === 'local')
  const preferred =
    local.find((d) => d.id === DEFAULT_DATASET_PREFERENCE) ??
    local.find((d) => d.id.includes('mnt_VAM')) ??
    local[0] ??
    datasets[0]
  return preferred?.id ?? null
}

function nearestDepth(depths, target) {
  let best = depths[0]
  let bestDiff = Math.abs(depths[0] - target)
  for (const d of depths) {
    const diff = Math.abs(d - target)
    if (diff < bestDiff) {
      best = d
      bestDiff = diff
    }
  }
  return best
}

function clampTimeIndex() {
  const s = get()
  const count = s.timeRange?.count
  if (Number.isFinite(count) && count > 0 && s.timeIndex > count - 1) {
    set({ timeIndex: count - 1 })
  }
}

export function defaultColormapFor(variable) {
  if (variable === 'salinity') return 'plasma'
  if (variable === 'u_current' || variable === 'v_current') return 'coolwarm'
  if (variable === 'chlorophyll') return 'magma'
  return 'viridis'
}
