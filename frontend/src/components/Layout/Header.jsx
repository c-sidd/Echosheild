import { useState } from 'react'
import { motion } from 'framer-motion'
import { Waves, Database, Layers2, Activity } from 'lucide-react'
import { useOceanStore } from '@/store/oceanStore'
import SystemStatus from '@/components/UI/SystemStatus'

const STATUS_COLORS = {
  ok: '#3ddc84',
  down: '#ff5470',
}

export default function Header() {
  const datasets = useOceanStore((s) => s.datasets)
  const activeDatasetId = useOceanStore((s) => s.activeDatasetId)
  const setActiveDataset = useOceanStore((s) => s.setActiveDataset)
  const viewMode = useOceanStore((s) => s.viewMode)
  const setViewMode = useOceanStore((s) => s.setViewMode)
  const upstream503 = useOceanStore((s) => s.upstream503)
  const [statusOpen, setStatusOpen] = useState(false)

  return (
    <header className="glass-panel pointer-events-auto absolute left-4 right-4 top-4 z-30 flex items-center justify-between px-5 py-2.5">
      <div className="flex items-center gap-2.5">
        <Waves className="h-6 w-6 text-glow dot-pulse" style={{ color: 'var(--color-glow)' }} />
        <div>
          <p className="text-base font-bold leading-tight tracking-tight text-text-primary">
            Echo<span style={{ color: 'var(--color-glow)' }}>Shield</span>
          </p>
          <p className="text-[10px] uppercase tracking-widest text-text-muted">
            INCOIS · SIH PS-26067
          </p>
        </div>
      </div>

      <label className="flex items-center gap-2 text-xs text-text-secondary">
        <Database className="h-3.5 w-3.5" />
        <span className="hidden md:inline">Dataset</span>
        <select
          value={activeDatasetId ?? ''}
          onChange={(e) => setActiveDataset(e.target.value)}
          className="max-w-[260px] truncate rounded-md border border-[rgba(0,212,255,0.25)] bg-surface/80 px-2.5 py-1.5 font-mono text-xs text-text-primary outline-none focus:border-glow"
        >
          {!datasets.length && <option value="">loading…</option>}
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {(d.title ?? d.id).slice(0, 48)}
              {d.source_type === 'local' ? '' : ' (remote)'}
            </option>
          ))}
        </select>
      </label>

      <button
        onClick={() => setViewMode(viewMode === '3D' ? '2D' : '3D')}
        className="group flex items-center gap-1.5 rounded-md border border-[rgba(0,212,255,0.25)] bg-surface/80 px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors hover:text-glow"
        title="Toggle view mode"
      >
        <Layers2 className="h-3.5 w-3.5 transition-transform group-hover:scale-110" />
        {viewMode === '3D' ? '3D Volume' : '2D Map'}
      </button>

      <motion.button
        whileTap={{ scale: 0.94 }}
        onClick={() => setStatusOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md border border-[rgba(0,212,255,0.25)] bg-surface/80 px-3 py-1.5 text-xs"
      >
        <Activity className="h-3.5 w-3.5 text-text-muted" />
        <span
          className={upstream503 ? 'dot-pulse' : ''}
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: upstream503 ? STATUS_COLORS.down : STATUS_COLORS.ok,
            color: upstream503 ? STATUS_COLORS.down : STATUS_COLORS.ok,
          }}
        />
        <span className="text-text-secondary">System: {upstream503 ? '503' : 'OK'}</span>
      </motion.button>

      {statusOpen && <SystemStatus onClose={() => setStatusOpen(false)} />}
    </header>
  )
}
