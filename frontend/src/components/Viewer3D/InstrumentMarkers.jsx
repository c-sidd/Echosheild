import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'
import { useArgoFloats, useGliderMissions } from '@/hooks/useOceanData'
import { makeDomainMapping } from '@/utils/depthUtils'

const SURFACE_Y = 0.6

function FloatMarker({ floatData, lonToX, latToZ }) {
  const selectedFloat = useOceanStore((s) => s.selectedFloat)
  const setSelectedFloat = useOceanStore((s) => s.setSelectedFloat)
  const [lat, lon] = floatData.last_location
  const x = lonToX(lon); const z = latToZ(lat)
  const isSelected = selectedFloat?.platform_wmo === floatData.platform_wmo
  return (
    <group position={[x, SURFACE_Y, z]}>
      <mesh onClick={(e) => { e.stopPropagation(); setSelectedFloat(floatData) }}>
        <sphereGeometry args={[isSelected ? 1.2 : 0.8, 16, 16]} />
        <meshStandardMaterial color="#00303f" emissive="#00ffff" emissiveIntensity={isSelected ? 3 : 1.8} toneMapped={false} />
      </mesh>
      <pointLight color="#00ffff" intensity={isSelected ? 4 : 1.5} distance={12} />
      <PulseRing active={isSelected} />
    </group>
  )
}

function GliderMarker({ mission, lonToX, latToZ }) {
  if (!Number.isFinite(mission?.latitude) || !Number.isFinite(mission?.longitude)) return null
  const x = lonToX(mission.longitude); const z = latToZ(mission.latitude)
  return (
    <group position={[x, SURFACE_Y - 0.2, z]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <octahedronGeometry args={[1.1, 0]} />
        <meshStandardMaterial color="#6d3cff" emissive="#b48cff" emissiveIntensity={2.2} toneMapped={false} />
      </mesh>
      <Html position={[0, 2.2, 0]} center distanceFactor={120}>
        <div className="rounded-md border border-violet-400/40 bg-deep/90 px-2 py-1 font-mono text-[10px] text-violet-200">
          GLIDER {mission.mission_id}
        </div>
      </Html>
    </group>
  )
}

function PulseRing({ active }) {
  const ringRef = useMemo(() => ({ t: Math.random() * Math.PI * 2 }), [])
  const ref = useRef()
  useFrame(() => {
    if (!ref.current) return
    ringRef.t += 0.02
    const s = (Math.sin(ringRef.t) + 1) / 2
    ref.current.scale.setScalar(1 + s * 1.6)
    ref.current.material.opacity = (active ? 0.5 : 0.25) * (1 - s)
  })
  return <sprite ref={ref}><spriteMaterial color="#00d4ff" transparent opacity={0.3} depthWrite={false} toneMapped={false} /></sprite>
}

export default function InstrumentMarkers() {
  const showArgo = useOceanStore((s) => s.showArgoFloats)
  const showGlider = useOceanStore((s) => s.showGlider)
  const bounds = useOceanStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds)
  const floatsQuery = useArgoFloats(bounds)
  const gliderQuery = useGliderMissions(showGlider)
  const mapping = useMemo(() => makeDomainMapping(bounds), [bounds])
  const floats = useMemo(() => Array.isArray(floatsQuery.data) ? floatsQuery.data.slice(0, 120) : [], [floatsQuery.data])
  const gliders = useMemo(() => Array.isArray(gliderQuery.data) ? gliderQuery.data.slice(0, 100) : [], [gliderQuery.data])

  return (
    <group>
      {showArgo && floatsQuery.isSuccess && floats.map((f, i) => (
        <PopIn key={`argo-${f.platform_wmo}`} delay={Math.min(i * 40, 2000)}>
          <FloatMarker floatData={f} lonToX={mapping.lonToX} latToZ={mapping.latToZ} />
        </PopIn>
      ))}
      {showGlider && gliderQuery.isSuccess && gliders.map((g) => (
        <GliderMarker key={`glider-${g.mission_id}`} mission={g} lonToX={mapping.lonToX} latToZ={mapping.latToZ} />
      ))}
    </group>
  )
}

function PopIn({ delay, children }) {
  const groupRef = useRef(); const startedAt = useRef(null)
  useFrame(() => {
    if (!groupRef.current) return
    const now = performance.now()
    if (startedAt.current == null) { startedAt.current = now + delay; groupRef.current.scale.setScalar(0.001) }
    const t = THREE.MathUtils.clamp((now - startedAt.current) / 400, 0, 1)
    if (t > 0) groupRef.current.scale.setScalar(1 - Math.pow(1 - t, 3))
  })
  return <group ref={groupRef}>{children}</group>
}

export function WmoLabel({ wmo, position }) {
  return <Html position={position} center distanceFactor={120}><div className="rounded-md border border-[rgba(0,212,255,0.4)] bg-deep/90 px-2 py-1 font-mono text-[10px] text-glow">WMO {wmo}</div></Html>
}
