import { useOceanStore } from '@/store/oceanStore'
import { colormapCSS } from '@/utils/colorUtils'
import {
  formatValue,
  canonicalLabel,
  unitLabel,
  CANONICAL_RANGES,
} from '@/utils/formatters'

export default function ColorbandLegend() {
  const colormap = useOceanStore((s) => s.colormap)
  const colorMin = useOceanStore((s) => s.colorMin)
  const colorMax = useOceanStore((s) => s.colorMax)
  const activeVariable = useOceanStore((s) => s.activeVariable)
  const variables = useOceanStore((s) => s.variables)

  const units = variables.find((v) => v.canonical_name === activeVariable)?.units
  const defaultRange = CANONICAL_RANGES[activeVariable] ?? { min: 0, max: 1 }
  const lo = colorMin ?? defaultRange.min
  const hi = colorMax ?? defaultRange.max

  const ticks = [
    lo,
    lo + (hi - lo) * 0.25,
    lo + (hi - lo) * 0.5,
    lo + (hi - lo) * 0.75,
    hi,
  ]

  return (
    <div className="glass-panel pointer-events-none absolute bottom-20 left-[70px] z-20 w-[180px] px-3 py-2">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-text-secondary">
        {canonicalLabel(activeVariable)} {unitLabel(units) ? `(${unitLabel(units)})` : ''}
      </p>
      <div
        className="h-3 w-full rounded-full"
        style={{ background: colormapCSS(colormap) }}
      />
      <div className="mt-1 flex justify-between font-mono text-[9px] text-text-muted">
        {ticks.map((t, i) => (
          <span key={i}>{formatValue(t, 1)}</span>
        ))}
      </div>
    </div>
  )
}
