import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'
import { useSliceStack } from '@/hooks/useOceanData'
import { buildLUT, valuesToTexture } from '@/utils/colorUtils'
import { depthToY, SCENE_WIDTH, SCENE_DEPTH } from '@/utils/depthUtils'

function SlicePlane({ slice, depth, isActive }) {
  const colormap = useOceanStore((s) => s.colormap)
  const colorMin = useOceanStore((s) => s.colorMin)
  const colorMax = useOceanStore((s) => s.colorMax)
  const logScale = useOceanStore((s) => s.logScale)
  const opacity = useOceanStore((s) => s.opacity)
  const verticalExaggeration = useOceanStore((s) => s.verticalExaggeration)

  const meshRef = useRef()
  const materialRef = useRef()
  const fadeRef = useRef(0)

  const latCount = slice?.latitude?.length ?? 0
  const lonCount = slice?.longitude?.length ?? 0
  const hasData = latCount > 1 && lonCount > 1 && Array.isArray(slice?.values)

  const range = useMemo(() => {
    if (!hasData) return null
    let min = Infinity
    let max = -Infinity
    for (const row of slice.values) {
      for (const v of row ?? []) {
        if (v == null || !Number.isFinite(v)) continue
        if (v < min) min = v
        if (v > max) max = v
      }
    }
    if (!Number.isFinite(min)) return null
    return { min, max }
  }, [slice])

  const autoMin = colorMin ?? range?.min ?? 0
  const autoMax = colorMax ?? range?.max ?? 1

  const lut = useMemo(
    () => buildLUT(colormap, autoMin, autoMax, logScale),
    [colormap, autoMin, autoMax, logScale],
  )

  const pixels = useMemo(() => {
    if (!hasData || !range) return null
    return valuesToTexture(
      slice.values,
      lut,
      autoMin,
      autoMax,
      lonCount,
      latCount,
      Math.round(opacity * 255),
    )
  }, [slice, lut, autoMin, autoMax, opacity])

  const texture = useMemo(() => {
    if (!pixels || !lonCount || !latCount) return null
    return new THREE.DataTexture(pixels, lonCount, latCount, THREE.RGBAFormat)
  }, [pixels, lonCount, latCount])

  useEffect(() => {
    if (!texture) return
    texture.magFilter = THREE.LinearFilter
    texture.minFilter = THREE.LinearFilter
    texture.needsUpdate = true
    return () => texture.dispose()
  }, [texture])

  const targetOpacity =
    (isActive ? Math.min(1, opacity + 0.12) : opacity * (isActive ? 1 : 0.82)) *
    (range ? 1 : 0)

  useFrame((_state, delta) => {
    const mat = materialRef.current
    if (!mat) return
    // Smooth fade toward target whenever fresh data or focus changes.
    fadeRef.current = THREE.MathUtils.damp(fadeRef.current, targetOpacity, 6, delta)
    mat.opacity = fadeRef.current
  })

  if (!texture) return null

  return (
    <group>
      <mesh
        ref={meshRef}
        position={[0, depthToY(depth, verticalExaggeration), 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        renderOrder={Math.round(depth)}
      >
        <planeGeometry args={[SCENE_WIDTH, SCENE_DEPTH]} />
        <meshBasicMaterial
          ref={materialRef}
          map={texture}
          transparent
          side={THREE.DoubleSide}
          depthWrite={false}
          opacity={0}
          toneMapped={false}
        />
      </mesh>
      {isActive && (
        <lineSegments
          position={[0, depthToY(depth, verticalExaggeration), 0]}
          rotation={[-Math.PI / 2, 0, 0]}
          renderOrder={999}
        >
          <edgesGeometry args={[new THREE.PlaneGeometry(SCENE_WIDTH, SCENE_DEPTH)]} />
          <lineBasicMaterial color="#00d4ff" transparent opacity={0.85} toneMapped={false} />
        </lineSegments>
      )}
    </group>
  )
}

export default function VolumeRenderer() {
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const variable = useOceanStore((s) => s.activeVariable)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depths = useOceanStore((s) => s.depths)
  const activeDepth = useOceanStore((s) => s.activeDepth)
  const showVolume = useOceanStore((s) => s.showVolume)

  const stack = useSliceStack(datasetId, variable, timeIndex)

  if (!showVolume || stack.isLoading || !Array.isArray(stack.data) || !depths.length) {
    return null
  }

  const slicesByDepth = new Map()
  stack.data.forEach((slice) => {
    if (slice && Number.isFinite(slice.depth_meters)) {
      slicesByDepth.set(slice.depth_meters, slice)
    }
  })

  return (
    <group>
      {depths.map((depth) => (
        <SlicePlane
          key={`${datasetId}-${variable}-${depth}`}
          slice={slicesByDepth.get(depth)}
          depth={depth}
          isActive={Math.abs(depth - activeDepth) < 1e-6}
        />
      ))}
    </group>
  )
}
