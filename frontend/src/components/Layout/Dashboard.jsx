import { useEffect } from 'react'
import Header from '@/components/Layout/Header'
import Sidebar from '@/components/Layout/Sidebar'
import OceanViewer from '@/components/Viewer3D/OceanViewer'
import SceneErrorBoundary from '@/components/Viewer3D/SceneErrorBoundary'
import OceanMap from '@/components/Map2D/OceanMap'
import DepthSlider from '@/components/Controls/DepthSlider'
import TimeControls from '@/components/Controls/TimeControls'
import ProfileChart from '@/components/ProfileChart/ProfileChart'
import HoverInspector from '@/components/UI/HoverInspector'
import MetadataPanel from '@/components/UI/MetadataPanel'
import ColorbandLegend from '@/components/UI/ColorbandLegend'
import UpstreamBanner from '@/components/UI/UpstreamBanner'
import LoadingOverlay from '@/components/UI/LoadingOverlay'
import GliderPlaceholder from '@/components/UI/GliderPlaceholder'
import { useDatasetSync, useDatasets } from '@/hooks/useOceanData'
import { useTimeAnimation } from '@/hooks/useTimeAnimation'
import { useOceanStore } from '@/store/oceanStore'

export default function Dashboard() {
  const viewMode = useOceanStore((s) => s.viewMode)
  const setDatasets = useOceanStore((s) => s.setDatasets)
  const datasetsQuery = useDatasets()

  useDatasetSync()
  useTimeAnimation()

  useEffect(() => {
    if (Array.isArray(datasetsQuery.data)) {
      setDatasets(datasetsQuery.data)
    }
  }, [datasetsQuery.data, setDatasets])

  // Keep the splash up until real renderable data (depth levels) arrives,
  // so the user never sees a black canvas gap after datasets resolve.
  const sliceReady = useOceanStore(
    (s) => s.dataLoadedAt != null || s.depths.length > 0,
  )

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-abyss">
      <SceneErrorBoundary>
        {viewMode === '3D' ? <OceanViewer /> : <OceanMap />}
      </SceneErrorBoundary>

      <Header />
      <Sidebar />
      <DepthSlider />
      <TimeControls />
      <ProfileChart />
      <MetadataPanel />
      <ColorbandLegend />
      <GliderPlaceholder />
      <HoverInspector />
      <UpstreamBanner />
      <LoadingOverlay
        loading={datasetsQuery.isLoading || (!sliceReady && !datasetsQuery.isError)}
      />
    </div>
  )
}
