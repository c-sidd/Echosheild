import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import SceneManager from '@/components/Viewer3D/SceneManager'
import VolumeRenderer from '@/components/Viewer3D/VolumeRenderer'
import IsoSurface from '@/components/Viewer3D/IsoSurface'
import OceanSurface from '@/components/Viewer3D/OceanSurface'
import CurrentArrows from '@/components/Viewer3D/CurrentArrows'
import InstrumentMarkers from '@/components/Viewer3D/InstrumentMarkers'

export default function OceanViewer() {
  return (
    <div className="absolute inset-0">
      <Canvas camera={{ position: [0, 80, 120], fov: 45, near: 0.1, far: 2000 }} gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }} onCreated={({ gl }) => { gl.toneMapping = THREE.ACESFilmicToneMapping; gl.setClearColor('#020b18') }} dpr={[1, 2]}>
        <SceneManager />
        <VolumeRenderer />
        <IsoSurface />
        <OceanSurface />
        <CurrentArrows />
        <InstrumentMarkers />
      </Canvas>
    </div>
  )
}
