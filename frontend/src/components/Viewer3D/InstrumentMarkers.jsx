import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'
import { useArgoFloats } from '@/hooks/useOceanData'
import { makeDomainMapping } from '@/utils/depthUtils'

const SURFACE_Y = 0.6
const MAX_FLOATS = 80

function FloatMarker({ floatData, lonToX, latToZ }) {
  const selectedFloat = useOceanStore((s) => s.selectedFloat)
  const setSelectedFloat = useOceanStore((s) => s.setSelectedFloat)
  const [lat, lon] = floatData.last_location
  const x = lonToX(lon)
  const z = latToZ(lat)
  const isSelected = selectedFloat?.platform_wmo === floatData.platform_wmo

  return (
    <group position={[x, SURFACE_Y, z]}>
      <mesh
        onClick={(e) => {
          e.stopPropagation()
          setSelectedFloat(floatData)
        }}
      >
        <sphereGeometry args={[isSelected ? 1.15 : 0.72, 12, 12]} />
        <meshStandardMaterial
          color="#00303f"
          emissive="#00ffff"
          emissiveIntensity={isSelected ? 3 : 1.5}
          toneMapped={false}
        />
      </mesh>
      {isSelected && <PulseRing />}
    </group>
  )
}

function PulseRing() {
  const ref = useRef()
  const t = useRef(0)
  useFrame((_state, delta) => {
    if (!ref.current) return
    t.current += delta
    const s = (Math.sin(t.current * 4) + 1) / 2
    ref.current.scale.setScalar(1 + s * 1.5)
    ref.current.material.opacity = 0.5 * (1 - s)
  })
  return (
    <sprite ref={ref} scale={1.2}>
      <spriteMaterial color="#00d4ff" transparent opacity={0.35} depthWrite={false} toneMapped={false} />
    </sprite>
  )
}

export default function InstrumentMarkers() {
  const show = useOceanStore((s) => s.showArgoFloats)
  const bounds = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds,
  )
  const floatsQuery = useArgoFloats()
  const mapping = useMemo(() => makeDomainMapping(bounds), [bounds])
  const floats = useMemo(() => {
    const data = floatsQuery.data
    return Array.isArray(data) ? data.slice(0, MAX_FLOATS) : []
  }, [floatsQuery.data])

  if (!show || !floatsQuery.isSuccess || !floats.length || floatsQuery.isError) return null

  return (
    <group>
      {floats.map((f, i) => (
        <PopIn key={f.platform_wmo} delay={Math.min(i * 25, 1200)}>
          <FloatMarker floatData={f} lonToX={mapping.lonToX} latToZ={mapping.latToZ} />
        </PopIn>
      ))}
    </group>
  )
}

function PopIn({ delay, children }) {
  const groupRef = useRef()
  const startedAt = useRef(null)
  useFrame(() => {
    if (!groupRef.current) return
    const now = performance.now()
    if (startedAt.current == null) {
      startedAt.current = now + delay
      groupRef.current.scale.setScalar(0.001)
    }
    const t = THREE.MathUtils.clamp((now - startedAt.current) / 300, 0, 1)
    if (t > 0) groupRef.current.scale.setScalar(1 - (1 - t) ** 3)
  })
  return <group ref={groupRef}>{children}</group>
}

export function WmoLabel({ wmo, position }) {
  return (
    <Html position={position} center distanceFactor={120}>
      <div className="rounded-md border border-[rgba(0,212,255,0.4)] bg-deep/90 px-2 py-1 font-mono text-[10px] text-glow">
        WMO {wmo}
      </div>
    </Html>
  )
}
