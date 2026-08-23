import { useMemo } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useOceanStore } from '@/store/oceanStore'
import { usePoint } from '@/hooks/useOceanData'
import {
  canonicalLabel,
  formatDepth,
  formatLat,
  formatLon,
  formatMonthYear,
  formatValue,
  unitLabel,
} from '@/utils/formatters'

const VARIABLES = ['temperature', 'salinity']

export default function HoverInspector({ hover = null }) {
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depth = useOceanStore((s) => s.activeDepth)
  const timeRange = useOceanStore((s) => s.timeRange)
  const startISO = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.time_range?.start,
  )
  const endISO = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.time_range?.end,
  )

  const pointQuery = usePoint(
    datasetId,
    VARIABLES,
    hover?.lat,
    hover?.lon,
    timeIndex,
    depth,
    !!hover,
  )

  const currentTimeISO = useMemo(() => {
    if (!timeRange?.count || !startISO || !endISO) return null
    const start = new Date(startISO)
    const end = new Date(endISO)
    const span = end.getTime() - start.getTime()
    const frac = timeRange.count > 1 ? timeIndex / (timeRange.count - 1) : 0
    return new Date(start.getTime() + frac * span).toISOString()
  }, [timeRange, timeIndex, startISO, endISO])

  if (!hover || !pointQuery.data?.values) return null

  const values = pointQuery.data.values ?? {}
  const units = pointQuery.data.units ?? {}
  const nearest = pointQuery.data.nearest_grid ?? {}

  return (
    <AnimatePresence>
      <motion.div
        key={`${hover.lat}-${hover.lon}`}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        className="glass-panel pointer-events-none absolute z-40 px-3 py-2"
        style={{
          left: Math.min(hover.x + 14, window.innerWidth - 240),
          top: Math.min(hover.y + 14, window.innerHeight - 150),
          boxShadow: '0 6px 24px rgba(0,0,0,0.55)',
        }}
      >
        <p className="font-mono text-[11px] font-bold text-glow">
          {formatLat(nearest.latitude ?? hover.lat)} ·{' '}
          {formatLon(nearest.longitude ?? hover.lon)}
        </p>
        {VARIABLES.map((v) =>
          values[v] != null ? (
            <p key={v} className="mt-0.5 font-mono text-[10px] text-text-secondary">
              {canonicalLabel(v)}:{' '}
              <span className="text-text-primary">{formatValue(values[v])}</span>{' '}
              {unitLabel(units[v])}
            </p>
          ) : null,
        )}
        <p className="mt-1 font-mono text-[9px] uppercase tracking-wider text-text-muted">
          {formatMonthYear(currentTimeISO)} · {formatDepth(depth)}
        </p>
      </motion.div>
    </AnimatePresence>
  )
}
