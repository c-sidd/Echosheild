import { useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { X, Thermometer, Droplets, Satellite } from 'lucide-react'
import { useOceanStore } from '@/store/oceanStore'
import { useArgoDetail, useArgoProfile } from '@/hooks/useOceanData'
import { formatDate, formatValue } from '@/utils/formatters'

export default function ProfileChart() {
  const selectedFloat = useOceanStore((s) => s.selectedFloat)
  const closeFloatPanel = useOceanStore((s) => s.closeFloatPanel)
  const detailQuery = useArgoDetail(selectedFloat?.platform_wmo ?? null)

  return (
    <AnimatePresence>
      {selectedFloat && (
        <motion.aside
          key={selectedFloat.platform_wmo}
          initial={{ x: 340, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 340, opacity: 0 }}
          transition={{ type: 'spring', damping: 26, stiffness: 220 }}
          className="glass-panel pointer-events-auto absolute bottom-[110px] left-4 z-30 flex max-h-[62vh] w-[330px] flex-col"
          style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.6)' }}
        >
          <HeaderRow
            wmo={selectedFloat.platform_wmo}
            detail={detailQuery.data}
            onClose={closeFloatPanel}
          />
          <Body wmo={selectedFloat.platform_wmo} />
        </motion.aside>
      )}
    </AnimatePresence>
  )
}

function HeaderRow({ wmo, detail, onClose }) {
  const lastCycle = detail?.recent_profiles?.[0]?.cycle_number
  const lastTime = detail?.time_range?.end ?? detail?.recent_profiles?.[0]?.time
  return (
    <div className="flex items-start justify-between border-b border-[rgba(0,212,255,0.15)] px-4 py-3">
      <div>
        <p className="font-mono text-sm font-bold text-glow">
          WMO {wmo}
        </p>
        <p className="mt-0.5 flex items-center gap-1 text-[10px] text-text-secondary">
          <Satellite className="h-3 w-3" />
          {lastCycle != null ? `Cycle ${lastCycle}` : ''}
          {lastTime ? ` · ${formatDate(lastTime)}` : ''}
        </p>
      </div>
      <button
        onClick={onClose}
        className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-glow"
        title="Close"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

function Body({ wmo }) {
  const profileQuery = useArgoProfile(wmo)
  const profileVariable = useOceanStore((s) => s.profileVariable)
  const setProfileVariable = useOceanStore((s) => s.setProfileVariable)

  const data = useMemo(() => {
    const pts = profileQuery.data?.points
    if (!Array.isArray(pts)) return []
    return pts
      .filter((p) => Number.isFinite(p.depth_meters))
      .map((p) => ({
        depth: Math.round(p.depth_meters),
        temperature: p.temperature_c,
        salinity: p.salinity_psu,
      }))
      .sort((a, b) => a.depth - b.depth)
  }, [profileQuery.data])

  if (profileQuery.isPending) {
    return <PanelMessage>Loading profile…</PanelMessage>
  }

  if (profileQuery.isError) {
    const status = profileQuery.error?.status
    return (
      <PanelMessage>
        {status === 503 || status === 0
          ? 'Float data requires an internet connection to the Argo GDAC.'
          : `No profile available for float ${wmo}.`}
      </PanelMessage>
    )
  }

  if (!data.length) {
    return <PanelMessage>No profile points in this cycle.</PanelMessage>
  }

  const isTemp = profileVariable === 'temperature'
  const unit = isTemp ? '°C' : 'PSU'
  const color = isTemp ? 'var(--color-warm)' : 'var(--color-salt)'
  const values = data.map((d) => d[profileVariable]).filter(Number.isFinite)
  const vMin = values.length ? Math.min(...values) : 0
  const vMax = values.length ? Math.max(...values) : 1

  return (
    <div className="flex flex-col overflow-hidden px-3 pb-3">
      <div className="mb-2 mt-2 flex gap-1.5">
        <TabBtn active={isTemp} onClick={() => setProfileVariable('temperature')} icon={Thermometer}>
          Temperature
        </TabBtn>
        <TabBtn active={!isTemp} onClick={() => setProfileVariable('salinity')} icon={Droplets}>
          Salinity
        </TabBtn>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 6, right: 12, bottom: 4, left: -14 }}>
          <CartesianGrid stroke="rgba(0,212,255,0.08)" />
          <XAxis
            type="number"
            dataKey={profileVariable}
            domain={[vMin, vMax]}
            tick={{ fill: '#7fb3c8', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            tickFormatter={(v) => formatValue(v, 1)}
            stroke="rgba(0,212,255,0.25)"
            label={{
              value: unit,
              position: 'insideBottomRight',
              offset: -2,
              fill: '#3a6a85',
              fontSize: 10,
            }}
          />
          <YAxis
            type="category"
            dataKey="depth"
            reversed
            width={46}
            tick={{ fill: '#7fb3c8', fontSize: 9, fontFamily: 'JetBrains Mono' }}
            tickFormatter={(d) => `${d}m`}
            stroke="rgba(0,212,255,0.25)"
          />
          <Tooltip
            contentStyle={tooltipStyle()}
            labelFormatter={(depth) => `${depth} m depth`}
            formatter={(value) => [`${formatValue(value)} ${unit}`, null]}
          />
          <Line
            type="monotone"
            dataKey={profileVariable}
            stroke={color}
            strokeWidth={2}
            dot={(props) =>
              props.index % Math.ceil(data.length / 24 || 1) === 0
                ? { ...props.circleProps, r: 2.5, fill: color }
                : { r: 0 }
            }
            activeDot={{ r: 4 }}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>

      <p className="mt-1 text-center text-[9px] uppercase tracking-widest text-text-muted">
        Depth (m) · {data.length} levels · Cycle{' '}
        {profileQuery.data?.cycle_number ?? '—'}
      </p>
    </div>
  )
}

function TabBtn({ active, onClick, icon: Icon, children }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-[11px] font-semibold transition-colors ${
        active
          ? 'border-glow/60 bg-surface text-text-primary'
          : 'border-transparent bg-deep/60 text-text-muted hover:text-text-secondary'
      }`}
    >
      <Icon
        className="h-3.5 w-3.5"
        style={{ color: active ? (children === 'Temperature' ? 'var(--color-warm)' : 'var(--color-salt)') : undefined }}
      />
      {children}
    </button>
  )
}

function PanelMessage({ children }) {
  return (
    <p className="px-4 py-8 text-center text-xs leading-relaxed text-text-secondary">
      {children}
    </p>
  )
}

export function tooltipStyle() {
  return {
    backgroundColor: 'rgba(4,23,40,0.95)',
    border: '1px solid rgba(0,212,255,0.35)',
    borderRadius: '8px',
    fontFamily: 'JetBrains Mono, monospace',
    fontSize: 11,
  }
}
