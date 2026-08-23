import { motion } from 'framer-motion'
import { Navigation } from 'lucide-react'
import { useGliderStatus } from '@/hooks/useOceanData'
import { useOceanStore } from '@/store/oceanStore'

export default function GliderPlaceholder() {
  const gliderQuery = useGliderStatus()
  const showGlider = useOceanStore((s) => s.showGlider)

  if (gliderQuery.data?.configured !== false || !showGlider) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 16 }}
      className="glass-panel pointer-events-auto absolute bottom-[130px] left-4 z-20 flex w-[260px] items-start gap-3 px-4 py-3"
    >
      <Navigation className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
      <div>
        <p className="text-xs font-semibold text-text-secondary">Underwater Gliders</p>
        <p className="mt-1 text-[10px] leading-relaxed text-text-muted">
          Glider ingestion is pluggable and awaiting a live data source — the
          client seam is ready on the backend. Coming soon.
        </p>
      </div>
    </motion.div>
  )
}
