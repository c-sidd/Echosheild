import { Eye, EyeOff } from 'lucide-react'
import { useOceanStore } from '@/store/oceanStore'
import { useCurrents, useGliderStatus } from '@/hooks/useOceanData'

function Toggle({ label, checked, onChange, badge, disabled }) {
  return (
    <button onClick={disabled ? undefined : onChange} disabled={disabled} className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 transition-colors ${disabled ? 'cursor-not-allowed opacity-45' : 'hover:bg-surface/60'}`}>
      <span className="text-xs font-medium text-text-secondary">{label}</span>
      <span className="flex items-center gap-2">
        {badge && <span className="rounded-full bg-surface px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-text-muted">{badge}</span>}
        {checked ? <Eye className="h-4 w-4" style={{ color: 'var(--color-glow)' }} /> : <EyeOff className="h-4 w-4 text-text-muted" />}
      </span>
    </button>
  )
}

export default function LayerControls() {
  const showVolume = useOceanStore((s) => s.showVolume)
  const toggleShowVolume = useOceanStore((s) => s.toggleShowVolume)
  const showArgoFloats = useOceanStore((s) => s.showArgoFloats)
  const toggleShowArgoFloats = useOceanStore((s) => s.toggleShowArgoFloats)
  const showCurrents = useOceanStore((s) => s.showCurrents)
  const toggleShowCurrents = useOceanStore((s) => s.toggleShowCurrents)
  const showGlider = useOceanStore((s) => s.showGlider)
  const toggleShowGlider = useOceanStore((s) => s.toggleShowGlider)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const depth = useOceanStore((s) => s.activeDepth)
  const currentsQuery = useCurrents(datasetId, timeIndex, depth, null)
  const gliderQuery = useGliderStatus()
  const currentsAvailable = currentsQuery.data?.available === true
  const gliderConfigured = gliderQuery.data?.configured === true

  return (
    <div className="space-y-0.5">
      <Toggle label="3D Volume stack" checked={showVolume} onChange={toggleShowVolume} />
      <Toggle label="Argo Floats" checked={showArgoFloats} onChange={toggleShowArgoFloats} />
      <Toggle label="Current vectors" checked={showCurrents && currentsAvailable} onChange={toggleShowCurrents} badge={currentsAvailable ? 'Live' : 'N/A'} disabled={!currentsAvailable} />
      <Toggle label="Gliders" checked={showGlider && gliderConfigured} onChange={toggleShowGlider} badge={gliderConfigured ? 'Live' : 'N/A'} disabled={!gliderConfigured} />
    </div>
  )
}
