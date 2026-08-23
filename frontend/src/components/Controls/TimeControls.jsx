import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  ChevronFirst,
  ChevronLast,
} from 'lucide-react'
import gsap from 'gsap'
import { useOceanStore } from '@/store/oceanStore'
import { fetchSliceBatch } from '@/services/modelService'
import { formatMonthYear } from '@/utils/formatters'

const SPEEDS = [0.5, 1, 2, 5]
const SPARK_POINTS = 24

export default function TimeControls() {
  const queryClient = useQueryClient()
  const timeRange = useOceanStore((s) => s.timeRange)
  const timeIndex = useOceanStore((s) => s.timeIndex)
  const setTimeIndex = useOceanStore((s) => s.setTimeIndex)
  const stepTime = useOceanStore((s) => s.stepTime)
  const isPlaying = useOceanStore((s) => s.isPlaying)
  const togglePlay = useOceanStore((s) => s.togglePlay)
  const playSpeed = useOceanStore((s) => s.playSpeed)
  const setPlaySpeed = useOceanStore((s) => s.setPlaySpeed)

  const dateRef = useRef(null)
  const count = timeRange?.count ?? 0
  const startISO = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.time_range?.start,
  )
  const endISO = useOceanStore(
    (s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.time_range?.end,
  )
  const datasetId = useOceanStore((s) => s.activeDatasetId)
  const activeVariable = useOceanStore((s) => s.activeVariable)
  const depths = useOceanStore((s) => s.depths)
  const timestampsList = useOceanStore((s) => s.timestampsList)

  // Real timestamp at this index; linear interpolation only as a fallback
  // while the full time axis is still downloading.
  const currentTimeISO =
    timestampsList[timeIndex] ??
    interpolateISO(startISO, endISO, timeIndex, count)

  // Sparkline of surface means sampled across the whole time axis — a few
  // batch requests (server caps batches at 10), then cached forever.
  const [sparkData, setSparkData] = useState([])
  useEffect(() => {
    if (!datasetId || !activeVariable || count < SPARK_POINTS) return
    const depth = depths[0]
    if (!Number.isFinite(depth)) return
    const step = Math.floor(count / SPARK_POINTS)
    const indexes = Array.from({ length: SPARK_POINTS }, (_, i) => i * step)
    const controller = new AbortController()
    let cancelled = false
    queryClient
      .fetchQuery({
        queryKey: ['sparkline', datasetId, activeVariable],
        queryFn: async ({ signal }) => {
          const batches = []
          for (let i = 0; i < indexes.length; i += 10) {
            batches.push(
              fetchSliceBatch(
                datasetId,
                indexes.slice(i, i + 10).map((t) => ({
                  variable: activeVariable,
                  time_index: t,
                  depth_meters: depth,
                })),
                signal ?? controller.signal,
              ),
            )
          }
          return (await Promise.all(batches)).flat()
        },
        staleTime: Infinity,
      })
      .then((slices) => {
        if (!cancelled && Array.isArray(slices)) {
          setSparkData(slices.map(meanOf))
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [queryClient, datasetId, activeVariable, count, depths])

  const sparkStats = useMemo(() => normalizeSpark(sparkData), [sparkData])
  const activeSparkIndex =
    sparkData.length > 1
      ? Math.min(
          Math.floor((timeIndex / count) * sparkData.length),
          sparkData.length - 1,
        )
      : -1

  // Number-roll animation on the date readout.
  useEffect(() => {
    if (!dateRef.current) return
    gsap.fromTo(
      dateRef.current,
      { y: 8, opacity: 0.4 },
      { y: 0, opacity: 1, duration: 0.22, ease: 'power2.out', overwrite: true },
    )
  }, [currentTimeISO])

  // Keyboard shortcuts: Space play/pause, arrows step.
  useEffect(() => {
    const onKey = (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
      if (e.code === 'Space') {
        e.preventDefault()
        togglePlay()
      } else if (e.code === 'ArrowRight') {
        e.preventDefault()
        useOceanStore.getState().setPlaying(false)
        stepTime(1)
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault()
        useOceanStore.getState().setPlaying(false)
        stepTime(-1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [togglePlay, stepTime])

  const scrubTo = useCallback(
    (clientX, element) => {
      const rect = element.getBoundingClientRect()
      const frac = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1)
      setTimeIndex(Math.round(frac * Math.max(count - 1, 0)))
    },
    [count, setTimeIndex],
  )

  const handleDrag = useCallback(
    (e) => {
      if (e.buttons !== 1) return
      scrubTo(e.clientX, e.currentTarget)
    },
    [scrubTo],
  )

  if (!count) return null

  return (
    <motion.div
      initial={{ y: 60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ delay: 0.45, duration: 0.5, ease: 'easeOut' }}
      className="glass-panel pointer-events-auto absolute bottom-4 left-1/2 z-20 w-[min(680px,calc(100vw-200px))] -translate-x-1/2 px-5 py-3"
      style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.55)' }}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-1">
          <IconBtn onClick={() => setTimeIndex(0)} title="First">
            <ChevronFirst className="h-4 w-4" />
          </IconBtn>
          <IconBtn
            onClick={() => {
              useOceanStore.getState().setPlaying(false)
              stepTime(-1)
            }}
            title="Previous"
          >
            <SkipBack className="h-4 w-4" />
          </IconBtn>
          <button
            onClick={togglePlay}
            title={isPlaying ? 'Pause' : 'Play'}
            className="mx-1 flex h-10 w-10 items-center justify-center rounded-full transition-transform hover:scale-105"
            style={{
              background: 'rgba(0,212,255,0.15)',
              border: '1px solid rgba(0,212,255,0.5)',
              boxShadow: '0 0 18px rgba(0,212,255,0.25)',
            }}
          >
            {isPlaying ? (
              <Pause className="h-4.5 w-4.5 text-glow" />
            ) : (
              <Play className="ml-0.5 h-4.5 w-4.5 text-glow" />
            )}
          </button>
          <IconBtn
            onClick={() => {
              useOceanStore.getState().setPlaying(false)
              stepTime(1)
            }}
            title="Next"
          >
            <SkipForward className="h-4 w-4" />
          </IconBtn>
          <IconBtn onClick={() => setTimeIndex(count - 1)} title="Last">
            <ChevronLast className="h-4 w-4" />
          </IconBtn>
        </div>

        <div ref={dateRef} className="text-center">
          <p className="text-lg font-bold leading-tight text-glow text-glow font-mono">
            {formatMonthYear(currentTimeISO)}
          </p>
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-muted">
            Step {timeIndex + 1} / {count}
          </p>
        </div>

        <div className="flex items-center gap-1">
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => setPlaySpeed(s)}
              className={`rounded px-1.5 py-1 font-mono text-[10px] transition-colors ${
                playSpeed === s
                  ? 'bg-glow/20 text-glow ring-1 ring-glow/50'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>

      {sparkData.length > 1 && (
        <div className="mb-1 flex h-6 items-end gap-[1px]">
          {sparkStats.bars.map((v, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm opacity-60 transition-all"
              style={{
                height: `${Math.max(4, v * 24)}px`,
                background:
                  i === activeSparkIndex
                    ? 'var(--color-glow)'
                    : 'rgba(0,212,255,0.35)',
              }}
            />
          ))}
        </div>
      )}

      <div
        className="relative mt-3 h-2 cursor-pointer select-none rounded-full bg-surface"
        onMouseDown={(e) => {
          useOceanStore.getState().setPlaying(false)
          scrubTo(e.clientX, e.currentTarget)
        }}
        onMouseMove={handleDrag}
        role="slider"
        aria-label="Time scrubber"
        aria-valuemin={1}
        aria-valuemax={count}
        aria-valuenow={timeIndex + 1}
        tabIndex={0}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${count > 1 ? (timeIndex / (count - 1)) * 100 : 0}%`,
            background:
              'linear-gradient(to right, rgba(0,102,255,0.5), rgba(0,212,255,0.8))',
          }}
        />
        <div
          className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-glow bg-deep transition-shadow"
          style={{
            left: `${count > 1 ? (timeIndex / (count - 1)) * 100 : 0}%`,
            boxShadow: isPlaying ? '0 0 14px rgba(0,212,255,0.9)' : 'none',
          }}
        />
      </div>

      <div className="mt-1 flex justify-between font-mono text-[9px] text-text-muted">
        <span>{formatMonthYear(startISO)}</span>
        <span>{formatMonthYear(endISO)}</span>
      </div>
    </motion.div>
  )
}

function IconBtn({ children, onClick, title }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="flex h-7 w-7 items-center justify-center rounded-md text-text-secondary transition-colors hover:bg-surface hover:text-glow"
    >
      {children}
    </button>
  )
}

function interpolateISO(startISO, endISO, timeIndex, count) {
  if (!count || !startISO || endISO == null) return null
  const start = new Date(startISO)
  const end = new Date(endISO)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null
  const span = end.getTime() - start.getTime()
  const t = count > 1 ? timeIndex / (count - 1) : 0
  return new Date(start.getTime() + t * span).toISOString()
}

function meanOf(slice) {
  if (!Array.isArray(slice?.values)) return null
  let sum = 0
  let n = 0
  for (const row of slice.values) {
    for (const v of row) {
      if (v != null && Number.isFinite(v)) {
        sum += v
        n += 1
      }
    }
  }
  return n > 0 ? sum / n : null
}

function normalizeSpark(data) {
  const finite = data.filter((v) => Number.isFinite(v))
  if (!finite.length) return { bars: [] }
  let min = Infinity
  let max = -Infinity
  for (const v of finite) {
    if (v < min) min = v
    if (v > max) max = v
  }
  const span = max - min || 1
  return {
    bars: data.map((v) =>
      Number.isFinite(v) ? Math.min(Math.max((v - min) / span, 0.08), 1) : 0,
    ),
  }
}
