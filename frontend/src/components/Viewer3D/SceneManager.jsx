import { useEffect, useRef } from 'react'
import { useThree } from '@react-three/fiber'
import { OrbitControls, Stars } from '@react-three/drei'
import {
  EffectComposer,
  Bloom,
  DepthOfField,
  ChromaticAberration,
  Vignette,
  Noise,
} from '@react-three/postprocessing'
import gsap from 'gsap'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'

export default function SceneManager() {
  const camera = useThree((s) => s.camera)
  const controlsRef = useRef()
  const bounds = useOceanStore(
    (s) =>
      s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds ?? null,
  )
  const activeDepth = useOceanStore((s) => s.activeDepth)

  // Smooth fly-to the dataset domain center on load / dataset switch.
  useEffect(() => {
    if (!bounds) return
    gsap.to(camera.position, {
      x: 0,
      y: 85,
      z: 125,
      duration: 1.6,
      ease: 'power3.inOut',
      onUpdate: () => camera.lookAt(0, -10, 0),
    })
    if (controlsRef.current) {
      gsap.to(controlsRef.current.target, {
        x: 0,
        y: -12,
        z: 0,
        duration: 1.6,
        ease: 'power3.inOut',
        onUpdate: () => controlsRef.current?.update(),
      })
    }
  }, [bounds?.west, bounds?.east, bounds?.south, bounds?.north])

  // Subtle camera tilt when navigating depth.
  useEffect(() => {
    if (!controlsRef.current) return
    gsap.to(controlsRef.current.target, {
      y: -(activeDepth / 2000) * 50 * 0.6,
      duration: 0.7,
      ease: 'power2.out',
      onUpdate: () => controlsRef.current?.update(),
    })
  }, [activeDepth])

  return (
    <>
      <ambientLight intensity={0.1} color="#001a33" />
      <directionalLight
        position={[50, 200, 50]}
        intensity={0.8}
        color="#4dd9ff"
        castShadow
      />
      <pointLight position={[0, -20, 0]} intensity={2} color="#006699" distance={300} />
      <hemisphereLight args={['#0a2a4a', '#01060e', 0.25]} />

      <Stars radius={300} depth={60} count={3000} factor={4} saturation={0} fade speed={0.6} />

      <fog attach="fog" args={['#020b18', 220, 700]} />

      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.05}
        minDistance={30}
        maxDistance={500}
        maxPolarAngle={Math.PI / 2.1}
        target={[0, -12, 0]}
      />

      <EffectComposer>
        <Bloom luminanceThreshold={0.3} luminanceSmoothing={0.9} intensity={1.2} />
        <DepthOfField focusDistance={0} focalLength={0.02} bokehScale={2} />
        <ChromaticAberration offset={new THREE.Vector2(0.0005, 0.0005)} radialModulation={false} modulationOffset={0} />
        <Vignette eskil={false} offset={0.1} darkness={0.8} />
        <Noise opacity={0.03} />
      </EffectComposer>
    </>
  )
}
