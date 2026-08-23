import { motion } from 'framer-motion'
import { CheckCircle2, XCircle, MinusCircle } from 'lucide-react'
import { useHealth, useReadiness } from '@/hooks/useOceanData'

export default function SystemStatus({ onClose }) {
  const healthQuery = useHealth()
  const readinessQuery = useReadiness()

  const health = healthQuery.data
  const checks = Array.isArray(readinessQuery.data?.checks) ? readinessQuery.data.checks : []

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: -8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: -8 }}
      className="glass-panel absolute right-16 top-full z-50 mt-2 w-[300px] px-4 py-3"
      style={{ boxShadow: '0 10px 44px rgba(0,0,0,0.6)' }}
      onMouseLeave={onClose}
    >
      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-text-secondary">
        System Status
      </p>

      <div className="mb-2 space-y-1 font-mono text-[10px]">
        <Row k="service" v={health?.service ?? '—'} />
        <Row k="version" v={health?.version ?? '—'} />
        <Row k="env" v={health?.environment ?? '—'} />
        <Row
          k="thredds"
          v={
            health == null
              ? '…'
              : health.thredds_configured
                ? 'configured'
                : 'not configured'
          }
        />
      </div>

      {checks.length > 0 && (
        <>
          <p className="mb-1.5 mt-3 border-t border-glow/10 pt-2 text-[10px] font-bold uppercase tracking-widest text-text-secondary">
            Readiness
          </p>
          <ul className="space-y-1">
            {checks.map((c) => (
              <li key={c.name} className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[10px] text-text-secondary">
                  {c.name}
                </span>
                <span className="flex items-center gap-1">
                  <span className="font-mono text-[9px] uppercase text-text-muted">
                    {c.status}
                  </span>
                  {c.status === 'ok' ? (
                    <CheckCircle2 className="h-3 w-3" style={{ color: '#3ddc84' }} />
                  ) : c.status === 'unavailable' ? (
                    <XCircle className="h-3 w-3" style={{ color: '#ff5470' }} />
                  ) : (
                    <MinusCircle className="h-3 w-3 text-text-muted" />
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </motion.div>
  )
}

function Row({ k, v }) {
  return (
    <p className="flex justify-between gap-3">
      <span className="text-text-muted">{k}</span>
      <span className="truncate text-text-secondary">{v}</span>
    </p>
  )
}
