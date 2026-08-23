import { useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useOceanStore } from '@/store/oceanStore'
import { makeDomainMapping, SCENE_HALF_D, SCENE_HALF_W } from '@/utils/depthUtils'

const UPDATE_MS = 500

export default function ViewportDataController() {
  const camera = useThree((s) => s.camera)
  const lastUpdate = useRef(0)
  const lastKey = useRef('')
  const bounds = useOceanStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds)

  useFrame(() => {
    if (!bounds) return
    const now = performance.now()
    if (now - lastUpdate.current < UPDATE_MS) return
    lastUpdate.current = now
    const mapping = makeDomainMapping(bounds)
    const distance = camera.position.length()
    const fraction = distance > 280 ? 1 : distance > 170 ? 0.65 : distance > 100 ? 0.4 : 0.22
    const halfLon = (bounds.east - bounds.west) * fraction / 2
    const halfLat = (bounds.north - bounds.south) * fraction / 2
    const sceneX = Math.max(-SCENE_HALF_W, Math.min(SCENE_HALF_W, camera.position.x))
    const sceneZ = Math.max(-SCENE_HALF_D, Math.min(SCENE_HALF_D, camera.position.z))
    const centerLon = mapping.xToLon(sceneX)
    const centerLat = mapping.zToLat(sceneZ)
    const west = Math.max(bounds.west, centerLon - halfLon)
    const east = Math.min(bounds.east, centerLon + halfLon)
    const south = Math.max(bounds.south, centerLat - halfLat)
    const north = Math.min(bounds.north, centerLat + halfLat)
    if (east <= west || north <= south) return
    const key = [west, east, south, north].map((v) => v.toFixed(2)).join(':')
    if (key === lastKey.current) return
    lastKey.current = key
    useOceanStore.getState().setBbox({ west, east, south, north })
  })

  return null
}
