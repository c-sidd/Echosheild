import { useQuery } from '@tanstack/react-query'
import { GitCompareArrows, AlertTriangle } from 'lucide-react'
import { get } from '@/services/api'
import { useOceanStore } from '@/store/oceanStore'

export default function ModelComparisonPanel() {
  const selectedFloat = useOceanStore((s) => s.selectedFloat)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const wmo = selectedFloat?.platform_wmo

  const query = useQuery({
    queryKey: ['argo-comparison', wmo, datasetId],
    queryFn: ({ signal }) => get(`/argo/${wmo}/compare?dataset_id=${encodeURIComponent(datasetId)}`, { signal }),
    enabled: Number.isFinite(wmo) && !!datasetId,
    staleTime: 10 * 60 * 1000,
    retry: false,
  })

  if (!selectedFloat) return null
  if (query.isPending) return <Panel><span className="animate-pulse">Comparing model with observation…</span></Panel>
  if (query.isError) {
    return <Panel><div className="flex items-start gap-2 text-text-secondary"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><span>Comparison unavailable for this float/model pair.</span></div></Panel>
  }

  const metrics = query.data?.metrics
  return (
    <Panel>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-glow">
        <GitCompareArrows className="h-4 w-4" /> Model ↔ Argo validation
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Metric label="Temp bias" value={metrics?.temperature_bias_c} unit="°C" />
        <Metric label="Temp RMSE" value={metrics?.temperature_rmse_c} unit="°C" />
        <Metric label="Salinity bias" value={metrics?.salinity_bias_psu} unit="PSU" />
        <Metric label="Salinity RMSE" value={metrics?.salinity_rmse_psu} unit="PSU" />
      </div>
      <p className="mt-2 text-[9px] text-text-muted">
        {metrics?.temperature_count ?? 0} temperature + {metrics?.salinity_count ?? 0} salinity matched levels · nearest model timestep
      </p>
    </Panel>
  )
}

function Metric({ label, value, unit }) {
  return (
    <div className="rounded-lg border border-glow/10 bg-deep/50 px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-wide text-text-muted">{label}</p>
      <p className="font-mono text-xs text-text-primary">
        {Number.isFinite(value) ? `${value.toFixed(3)} ${unit}` : '—'}
      </p>
    </div>
  )
}

function Panel({ children }) {
  return <div className="pointer-events-auto absolute bottom-[110px] left-[360px] z-30 w-[260px] rounded-xl border border-glow/20 bg-deep/90 p-3 shadow-xl backdrop-blur">{children}</div>
}
