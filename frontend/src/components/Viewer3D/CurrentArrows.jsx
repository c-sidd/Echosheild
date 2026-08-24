import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'
import { useCurrents } from '@/hooks/useOceanData'
import { makeDomainMapping, depthToY, SCENE_HALF_W, SCENE_HALF_D } from '@/utils/depthUtils'

const MAX_PARTICLES = 1600
const UPDATE_INTERVAL = 1 / 30

export default function CurrentArrows() {
  const show = useOceanStore((s) => s.showCurrents)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depth = useOceanStore((s) => s.activeDepth)
  const bbox = useOceanStore((s) => s.bbox)
  const verticalExaggeration = useOceanStore((s) => s.verticalExaggeration)
  const currentsQuery = useCurrents(show ? datasetId : null, timeIndex, depth, bbox)
  if (!show || !currentsQuery.data?.available) return null
  return <Particles field={currentsQuery.data} verticalExaggeration={verticalExaggeration} />
}

function Particles({ field, verticalExaggeration }) {
  const bounds = useOceanStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds)
  const mapping = useMemo(() => makeDomainMapping(bounds), [bounds])
  const tickRef = useRef(0)
  const particles = useMemo(() => {
    const { latitude, longitude, u, v } = field
    if (!latitude?.length || !longitude?.length || !u?.length || !v?.length) return null
    const validCells = []
    for (let i = 0; i < latitude.length; i += 1) for (let j = 0; j < longitude.length; j += 1) {
      const ui = u[i]?.[j]; const vi = v[i]?.[j]
      if (Number.isFinite(ui) && Number.isFinite(vi)) validCells.push([i, j, ui, vi])
    }
    if (!validCells.length) return null
    const count = Math.min(validCells.length, MAX_PARTICLES)
    const positions = new Float32Array(count * 3)
    const velocities = new Float32Array(count * 2)
    for (let k = 0; k < count; k += 1) {
      const [i, j, ui, vi] = validCells[Math.min(validCells.length - 1, Math.floor((k * validCells.length) / count))]
      positions[k * 3] = mapping.lonToX(longitude[j]); positions[k * 3 + 1] = depthToY(Number.isFinite(field.depth_meters) ? field.depth_meters : 0, verticalExaggeration); positions[k * 3 + 2] = mapping.latToZ(latitude[i])
      velocities[k * 2] = ui; velocities[k * 2 + 1] = vi
    }
    return { count, positions, velocities }
  }, [field, mapping, verticalExaggeration])
  const pointsRef = useRef()
  const geometry = useMemo(() => {
    if (!particles) return null
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(particles.positions, 3))
    geo.setAttribute('velocity', new THREE.BufferAttribute(particles.velocities, 2))
    return geo
  }, [particles])
  const material = useMemo(() => particles ? new THREE.PointsMaterial({ size: 1.4, transparent: true, opacity: 0.82, color: new THREE.Color('#ffe66d'), depthWrite: false, toneMapped: false }) : null, [particles])
  useFrame((_state, delta) => {
    if (!pointsRef.current || !geometry || !particles) return
    tickRef.current += delta
    if (tickRef.current < UPDATE_INTERVAL) return
    const step = tickRef.current; tickRef.current = 0
    const posAttr = geometry.attributes.position; const vel = geometry.attributes.velocity.array; const arr = posAttr.array; const scale = 2600 * step
    for (let k = 0; k < particles.count; k += 1) {
      arr[k * 3] += vel[k * 2] * scale; arr[k * 3 + 2] -= vel[k * 2 + 1] * scale
      if (arr[k * 3] > SCENE_HALF_W) arr[k * 3] = -SCENE_HALF_W
      if (arr[k * 3] < -SCENE_HALF_W) arr[k * 3] = SCENE_HALF_W
      if (arr[k * 3 + 2] > SCENE_HALF_D) arr[k * 3 + 2] = -SCENE_HALF_D
      if (arr[k * 3 + 2] < -SCENE_HALF_D) arr[k * 3 + 2] = SCENE_HALF_D
    }
    posAttr.needsUpdate = true
  })
  if (!geometry || !material) return null
  return <points ref={pointsRef} geometry={geometry} material={material} frustumCulled={false} />
}
