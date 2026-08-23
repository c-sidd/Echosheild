import { motion } from 'framer-motion'
import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import VariableSelector from '@/components/Controls/VariableSelector'
import ColorbarEditor from '@/components/Controls/ColorbarEditor'
import LayerControls from '@/components/Controls/LayerControls'
import { useOceanStore } from '@/store/oceanStore'

function Section({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-[rgba(0,212,255,0.1)] px-4 py-3 last:border-b-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-[11px] font-semibold uppercase tracking-widest text-text-secondary hover:text-glow"
      >
        {title}
        <motion.span animate={{ rotate: open ? 0 : -90 }} className="inline-flex">
          <ChevronDown className="h-3.5 w-3.5" />
        </motion.span>
      </button>
      <motion.div
        initial={false}
        animate={{ height: open ? 'auto' : 0, opacity: open ? 1 : 0 }}
        transition={{ duration: 0.25, ease: 'easeInOut' }}
        className="overflow-hidden"
      >
        <div className="pt-3">{children}</div>
      </motion.div>
    </div>
  )
}

export default function Sidebar() {
  const opacity = useOceanStore((s) => s.opacity)
  const setOpacity = useOceanStore((s) => s.setOpacity)
  const verticalExaggeration = useOceanStore((s) => s.verticalExaggeration)
  const setVerticalExaggeration = useOceanStore((s) => s.setVerticalExaggeration)

  return (
    <aside
      className="glass-panel pointer-events-auto absolute right-4 top-[76px] z-20 flex max-h-[calc(100vh-170px)] w-[280px] flex-col overflow-y-auto"
      style={{ boxShadow: '0 8px 40px rgba(0,0,0,0.5)' }}
    >
      <div className="flex items-center gap-2 border-b border-[rgba(0,212,255,0.15)] px-4 py-3">
        <SlidersHorizontal className="h-4 w-4" style={{ color: 'var(--color-glow)' }} />
        <p className="text-xs font-bold uppercase tracking-widest">Controls</p>
      </div>

      <Section title="Variable">
        <VariableSelector />
      </Section>

      <Section title="Colorbar">
        <ColorbarEditor />
      </Section>

      <Section title="Render">
        <div className="space-y-4">
          <SliderRow
            label="Opacity"
            value={opacity}
            min={0.1}
            max={1}
            step={0.05}
            display={`${Math.round(opacity * 100)}%`}
            onChange={setOpacity}
          />
          <SliderRow
            label="V. Exag."
            value={verticalExaggeration}
            min={5}
            max={120}
            step={5}
            display={`${verticalExaggeration}×`}
            onChange={setVerticalExaggeration}
          />
        </div>
      </Section>

      <Section title="Layers">
        <LayerControls />
      </Section>
    </aside>
  )
}

export function SliderRow({ label, value, min, max, step, display, onChange }) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="text-text-secondary">{label}</span>
        <span className="font-mono text-glow">{display}</span>
      </div>
      <input
        type="range"
        className="w-full"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

export { Section as SidebarSection }
