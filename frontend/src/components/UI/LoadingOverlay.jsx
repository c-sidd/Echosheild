import { motion } from 'framer-motion'
import { Waves } from 'lucide-react'

export default function LoadingOverlay({ loading }) {
  return (
    <motion.div
      initial={{ opacity: 1 }}
      animate={{ opacity: loading ? 1 : 0 }}
      transition={{ duration: 0.6 }}
      className="pointer-events-none absolute inset-0 z-50 flex flex-col items-center justify-center bg-abyss"
      style={{ visibility: loading ? 'visible' : 'hidden' }}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.8, ease: 'easeOut' }}
        className="flex items-center gap-3"
      >
        <Waves className="h-8 w-8 dot-pulse" style={{ color: 'var(--color-glow)' }} />
        <p className="text-3xl font-extrabold tracking-tight text-text-primary text-glow">
          Echo<span style={{ color: 'var(--color-glow)' }}>Shield</span>
        </p>
      </motion.div>

      <div className="mt-5 h-[3px] w-52 overflow-hidden rounded-full bg-surface">
        <motion.div
          animate={{ x: ['-100%', '100%'] }}
          transition={{ repeat: Infinity, duration: 1.4, ease: 'easeInOut' }}
          className="h-full w-1/2 rounded-full"
          style={{
            background:
              'linear-gradient(to right, transparent, var(--color-glow), transparent)',
          }}
        />
      </div>

      <p className="mt-4 font-mono text-xs uppercase tracking-widest text-text-muted">
        Connecting to INCOIS data services…
      </p>
    </motion.div>
  )
}
