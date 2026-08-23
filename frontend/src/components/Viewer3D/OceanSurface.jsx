import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { Water } from 'three-stdlib'

function makeProceduralNormals() {
  const size = 256
  const data = new Uint8Array(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const nx = Math.sin(x * 0.22) * 0.5 + Math.sin((x + y) * 0.11) * 0.5
      const ny = Math.cos(y * 0.19) * 0.5 + Math.cos((x - y) * 0.13) * 0.5
      const o = (y * size + x) * 4
      data[o] = 128 + nx * 60
      data[o + 1] = 128 + ny * 60
      data[o + 2] = 255
      data[o + 3] = 255
    }
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.needsUpdate = true
  return tex
}

export default function OceanSurface() {
  const [normalsTexture, setNormalsTexture] = useState(null)
  const waterRef = useRef(null)

  useEffect(() => {
    let disposed = false
    const loader = new THREE.TextureLoader()
    loader.setCrossOrigin('anonymous')
    loader.load(
      '/assets/waternormals.jpg',
      (tex) => {
        if (disposed) return
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping
        setNormalsTexture(tex)
      },
      undefined,
      () => setNormalsTexture(makeProceduralNormals()),
    )
    return () => {
      disposed = true
    }
  }, [])

  const geometry = useMemo(() => new THREE.PlaneGeometry(400, 260, 64, 64), [])

  const material = useMemo(() => {
    if (!normalsTexture) return null
    return new Water(geometry, {
      textureWidth: 512,
      textureHeight: 512,
      waterNormals: normalsTexture,
      sunDirection: new THREE.Vector3(0.5, 1, 0.5),
      sunColor: 0x4dd9ff,
      waterColor: 0x001e4d,
      distortionScale: 3.7,
      alpha: 0.92,
      fog: false,
    })
  }, [normalsTexture, geometry])

  useEffect(() => () => geometry.dispose(), [geometry])

  useFrame((_state, delta) => {
    if (material?.uniforms?.time != null) {
      material.uniforms.time.value += delta * 0.4
    }
    // Gentle breathing bob just above the shallowest slice.
    if (waterRef.current) {
      waterRef.current.position.y =
        -0.4 + Math.sin(performance.now() * 0.0006) * 0.15
    }
  })

  return (
    <mesh
      ref={waterRef}
      geometry={geometry}
      material={material ?? undefined}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[0, -0.4, 0]}
    >
      {!material && (
        <meshStandardMaterial
          color="#04203a"
          metalness={0.65}
          roughness={0.25}
          transparent
          opacity={0.94}
        />
      )}
    </mesh>
  )
}
