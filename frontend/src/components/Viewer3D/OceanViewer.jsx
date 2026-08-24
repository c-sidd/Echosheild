import { Canvas } from '@react-three/fiber'
import { AdaptiveDpr } from '@react-three/drei'
import * as THREE from 'three'
import SceneManager from '@/components/Viewer3D/SceneManager'
import VolumeRenderer from '@/components/Viewer3D/VolumeRenderer'
import IsosurfaceRenderer from '@/components/Viewer3D/IsosurfaceRenderer'
import ViewportDataController from '@/components/Viewer3D/ViewportDataController'
import OceanSurface from '@/components/Viewer3D/OceanSurface'
import OceanFloor from '@/components/Viewer3D/OceanFloor'
import CurrentArrows from '@/components/Viewer3D/CurrentArrows'
import InstrumentMarkers from '@/components/Viewer3D/InstrumentMarkers'
import CanvasProbe from '@/components/Viewer3D/CanvasProbe'

function getMaxDpr() {
  if (typeof window === 'undefined') return 1
  const memory = Number(navigator.deviceMemory || 4)
  const cores = Number(navigator.hardwareConcurrency || 4)
  const mobile = /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent)
  if (mobile || memory <= 4 || cores <= 4) return 1
  if (memory <= 8 || cores <= 8) return 1.25
  return 1.5
}

export default function OceanViewer() {
  return (
    <div className="absolute inset-0">
      <Canvas
        camera={{ position: [0, 80, 120], fov: 45, near: 0.1, far: 2000 }}
        gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
        onCreated={({ gl }) => { gl.toneMapping = THREE.ACESFilmicToneMapping; gl.setClearColor('#020b18') }}
        dpr={[1, getMaxDpr()]}
        performance={{ min: 0.5, max: 1, debounce: 250 }}
      >
        <AdaptiveDpr pixelated />
        <SceneManager />
        <ViewportDataController />
        <OceanFloor />
        <VolumeRenderer />
        <IsosurfaceRenderer />
        <OceanSurface />
        <CurrentArrows />
        <InstrumentMarkers />
        <CanvasProbe />
      </Canvas>
    </div>
  )
}
