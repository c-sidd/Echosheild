import { useMemo, useState } from 'react'
import { Html } from '@react-three/drei'
import { useOceanStore } from '@/store/oceanStore'
import { usePoint } from '@/hooks/useOceanData'
import {
  SCENE_WIDTH,
  SCENE_DEPTH,
  makeDomainMapping,
} from '@/utils/depthUtils'
import { formatLat, formatLon, formatValue, unitLabel } from '@/utils/formatters'

// Invisible plane just under the water surface that receives raycasted
// clicks and converts them back to lat/lon via the scene domain mapping.
export default function CanvasProbe() {
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depth = useOceanStore((s) => s.activeDepth)
  const bounds = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.spatial_bounds,
  )

  const [probe, setProbe] = useState(null) // { lat, lon, x, z }

  const mapping = useMemo(() => makeDomainMapping(bounds), [bounds])

  const handleClick = (e) => {
    e.stopPropagation()
    const lon = mapping.xToLon(e.point.x)
    const lat = mapping.zToLat(e.point.z)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    setProbe({ lat, lon, x: e.point.x, z: e.point.z })
  }

  return (
    <>
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -1, 0]}
        onClick={handleClick}
        onPointerMissed={() => setProbe(null)}
      >
        <planeGeometry args={[SCENE_WIDTH, SCENE_DEPTH]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {probe && (
        <ProbeTooltip
          key={`${probe.lat}-${probe.lon}-${timeIndex}-${depth}`}
          lat={probe.lat}
          lon={probe.lon}
          position={[probe.x, 0.5, probe.z]}
          datasetId={datasetId}
          timeIndex={timeIndex}
          depth={depth}
        />
      )}
    </>
  )
}

function ProbeTooltip({ lat, lon, position, datasetId, timeIndex, depth }) {
  const pointQuery = usePoint(
    datasetId,
    ['temperature', 'salinity'],
    lat,
    lon,
    timeIndex,
    depth,
    !!datasetId,
  )
  const values = pointQuery.data?.values ?? {}
  const units = pointQuery.data?.units ?? {}

  return (
    <Html position={position} center distanceFactor={140} zIndexRange={[20, 10]}>
      <div className="glass-panel pointer-events-none whitespace-nowrap px-3 py-2 text-[11px] font-mono">
        <p className="text-glow font-bold">
          {formatLat(lat)} · {formatLon(lon)}
        </p>
        {pointQuery.isLoading && (
          <p className="mt-0.5 text-text-muted">probing…</p>
        )}
        {!pointQuery.isLoading &&
          Object.entries(values).map(([v, val]) =>
            val != null ? (
              <p key={v} className="mt-0.5 text-text-secondary">
                {v}:{' '}
                <span className="text-text-primary">
                  {formatValue(val)} {unitLabel(units[v])}
                </span>
              </p>
            ) : null,
          )}
        <p className="mt-1 text-[9px] uppercase tracking-wider text-text-muted">
          {depth}m depth
        </p>
      </div>
    </Html>
  )
}
