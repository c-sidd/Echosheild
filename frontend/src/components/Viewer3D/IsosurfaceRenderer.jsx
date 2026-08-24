import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { MarchingCubes } from 'three-stdlib'
import { useOceanStore } from '@/store/oceanStore'
import { useSliceStack } from '@/hooks/useOceanData'
import { SCENE_DEPTH, SCENE_WIDTH } from '@/utils/depthUtils'

const RESOLUTION = 24

function sampleVolume(slices) {
  if (!slices?.length) return null
  const depthSlices = slices.filter((slice) => Number.isFinite(slice?.depth_meters))
  if (depthSlices.length < 2) return null
  let min = Infinity
  let max = -Infinity
  for (const slice of depthSlices) for (const row of slice.values ?? []) for (const value of row ?? []) if (Number.isFinite(value)) { min = Math.min(min, value); max = Math.max(max, value) }
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return null

  const field = new Float32Array(RESOLUTION * RESOLUTION * RESOLUTION)
  for (let z = 0; z < RESOLUTION; z += 1) {
    const slice = depthSlices[Math.round((z * (depthSlices.length - 1)) / (RESOLUTION - 1))]
    const rows = slice?.values ?? []
    const height = rows.length
    const width = rows[0]?.length ?? 0
    if (!height || !width) continue
    for (let y = 0; y < RESOLUTION; y += 1) {
      const row = rows[Math.min(height - 1, Math.round((y * (height - 1)) / (RESOLUTION - 1)))] ?? []
      for (let x = 0; x < RESOLUTION; x += 1) {
        const value = row[Math.min(width - 1, Math.round((x * (width - 1)) / (RESOLUTION - 1)))]
        field[x + RESOLUTION * (y + RESOLUTION * z)] = Number.isFinite(value) ? (value - min) / (max - min) : 0
      }
    }
  }
  return { field }
}

export default function IsosurfaceRenderer() {
  const enabled = useOceanStore((s) => s.showIsosurface && s.showVolume)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const variable = useOceanStore((s) => s.activeVariable)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const activeDepth = useOceanStore((s) => s.activeDepth)
  const verticalExaggeration = useOceanStore((s) => s.verticalExaggeration)
  const stack = useSliceStack(datasetId, variable, timeIndex, activeDepth, enabled)
  const volume = useMemo(() => sampleVolume(stack.data), [stack.data])
  const depthSpan = useMemo(() => {
    const depths = stack.data?.map((s) => s.depth_meters).filter(Number.isFinite) ?? []
    if (depths.length < 2) return 30
    return Math.max(20, Math.abs(Math.max(...depths) - Math.min(...depths)) * (verticalExaggeration / 50))
  }, [stack.data, verticalExaggeration])
  const marching = useMemo(() => {
    const material = new THREE.MeshStandardMaterial({ color: '#23d9ff', transparent: true, opacity: 0.28, roughness: 0.55, metalness: 0.05, side: THREE.DoubleSide, depthWrite: false, toneMapped: false })
    const mc = new MarchingCubes(RESOLUTION, material, false, false, 18000)
    mc.isolation = 0.5
    mc.setSize(SCENE_WIDTH, depthSpan, SCENE_DEPTH)
    return mc
  }, [depthSpan])

  useEffect(() => {
    if (!enabled || !volume) return
    marching.reset()
    marching.isolation = 0.5
    for (let i = 0; i < volume.field.length; i += 1) marching.field[i] = volume.field[i]
    marching.update()
  }, [enabled, volume, marching])

  useEffect(() => () => { marching.geometry?.dispose(); marching.material?.dispose() }, [marching])
  if (!enabled || !volume || stack.isLoading) return null
  return <primitive object={marching} position={[0, -depthSpan / 2, 0]} />
}
