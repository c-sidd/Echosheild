import { useMemo } from 'react'
import * as THREE from 'three'
import { useOceanStore } from '@/store/oceanStore'

export default function OceanFloor() {
  const verticalExaggeration = useOceanStore((s) => s.verticalExaggeration)
  const floorY = -verticalExaggeration

  const geometry = useMemo(() => new THREE.PlaneGeometry(130, 90, 32, 32), [])

  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: '#030f1e',
        roughness: 0.95,
        metalness: 0.15,
        wireframe: false,
      }),
    [],
  )

  const gridHelper = useMemo(() => {
    const g = new THREE.GridHelper(130, 20, '#0a2a3a', '#04152a')
    g.position.y = 0.05
    return g
  }, [])

  return (
    <group position={[0, floorY, 0]}>
      <mesh geometry={geometry} material={material} rotation={[-Math.PI / 2, 0, 0]} />
      <primitive object={gridHelper} />
      {[-55, 55].map((x) =>
        [-35, 35].map((z) => (
          <mesh key={`${x}-${z}`} position={[x, verticalExaggeration / 2, z]}>
            <cylinderGeometry args={[0.08, 0.08, verticalExaggeration, 6]} />
            <meshBasicMaterial color="#0a2a3a" transparent opacity={0.6} />
          </mesh>
        )),
      )}
    </group>
  )
}
