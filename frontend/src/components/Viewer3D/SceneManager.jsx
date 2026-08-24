import { useEffect, useRef } from 'react'
import { useThree } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing'
import gsap from 'gsap'
import { useOceanStore } from '@/store/oceanStore'

export default function SceneManager() {
  const camera = useThree((s) => s.camera)
  const controlsRef = useRef()
  const bounds = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds ?? null,
  )
  const activeDepth = useOceanStore((s) => s.activeDepth)

  useEffect(() => {
    if (!bounds) return undefined
    gsap.to(camera.position, {
      x: 0,
      y: 85,
      z: 125,
      duration: 1.1,
      ease: 'power2.inOut',
      onUpdate: () => camera.lookAt(0, -10, 0),
    })
    if (controlsRef.current) {
      gsap.to(controlsRef.current.target, {
        x: 0,
        y: -12,
        z: 0,
        duration: 1.1,
        ease: 'power2.inOut',
        onUpdate: () => controlsRef.current?.update(),
      })
    }
    return () => gsap.killTweensOf([camera.position, controlsRef.current?.target].filter(Boolean))
  }, [bounds?.west, bounds?.east, bounds?.south, bounds?.north, camera])

  useEffect(() => {
    if (!controlsRef.current || !Number.isFinite(activeDepth)) return undefined
    gsap.to(controlsRef.current.target, {
      y: -(activeDepth / 2000) * 30,
      duration: 0.45,
      ease: 'power2.out',
      onUpdate: () => controlsRef.current?.update(),
    })
    return () => gsap.killTweensOf(controlsRef.current?.target)
  }, [activeDepth])

  return (
    <>
      <ambientLight intensity={0.12} color="#001a33" />
      <directionalLight position={[50, 200, 50]} intensity={0.8} color="#4dd9ff" />
      <hemisphereLight args={['#0a2a4a', '#01060e', 0.25]} />

      {/* Orientation aid only; keep the grid deliberately sparse because it
          competes with scientific layers and adds unnecessary line work. */}
      <Grid
        position={[0, 0.1, 0]}
        args={[130, 90]}
        cellSize={15}
        cellThickness={0.18}
        cellColor="#0a2a4a"
        sectionSize={45}
        sectionThickness={0.35}
        sectionColor="#0d3a5a"
        fadeDistance={150}
        fadeStrength={2}
        infiniteGrid={false}
      />

      <fog attach="fog" args={['#020b18', 220, 700]} />

      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.06}
        minDistance={30}
        maxDistance={500}
        maxPolarAngle={Math.PI / 2.1}
        target={[0, -12, 0]}
      />

      <EffectComposer multisampling={0}>
        <Bloom luminanceThreshold={0.45} luminanceSmoothing={0.9} intensity={0.65} />
        <Vignette eskil={false} offset={0.12} darkness={0.45} />
      </EffectComposer>
    </>
  )
}
