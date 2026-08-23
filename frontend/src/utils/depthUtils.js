export const MAX_DEPTH_METERS = 2000

export const SCENE_WIDTH = 120
export const SCENE_DEPTH = 80
export const SCENE_HALF_W = 62
export const SCENE_HALF_D = 42

export function depthToY(depthMeters, verticalExaggeration = 50) {
  return -(Math.max(0, depthMeters) / MAX_DEPTH_METERS) * verticalExaggeration
}

export function makeDomainMapping(bounds) {
  const west = bounds?.west ?? 30.5
  const east = bounds?.east ?? 119.5
  const south = bounds?.south ?? -29.5
  const north = bounds?.north ?? 29.5
  return {
    lonToX: (lon) => ((lon - west) / (east - west) - 0.5) * SCENE_WIDTH,
    latToZ: (lat) => -((lat - south) / (north - south) - 0.5) * SCENE_DEPTH,
    xToLon: (x) => west + (x / SCENE_WIDTH + 0.5) * (east - west),
    zToLat: (z) => south + (-z / SCENE_DEPTH + 0.5) * (north - south),
    center: [(west + east) / 2, (south + north) / 2],
  }
}
