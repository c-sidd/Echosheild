import { useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'
import { makeDomainMapping, SCENE_DEPTH, SCENE_WIDTH } from '@/utils/depthUtils'

const UPDATE_MS = 500

export default function ViewportDataController() {
  const camera = useThree((s) => s.camera)
  const lastUpdate = useRef(0)
  const lastKey = useRef('')
  const direction = useRef(new THREE.Vector3())
  const bounds = useOceanStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds)

  useFrame(() => {
    if (!bounds) return
    const now = performance.now()
    if (now - lastUpdate.current < UPDATE_MS) return
    lastUpdate.current = now

    const mapping = makeDomainMapping(bounds)
    const distance = camera.position.length()
    const fraction = distance > 280 ? 1 : distance > 170 ? 0.65 : distance > 100 ? 0.4 : 0.22
    const halfLon = Math.abs(bounds.east - bounds.west) * fraction / 2
    const halfLat = Math.abs(bounds.north - bounds.south) * fraction / 2

    // OrbitControls moves the camera around a target. Camera x/z alone is
    // therefore not the geographic center of the viewport. Intersect the
    // camera's forward ray with the ocean plane instead.
    camera.getWorldDirection(direction.current)
    const dy = direction.current.y
    const t = Math.abs(dy) > 1e-4 ? -camera.position.y / dy : 0
    const hitX = t > 0 && Number.isFinite(t) ? camera.position.x + direction.current.x * t : 0
    const hitZ = t > 0 && Number.isFinite(t) ? camera.position.z + direction.current.z * t : 0
    const sceneX = Math.max(-SCENE_WIDTH / 2, Math.min(SCENE_WIDTH / 2, hitX))
    const sceneZ = Math.max(-SCENE_DEPTH / 2, Math.min(SCENE_DEPTH / 2, hitZ))
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
