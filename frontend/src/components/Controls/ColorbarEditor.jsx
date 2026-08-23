import { useEffect } from 'react'
import { RotateCcw } from 'lucide-react'
import { useOceanStore } from '@/store/oceanStore'
import { colormapCSS } from '@/utils/colorUtils'
import { unitLabel } from '@/utils/formatters'

const COLORMAPS = ['viridis', 'plasma', 'coolwarm', 'inferno', 'magma']

export default function ColorbarEditor() {
  const colormap = useOceanStore((s) => s.colormap)
  const setColormap = useOceanStore((s) => s.setColormap)
  const colorMin = useOceanStore((s) => s.colorMin)
  const colorMax = useOceanStore((s) => s.colorMax)
  const setColorRange = useOceanStore((s) => s.setColorRange)
  const resetColorRange = useOceanStore((s) => s.resetColorRange)
  const logScale = useOceanStore((s) => s.logScale)
  const setLogScale = useOceanStore((s) => s.setLogScale)

  const variables = useOceanStore((s) => s.variables)
  const activeVariable = useOceanStore((s) => s.activeVariable)
  const units = variables.find((v) => v.canonical_name === activeVariable)?.units

  // Auto range comes from data when colorMin/Max are null; show effective bounds.
  const gradient = colormapCSS(colormap)

  return (
    <div className="space-y-3">
      <div
        className="h-3 w-full rounded-full border border-[rgba(0,212,255,0.2)]"
        style={{ background: gradient }}
        title={`${colorMin ?? 'auto'} → ${colorMax ?? 'auto'} ${unitLabel(units)}`}
      />
      <div className="flex justify-between font-mono text-[10px] text-text-secondary">
        <span>{colorMin != null ? colorMin : 'min (auto)'}</span>
        <span className="text-text-muted">{unitLabel(units)}</span>
        <span>{colorMax != null ? colorMax : 'max (auto)'}</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <NumberField
          label="Min"
          value={colorMin}
          onChange={(v) => setColorRange(v, colorMax)}
        />
        <NumberField
          label="Max"
          value={colorMax}
          onChange={(v) => setColorRange(colorMin, v)}
        />
      </div>

      <div className="flex items-center gap-2">
        <select
          value={colormap}
          onChange={(e) => setColormap(e.target.value)}
          className="flex-1 rounded-md border border-[rgba(0,212,255,0.25)] bg-surface/80 px-2 py-1.5 font-mono text-xs text-text-primary outline-none focus:border-glow"
        >
          {COLORMAPS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button
          onClick={() => setLogScale(!logScale)}
          className={`rounded-md px-2 py-1.5 font-mono text-xs transition-colors ${
            logScale
              ? 'bg-glow/20 text-glow ring-1 ring-glow/50'
              : 'bg-surface/60 text-text-muted hover:text-text-secondary'
          }`}
          title={logScale ? 'Logarithmic scale' : 'Linear scale'}
        >
          {logScale ? 'log' : 'lin'}
        </button>
        <button
          onClick={() => {
            resetColorRange()
            setLogScale(false)
          }}
          className="rounded-md bg-surface/60 p-2 text-text-muted transition-colors hover:text-glow"
          title="Reset to auto range"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

function NumberField({ label, value, onChange }) {
  useEffect(() => {}, [])
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <input
        type="number"
        value={value ?? ''}
        placeholder="auto"
        onChange={(e) => {
          const raw = e.target.value
          onChange(raw === '' ? null : Number(raw))
        }}
        className="w-full rounded-md border border-[rgba(0,212,255,0.25)] bg-surface/80 px-2 py-1.5 font-mono text-xs text-text-primary outline-none placeholder:text-text-muted focus:border-glow"
      />
    </label>
  )
}
