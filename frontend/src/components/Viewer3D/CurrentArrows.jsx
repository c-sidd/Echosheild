import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'
import { useCurrents } from '@/hooks/useOceanData'
import { buildLUT } from '@/utils/colorUtils'
import {
  makeDomainMapping,
  depthToY,
  SCENE_HALF_W,
  SCENE_HALF_D,
} from '@/utils/depthUtils'

export default function CurrentArrows() {
  const show = useOceanStore((s) => s.showCurrents)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depth = useOceanStore((s) => s.activeDepth)
  const verticalExaggeration = useOceanStore((s) => s.verticalExaggeration)
  const currentsQuery = useCurrents(show ? datasetId : null, timeIndex, depth, null)

  if (!show || !currentsQuery.data?.available) return null

  return <Particles field={currentsQuery.data} verticalExaggeration={verticalExaggeration} />
}

function Particles({ field, verticalExaggeration }) {
  const bounds = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds,
  )

  const mapping = useMemo(() => makeDomainMapping(bounds), [bounds])

  const particles = useMemo(() => {
    const { latitude, longitude, u, v, max_speed_ms } = field
    if (!latitude?.length || !longitude?.length || !u?.length || !v?.length) return null

    const count = Math.min(latitude.length * longitude.length, 5000)
    const positions = new Float32Array(count * 3)
    const velocities = new Float32Array(count * 2)

    for (let k = 0; k < count; k++) {
      const i = Math.floor(Math.random() * latitude.length)
      const j = Math.floor(Math.random() * longitude.length)
      positions[k * 3] = mapping.lonToX(longitude[j])
      positions[k * 3 + 1] = depthToY(Number.isFinite(field.depth_meters) ? field.depth_meters : 0, verticalExaggeration)
      positions[k * 3 + 2] = mapping.latToZ(latitude[i])
      const ui = u[i]?.[j] ?? 0
      const vi = v[i]?.[j] ?? 0
      velocities[k * 2] = Number.isFinite(ui) ? ui : 0
      velocities[k * 2 + 1] = Number.isFinite(vi) ? vi : 0
    }
    return { count, positions, velocities, maxSpeed: max_speed_ms || 0.4 }
  }, [field, mapping])

  const pointsRef = useRef()
  const lut = useMemo(() => buildLUT('coolwarm', 0, particles?.maxSpeed ?? 0.4), [particles])

  const geometry = useMemo(() => {
    if (!particles) return null
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(particles.positions, 3))
    geo.setAttribute('velocity', new THREE.BufferAttribute(particles.velocities, 2))
    return geo
  }, [particles])

  const material = useMemo(() => {
    if (!lut) return null
    return new THREE.PointsMaterial({
      size: 1.4,
      vertexColors: false,
      transparent: true,
      opacity: 0.85,
      color: new THREE.Color('#ffe66d'),
      depthWrite: false,
      toneMapped: false,
    })
  }, [lut])

  useFrame((_state, delta) => {
    if (!pointsRef.current || !geometry || !particles) return
    const posAttr = geometry.attributes.position
    const vel = geometry.attributes.velocity.array
    const arr = posAttr.array
    const scale = 2600 * delta

    for (let k = 0; k < particles.count; k++) {
      arr[k * 3] += vel[k * 2] * scale
      arr[k * 3 + 2] -= vel[k * 2 + 1] * scale
      // Wrap within scene bounds.
      if (arr[k * 3] > SCENE_HALF_W) arr[k * 3] = -SCENE_HALF_W
      if (arr[k * 3] < -SCENE_HALF_W) arr[k * 3] = SCENE_HALF_W
      if (arr[k * 3 + 2] > SCENE_HALF_D) arr[k * 3 + 2] = -SCENE_HALF_D
      if (arr[k * 3 + 2] < -SCENE_HALF_D) arr[k * 3 + 2] = SCENE_HALF_D
    }
    posAttr.needsUpdate = true
  })

  if (!geometry || !material) return null

  return (
    <points ref={pointsRef} geometry={geometry} material={material} frustumCulled={false} />
  )
}
