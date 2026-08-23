import { AnimatePresence, motion } from 'framer-motion'
import { ExternalLink, Server, X, Globe, Database } from 'lucide-react'
import { useState } from 'react'
import { useOceanStore } from '@/store/oceanStore'
import { useServices } from '@/hooks/useOceanData'

// Keys mirror backend ServiceEndpoints exactly.
const SERVICE_META = [
  { key: 'opendap', label: 'OPeNDAP', icon: Database, color: '#00d4ff', desc: 'Direct data access protocol' },
  { key: 'wms', label: 'WMS', icon: Globe, color: '#3ddc84', desc: 'Web Map Service (GetMap tiles)' },
  { key: 'wcs', label: 'WCS', icon: Globe, color: '#4ecdc4', desc: 'Web Coverage Service (grids)' },
  { key: 'erddap_griddap', label: 'ERDDAP griddap', icon: Server, color: '#ffe66d', desc: 'INCOIS ERDDAP grid access' },
  { key: 'erddap_tabledap', label: 'ERDDAP tabledap', icon: Server, color: '#ffd166', desc: 'INCOIS ERDDAP in-situ queries' },
  { key: 'http_download', label: 'HTTP download', icon: ExternalLink, color: '#7fb3c8', desc: 'Direct NetCDF file download' },
  { key: 'thredds_catalog', label: 'THREDDS Catalog', icon: Server, color: '#9b8ea8', desc: 'Browse full catalog' },
]

export default function ServicesPanel() {
  const [open, setOpen] = useState(false)
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const servicesQuery = useServices(datasetId)

  const services = servicesQuery.data
  const links = services
    ? SERVICE_META.map((meta) => ({ meta, url: services[meta.key] })).filter(
        ({ url }) => typeof url === 'string' && url.length > 0,
      )
    : []

  const hasServices = links.length > 0
  const isUnavailable =
    servicesQuery.isError || (servicesQuery.isSuccess && !hasServices)

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        title="Data access services (OPeNDAP / WMS / ERDDAP)"
        className={`glass-panel pointer-events-auto absolute bottom-[8.5rem] right-[296px] z-20 flex h-9 w-9 items-center justify-center rounded-full transition-colors hover:text-glow ${
          hasServices ? '' : 'opacity-50'
        }`}
      >
        <Server className="h-4 w-4" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.aside
            key="services-panel"
            initial={{ x: 320, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 320, opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 220 }}
            className="glass-panel pointer-events-auto absolute bottom-[8.5rem] right-4 z-30 max-h-[55vh] w-[300px] overflow-y-auto"
            style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.6)' }}
          >
            <div className="flex items-center justify-between border-b border-glow/10 px-4 py-3">
              <p className="text-xs font-bold uppercase tracking-widest text-text-secondary">
                Data Access Services
              </p>
              <button
                onClick={() => setOpen(false)}
                className="rounded p-1 text-text-muted hover:text-glow"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="px-4 py-3">
              {servicesQuery.isPending && (
                <p className="text-xs text-text-muted">Checking available services…</p>
              )}

              {isUnavailable && (
                <div className="space-y-1">
                  <p className="text-xs leading-relaxed text-text-muted">
                    No external services are currently configured for this dataset.
                  </p>
                  <p className="font-mono text-[10px] text-text-muted opacity-70">
                    Start the THREDDS container to enable OPeNDAP, WMS, and WCS:
                  </p>
                  <code className="mt-1 block rounded bg-surface px-2 py-1.5 font-mono text-[10px] text-glow">
                    docker compose -f infra/docker-compose.yml up -d
                  </code>
                </div>
              )}

              {hasServices && (
                <ul className="space-y-2">
                  {links.map(({ meta, url }) => {
                    const Icon = meta.icon
                    return (
                      <li key={meta.key}>
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="group flex items-start gap-2.5 rounded-lg border border-transparent px-2.5 py-2 transition-all hover:border-glow/30 hover:bg-surface/60"
                        >
                          <Icon
                            className="mt-0.5 h-3.5 w-3.5 shrink-0"
                            style={{ color: meta.color }}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-semibold text-text-primary">
                              {meta.label}
                            </p>
                            <p className="text-[10px] text-text-muted">{meta.desc}</p>
                            <p className="mt-0.5 truncate font-mono text-[9px] text-text-muted opacity-70">
                              {url.replace(/\?.*/, '')}
                            </p>
                          </div>
                          <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                        </a>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
