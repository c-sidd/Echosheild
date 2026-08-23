import { useMemo, useState } from 'react'
import { DeckGL } from '@deck.gl/react'
import { BitmapLayer, ScatterplotLayer } from '@deck.gl/layers'
import { TileLayer } from '@deck.gl/geo-layers'
import { HeatmapLayer } from '@deck.gl/aggregation-layers'
import { useOceanStore } from '@/store/oceanStore'
import { useSlice, useArgoFloats } from '@/hooks/useOceanData'
import { COLORMAPS } from '@/utils/colorUtils'
import HoverInspector from '@/components/UI/HoverInspector'

const INITIAL_VIEW = {
  longitude: 75,
  latitude: 8,
  zoom: 3.4,
  minZoom: 2,
  maxZoom: 12,
  pitch: 25,
  bearing: 0,
}

function colormapToColorRange(colormap) {
  const stops = COLORMAPS[colormap] ?? COLORMAPS.viridis
  return stops.map(([r, g, b]) => [r, g, b])
}

export default function OceanMap() {
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const variable = useOceanStore((s) => s.activeVariable)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depth = useOceanStore((s) => s.activeDepth)
  const colormap = useOceanStore((s) => s.colormap)
  const setSelectedFloat = useOceanStore((s) => s.setSelectedFloat)
  const showArgoFloats = useOceanStore((s) => s.showArgoFloats)

  const [hover, setHover] = useState(null)

  const sliceQuery = useSlice(datasetId, variable, timeIndex, depth, null)
  const argoQuery = useArgoFloats()

  const heatPoints = useMemo(() => {
    const slice = sliceQuery.data
    if (!slice?.values || !slice.latitude?.length || !slice.longitude?.length) {
      return []
    }
    let min = Infinity
    let max = -Infinity
    for (const row of slice.values) {
      for (const v of row ?? []) {
        if (v == null || !Number.isFinite(v)) continue
        if (v < min) min = v
        if (v > max) max = v
      }
    }
    if (!Number.isFinite(min)) return []
    const span = max - min || 1
    const points = []
    for (let i = 0; i < slice.latitude.length; i++) {
      for (let j = 0; j < slice.longitude.length; j++) {
        const v = slice.values[i]?.[j]
        if (v == null || !Number.isFinite(v)) continue
        points.push({
          position: [slice.longitude[j], slice.latitude[i]],
          weight: (v - min) / span,
        })
      }
    }
    return points
  }, [sliceQuery.data])

  const floats = useMemo(
    () => (Array.isArray(argoQuery.data) ? argoQuery.data : []),
    [argoQuery.data],
  )

  const layers = [
    new TileLayer({
      id: 'dark-ocean-base',
      data: 'https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png',
      minZoom: 0,
      maxZoom: 19,
      tileSize: 256,
      renderSubLayers: (props) => {
        const { boundingBox } = props.tile
        return new BitmapLayer(props, {
          data: undefined,
          image: props.data,
          bounds: [
            boundingBox[0][0],
            boundingBox[0][1],
            boundingBox[1][0],
            boundingBox[1][1],
          ],
        })
      },
      visible: true,
    }),
    heatPoints.length > 0 &&
      new HeatmapLayer({
        id: 'slice-heat',
        data: heatPoints,
        getPosition: (d) => d.position,
        getWeight: (d) => d.weight,
        radiusPixels: 40,
        intensity: 1.4,
        threshold: 0.04,
        colorRange: colormapToColorRange(colormap),
        opacity: 0.75,
        pickable: true,
        onHover: ({ coordinate, x, y }) =>
          setHover(
            coordinate ? { lat: coordinate[1], lon: coordinate[0], x, y } : null,
          ),
      }),
    showArgoFloats &&
      floats.length > 0 &&
      new ScatterplotLayer({
        id: 'argo-floats',
        data: floats,
        pickable: true,
        getPosition: (d) => [d.last_location[1], d.last_location[0]],
        getRadius: 15000,
        getFillColor: [0, 212, 255, 210],
        getLineColor: [0, 80, 110, 255],
        stroked: true,
        lineWidthMinPixels: 1.5,
        radiusMinPixels: 6,
        radiusMaxPixels: 18,
        onClick: ({ object }) => object && setSelectedFloat(object),
        onHover: ({ object, x, y }) =>
          setHover(
            object
              ? { float: object, lat: object.last_location[0], lon: object.last_location[1], x, y }
              : null,
          ),
      }),
  ].filter(Boolean)

  return (
    <div className="absolute inset-0">
      <DeckGL
        initialViewState={INITIAL_VIEW}
        controller={{ dragRotate: true }}
        layers={layers}
        getTooltip={({ object }) =>
          object?.platform_wmo
            ? { text: `Argo WMO ${object.platform_wmo} · ${object.cycles} cycles`, style: darkTipStyle() }
            : null
        }
      />
      <HoverInspector hover={hover} />
    </div>
  )
}

export function darkTipStyle() {
  return {
    backgroundColor: 'rgba(4, 23, 40, 0.92)',
    border: '1px solid rgba(0,212,255,0.35)',
    borderRadius: '8px',
    color: '#e8f4f8',
    fontFamily: 'JetBrains Mono, monospace',
    fontSize: '11px',
    padding: '6px 10px',
  }
}
