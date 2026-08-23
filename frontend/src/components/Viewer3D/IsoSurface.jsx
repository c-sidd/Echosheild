import { useMemo } from 'react'
import { MarchingCubes } from 'three/examples/jsm/objects/MarchingCubes.js'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'
import { useSliceStack } from '@/hooks/useOceanData'
import { SCENE_DEPTH, SCENE_WIDTH, depthToY } from '@/utils/depthUtils'

const RESOLUTION = 32

export default function IsoSurface() {
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const variable = useOceanStore((s) => s.activeVariable)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depths = useOceanStore((s) => s.depths)
  const show = useOceanStore((s) => s.showIsosurface)
  const opacity = useOceanStore((s) => s.opacity)
  const colorMin = useOceanStore((s) => s.colorMin)
  const colorMax = useOceanStore((s) => s.colorMax)
  const isoValue = useOceanStore((s) => s.isoValue)
  const verticalExaggeration = useOceanStore((s) => s.verticalExaggeration)
  const stack = useSliceStack(datasetId, variable, timeIndex)

  const object = useMemo(() => {
    if (!show || !Array.isArray(stack.data) || stack.data.length < 2 || depths.length < 2) return null
    const slices = stack.data.filter((s) => s?.values?.length > 1 && s?.values?.[0]?.length > 1)
    if (slices.length < 2) return null
    const latCount = slices[0].values.length
    const lonCount = slices[0].values[0].length
    if (latCount < 2 || lonCount < 2) return null
    const finite = []
    for (const slice of slices) for (const row of slice.values) for (const value of row ?? []) if (Number.isFinite(value)) finite.push(value)
    if (!finite.length) return null
    const min = Number.isFinite(colorMin) ? colorMin : Math.min(...finite)
    const max = Number.isFinite(colorMax) ? colorMax : Math.max(...finite)
    if (!(max > min)) return null
    const target = Number.isFinite(isoValue) ? isoValue : (min + max) / 2
    const mc = new MarchingCubes(RESOLUTION, new THREE.MeshBasicMaterial({ color: '#00d4ff', transparent: true, opacity: Math.min(0.9, opacity), side: THREE.DoubleSide, toneMapped: false }), false, false)
    mc.isolation = 0
    mc.reset()
    const field = mc.field
    const sample = (x, y, z) => {
      const xi = Math.min(lonCount - 1, Math.round((x / (RESOLUTION - 1)) * (lonCount - 1)))
      const yi = Math.min(latCount - 1, Math.round((y / (RESOLUTION - 1)) * (latCount - 1)))
      const zi = Math.min(slices.length - 1, Math.round((z / (RESOLUTION - 1)) * (slices.length - 1)))
      const value = Number(slices[zi]?.values?.[yi]?.[xi])
      return Number.isFinite(value) ? value : target
    }
    const scale = max - min
    for (let z = 0; z < RESOLUTION; z++) for (let y = 0; y < RESOLUTION; y++) for (let x = 0; x < RESOLUTION; x++) field[x + y * RESOLUTION + z * RESOLUTION * RESOLUTION] = (sample(x, y, z) - target) / scale
    mc.update()
    const topY = depthToY(depths[0], verticalExaggeration)
    const bottomY = depthToY(depths[depths.length - 1], verticalExaggeration)
    mc.position.set(0, (topY + bottomY) / 2, 0)
    mc.scale.set(SCENE_WIDTH / 2, Math.max(1, Math.abs(bottomY - topY) / 2), SCENE_DEPTH / 2)
    mc.frustumCulled = false
    return mc
  }, [show, stack.data, depths, colorMin, colorMax, isoValue, opacity, verticalExaggeration])

  if (!object) return null
  return <primitive object={object} dispose={null} />
}
