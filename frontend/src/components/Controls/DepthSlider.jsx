import { motion } from 'framer-motion'
import { useOceanStore } from '@/store/oceanStore'
import { formatDepth } from '@/utils/formatters'

const LABEL_EVERY = new Set([0, 4, 6, 9, 13, 16, 20, 23])

export default function DepthSlider() {
  const depths = useOceanStore((s) => s.depths)
  const activeDepth = useOceanStore((s) => s.activeDepth)
  const setActiveDepth = useOceanStore((s) => s.setActiveDepth)

  if (!depths.length) return null

  // Render shallowest at top, deepest at bottom (list is already ascending).
  const levels = [...depths].reverse()

  return (
    <motion.aside
      initial={{ x: -60, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ delay: 0.3, duration: 0.5, ease: 'easeOut' }}
      className="glass-panel pointer-events-auto absolute left-4 top-[50%] z-20 -translate-y-1/2 px-3 py-4"
      style={{
        background:
          'linear-gradient(180deg, rgba(6,38,64,0.85), rgba(2,11,24,0.92))',
        boxShadow: '0 8px 40px rgba(0,0,0,0.5)',
      }}
    >
      <p className="mb-3 text-center text-[10px] font-semibold uppercase tracking-widest text-text-muted">
        Depth
      </p>
      <div className="flex flex-col items-center gap-[3px]">
        {levels.map((depth, i) => {
          const isActive = Math.abs(depth - activeDepth) < 1e-6
          return (
            <button
              key={depth}
              onClick={() => setActiveDepth(depth)}
              className={`group flex items-center gap-1.5 transition-all ${
                isActive ? 'scale-110' : 'hover:scale-105'
              }`}
              title={`${formatDepth(depth)} — click to select`}
            >
              <span
                className={`text-right font-mono text-[10px] leading-none ${
                  LABEL_EVERY.has(depths.length - 1 - i) || isActive
                    ? isActive
                      ? 'text-glow'
                      : 'text-text-secondary'
                    : 'text-text-muted opacity-70'
                }`}
              >
                {isActive ? formatDepth(depth) : LABEL_EVERY.has(depths.length - 1 - i) ? formatDepth(depth) : '·'}
              </span>
              <span
                className="block rounded-full transition-all"
                style={{
                  width: isActive ? 14 : 8,
                  height: isActive ? 14 : 8,
                  background: isActive
                    ? 'var(--color-glow)'
                    : `rgba(0, 212, 255, ${0.15 + 0.55 * (i / levels.length)})`,
                  boxShadow: isActive
                    ? '0 0 12px rgba(0,212,255,0.9)'
                    : 'none',
                }}
              />
            </button>
          )
        })}
      </div>
      <p className="mt-3 text-center font-mono text-xs text-glow">
        {formatDepth(activeDepth)}
      </p>
    </motion.aside>
  )
}
