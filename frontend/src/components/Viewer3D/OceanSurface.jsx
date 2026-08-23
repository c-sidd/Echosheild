import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { Water } from 'three-stdlib'

function makeProceduralNormals() {
  const size = 128
  const data = new Uint8Array(size * size * 4)
  for (let y = 0; y < size; y += 1) for (let x = 0; x < size; x += 1) {
    const nx = Math.sin(x * 0.22) * 0.5 + Math.sin((x + y) * 0.11) * 0.5
    const ny = Math.cos(y * 0.19) * 0.5 + Math.cos((x - y) * 0.13) * 0.5
    const o = (y * size + x) * 4
    data[o] = 128 + nx * 60; data[o + 1] = 128 + ny * 60; data[o + 2] = 255; data[o + 3] = 255
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.needsUpdate = true
  return tex
}

export default function OceanSurface() {
  const [normalsTexture, setNormalsTexture] = useState(null)
  const waterRef = useRef(null)
  const tick = useRef(0)

  useEffect(() => {
    let disposed = false
    const loader = new THREE.TextureLoader()
    loader.setCrossOrigin('anonymous')
    loader.load('/assets/waternormals.jpg', (tex) => {
      if (disposed) { tex.dispose(); return }
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping
      setNormalsTexture(tex)
    }, undefined, () => {
      if (!disposed) setNormalsTexture(makeProceduralNormals())
    })
    return () => { disposed = true }
  }, [])

  const geometry = useMemo(() => new THREE.PlaneGeometry(400, 260, 32, 32), [])
  const water = useMemo(() => normalsTexture ? new Water(geometry, {
    textureWidth: 256,
    textureHeight: 256,
    waterNormals: normalsTexture,
    sunDirection: new THREE.Vector3(0.5, 1, 0.5),
    sunColor: 0x4dd9ff,
    waterColor: 0x001e4d,
    distortionScale: 2.5,
    alpha: 0.9,
    fog: false,
  }) : null, [normalsTexture, geometry])

  useEffect(() => () => geometry.dispose(), [geometry])
  useEffect(() => () => normalsTexture?.dispose(), [normalsTexture])
  useEffect(() => () => {
    if (!water) return
    water.material.dispose()
    water.geometry?.dispose()
  }, [water])

  useFrame((_state, delta) => {
    if (!water?.material?.uniforms?.time) return
    tick.current += delta
    if (tick.current < 1 / 30) return
    water.material.uniforms.time.value += tick.current * 0.4
    tick.current = 0
  })

  if (!water) return <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.4, 0]}><meshStandardMaterial color="#04203a" metalness={0.65} roughness={0.25} transparent opacity={0.94} /></mesh>
  return <primitive ref={waterRef} object={water} position={[0, -0.4, 0]} />
}
