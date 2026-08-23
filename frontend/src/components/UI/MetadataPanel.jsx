import { AnimatePresence, motion } from 'framer-motion'
import { Info, X, Globe, Clock, Database, Layers } from 'lucide-react'
import { useState } from 'react'
import { useOceanStore } from '@/store/oceanStore'
import {
  formatDate,
  formatDepth,
  formatLat,
  formatLon,
} from '@/utils/formatters'
import { useMetadata } from '@/hooks/useOceanData'

export default function MetadataPanel() {
  const [open, setOpen] = useState(false)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const metaQuery = useMetadata(datasetId)
  const md = metaQuery.data
  const institution =
    md?.global_attributes?.institution ?? md?.institution ?? md?.provider

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        className="glass-panel pointer-events-auto absolute bottom-24 right-[296px] z-20 flex h-9 w-9 items-center justify-center rounded-full transition-colors hover:text-glow"
        title="Dataset metadata"
      >
        <Info className="h-4 w-4" />
      </button>

      <AnimatePresence>
        {open && md && (
          <motion.aside
            initial={{ x: 320, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 320, opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 220 }}
            className="glass-panel pointer-events-auto absolute bottom-24 right-4 z-30 max-h-[60vh] w-[300px] overflow-y-auto"
          >
            <div className="flex items-center justify-between border-b border-glow/10 px-4 py-3">
              <p className="text-xs font-bold uppercase tracking-widest text-text-secondary">
                Dataset Info
              </p>
              <button
                onClick={() => setOpen(false)}
                className="rounded p-1 text-text-muted hover:text-glow"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="space-y-3 px-4 py-3 text-[11px]">
              <Row icon={Database} label="Title" value={md.title} />
              <Row icon={Globe} label="Institution" value={institution ?? '—'} />
              {(md.summary || md.abstract) && (
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-wider text-text-muted">
                    Abstract
                  </p>
                  <p className="leading-relaxed text-text-secondary">
                    {md.summary ?? md.abstract}
                  </p>
                </div>
              )}
              {md.spatial_bounds && (
                <Row
                  icon={Globe}
                  label="Domain"
                  value={`${formatLat(md.spatial_bounds.south)}–${formatLat(
                    md.spatial_bounds.north,
                  )} · ${formatLon(md.spatial_bounds.west)}–${formatLon(
                    md.spatial_bounds.east,
                  )}`}
                />
              )}
              {md.time_range && (
                <Row
                  icon={Clock}
                  label="Period"
                  value={`${formatDate(md.time_range.start)} → ${formatDate(
                    md.time_range.end,
                  )} (${md.time_range.count} steps)`}
                />
              )}
              {md.depth_range && (
                <Row
                  icon={Layers}
                  label="Depth"
                  value={`${formatDepth(md.depth_range.min_meters)} – ${formatDepth(
                    md.depth_range.max_meters,
                  )}`}
                />
              )}
              {md.license && <Row icon={Database} label="License" value={md.license} />}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}

function Row({ icon: Icon, label, value }) {
  return (
    <div className="flex gap-2">
      <Icon className="mt-0.5 h-3 w-3 shrink-0 text-text-muted" />
      <div>
        <span className="text-text-muted">{label}: </span>
        <span className="text-text-primary">{value}</span>
      </div>
    </div>
  )
}
