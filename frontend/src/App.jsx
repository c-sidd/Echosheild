import { useOceanStore } from '@/store/oceanStore'

const STACK_ITEMS = [
  ['Three.js / R3F', '3D volume + slice rendering'],
  ['Deck.gl', 'Argo floats · currents · heatmaps'],
  ['Zustand', 'Scene-wide selection state'],
  ['TanStack Query', 'Cached slice fetching'],
  ['Tailwind v4', 'Dark HUD styling'],
]

function StackBadge({ name, role }) {
  return (
    <div className="rounded-lg border border-abyss-600 bg-abyss-800/60 px-4 py-3">
      <p className="text-sm font-semibold text-ocean-300">{name}</p>
      <p className="mt-0.5 text-xs text-foam-100/60">{role}</p>
    </div>
  )
}

export default function App() {
  const variable = useOceanStore((s) => s.variable)

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-abyss-700 bg-abyss-900 px-6 py-3">
        <h1 className="text-lg font-bold tracking-tight">
          Echo<span className="text-ocean-400">Shield</span>
        </h1>
        <span className="text-xs text-foam-100/50">
          INCOIS Argo · SIH PS 26067
        </span>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-8 p-8">
        <div className="text-center">
          <p className="text-sm uppercase tracking-widest text-ocean-400">
            Scaffold ready
          </p>
          <h2 className="mt-2 text-3xl font-bold text-foam-100">
            Ocean visualization shell online
          </h2>
          <p className="mt-2 max-w-md text-sm text-foam-100/60">
            Vite + React 19 dev environment is live with the API proxy pointed
            at <code className="text-ocean-300">localhost:8000</code>. Store
            variable: <code className="text-ocean-300">{String(variable)}</code>
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {STACK_ITEMS.map(([name, role]) => (
            <StackBadge key={name} name={name} role={role} />
          ))}
        </div>
      </main>
    </div>
  )
}
