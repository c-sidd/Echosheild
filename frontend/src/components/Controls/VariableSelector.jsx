import { Thermometer, Droplets, Waves, Leaf } from 'lucide-react'
import { useOceanStore } from '@/store/oceanStore'
import { canonicalLabel, unitLabel } from '@/utils/formatters'

const ICONS = {
  temperature: Thermometer,
  salinity: Droplets,
  u_current: Waves,
  v_current: Waves,
  chlorophyll: Leaf,
}

export default function VariableSelector() {
  const variables = useOceanStore((s) => s.variables)
  const activeVariable = useOceanStore((s) => s.activeVariable)
  const setActiveVariable = useOceanStore((s) => s.setActiveVariable)

  const canonicalVars = variables.filter((v) => v.canonical_name)

  if (!canonicalVars.length) {
    return <p className="text-xs text-text-muted">Loading variables…</p>
  }

  return (
    <div className="space-y-1.5">
      {canonicalVars.map((v) => {
        const Icon = ICONS[v.canonical_name] ?? Thermometer
        const isActive = v.canonical_name === activeVariable
        return (
          <button
            key={v.canonical_name + v.name}
            onClick={() => setActiveVariable(v.canonical_name)}
            className={`flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-all ${
              isActive
                ? 'border-glow/60 bg-surface'
                : 'border-transparent hover:border-glow/25 hover:bg-surface/60'
            }`}
          >
            <Icon
              className="h-4 w-4 shrink-0"
              style={{ color: isActive ? 'var(--color-glow)' : 'var(--color-text-muted)' }}
            />
            <div className="min-w-0 flex-1">
              <p
                className="truncate text-xs font-semibold"
                style={{ color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}
              >
                {canonicalLabel(v.canonical_name)}
              </p>
              <p className="truncate font-mono text-[10px] text-text-muted">
                {v.name} · {unitLabel(v.units)}
              </p>
            </div>
            {isActive && (
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full dot-pulse"
                style={{ background: 'var(--color-glow)', color: 'var(--color-glow)' }}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}
