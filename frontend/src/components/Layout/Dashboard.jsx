import { useEffect } from 'react'
import Header from '@/components/Layout/Header'
import Sidebar from '@/components/Layout/Sidebar'
import OceanViewer from '@/components/Viewer3D/OceanViewer'
import OceanMap from '@/components/Map2D/OceanMap'
import DepthSlider from '@/components/Controls/DepthSlider'
import TimeControls from '@/components/Controls/TimeControls'
import ProfileChart from '@/components/ProfileChart/ProfileChart'
import HoverInspector from '@/components/UI/HoverInspector'
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

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-abyss">
      {viewMode === '3D' ? <OceanViewer /> : <OceanMap />}

      <Header />
      <Sidebar />
      <DepthSlider />
      <TimeControls />
      <ProfileChart />
      <GliderPlaceholder />
      <HoverInspector />
      <UpstreamBanner />
      <LoadingOverlay loading={datasetsQuery.isLoading || datasetsQuery.isError} />
    </div>
  )
}
