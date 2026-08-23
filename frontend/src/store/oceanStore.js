import { create } from 'zustand'

export const useOceanStore = create((set) => ({
  datasetId: null,
  variable: null,
  timeIndex: 0,
  depthIndex: 0,
  colormap: 'turbo',
  opacity: 1,
  bbox: null,
  selectedFloat: null,

  setSelection: (patch) => set(patch),
  setSelectedFloat: (wmo) => set({ selectedFloat: wmo }),
}))
