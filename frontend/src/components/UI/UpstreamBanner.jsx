import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, X, RefreshCw } from 'lucide-react'
import { useOceanStore } from '@/store/oceanStore'
import { useReadiness } from '@/hooks/useOceanData'

const COUNTDOWN_SECONDS = 30

export default function UpstreamBanner() {
  const upstream503 = useOceanStore((s) => s.upstream503)
  const message = useOceanStore((s) => s.upstream503Message)
  const setUpstream503 = useOceanStore((s) => s.setUpstream503)
  const [secondsLeft, setSecondsLeft] = useState(COUNTDOWN_SECONDS)

  const readiness = useReadiness()

  // Auto-dismiss once the backend recovers.
  useEffect(() => {
    if (upstream503 && readiness.isSuccess && readiness.data?.ready === true) {
      setUpstream503(false)
    }
  }, [readiness.data, readiness.isSuccess, upstream503, setUpstream503])

  useEffect(() => {
    if (!upstream503) return
    setSecondsLeft(COUNTDOWN_SECONDS)
    const timer = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(timer)
          return 0
        }
        return s - 1
      })
    }, 1000)
    const retryTimer = setTimeout(() => {
      readiness.refetch()
      setSecondsLeft(COUNTDOWN_SECONDS)
    }, COUNTDOWN_SECONDS * 1000)
    return () => {
      clearInterval(timer)
      clearTimeout(retryTimer)
    }
  }, [upstream503])

  return (
    <AnimatePresence>
      {upstream503 && (
        <motion.div
          initial={{ y: -70 }}
          animate={{ y: 0 }}
          exit={{ y: -70 }}
          transition={{ type: 'spring', damping: 22, stiffness: 260 }}
          className="absolute left-1/2 top-[70px] z-40 flex -translate-x-1/2 items-center gap-3 rounded-xl border px-4 py-2.5"
          style={{
            background: 'rgba(66, 50, 4, 0.85)',
            borderColor: 'rgba(255,230,109,0.45)',
            backdropFilter: 'blur(20px)',
            boxShadow: '0 6px 30px rgba(0,0,0,0.5)',
          }}
        >
          <AlertTriangle className="h-4 w-4 shrink-0" style={{ color: '#ffe66d' }} />
          <p className="text-xs text-text-primary">
            Data source temporarily unavailable
            {message ? ` — ${message}` : ''}
            {secondsLeft > 0 ? (
              <span className="ml-2 font-mono text-current opacity-80">
                retrying in {secondsLeft}s
              </span>
            ) : null}
          </p>
          <button
            onClick={() => readiness.refetch()}
            className="flex items-center gap-1 rounded-md border border-current/40 px-2 py-1 text-[11px] font-semibold transition-colors hover:bg-white/10"
            style={{ color: '#ffe66d' }}
          >
            <RefreshCw className="h-3 w-3" /> Retry now
          </button>
          <button
            onClick={() => setUpstream503(false)}
            className="rounded p-1 text-text-muted transition-colors hover:text-text-primary"
            title="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
