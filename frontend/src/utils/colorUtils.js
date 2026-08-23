const CLAMP01 = (t) => (t < 0 ? 0 : t > 1 ? 1 : t)

export const COLORMAPS = {
  viridis: [
    [68, 1, 84],
    [72, 40, 120],
    [62, 74, 137],
    [49, 104, 142],
    [38, 130, 142],
    [31, 158, 137],
    [53, 183, 121],
    [109, 205, 89],
    [180, 222, 44],
    [253, 231, 37],
  ],
  plasma: [
    [13, 8, 135],
    [69, 3, 158],
    [114, 1, 168],
    [156, 23, 158],
    [189, 55, 134],
    [216, 87, 107],
    [237, 121, 83],
    [251, 159, 58],
    [253, 202, 38],
    [240, 249, 33],
  ],
  coolwarm: [
    [59, 76, 192],
    [83, 110, 227],
    [123, 153, 245],
    [170, 190, 250],
    [207, 218, 252],
    [242, 242, 242],
    [250, 220, 210],
    [245, 185, 165],
    [235, 135, 105],
    [215, 85, 65],
    [180, 4, 38],
  ],
  inferno: [
    [0, 0, 4],
    [31, 12, 72],
    [85, 15, 109],
    [136, 34, 106],
    [186, 54, 85],
    [227, 89, 51],
    [249, 140, 10],
    [249, 201, 50],
    [252, 255, 164],
  ],
  magma: [
    [0, 0, 4],
    [28, 16, 68],
    [79, 18, 123],
    [129, 37, 129],
    [181, 54, 122],
    [229, 80, 100],
    [251, 135, 97],
    [254, 194, 135],
    [252, 253, 191],
  ],
}

function sampleStops(stops, t) {
  const clamped = CLAMP01(t)
  const scaled = clamped * (stops.length - 1)
  const i = Math.min(Math.floor(scaled), stops.length - 2)
  const f = scaled - i
  const a = stops[i]
  const b = stops[i + 1]
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ]
}

export function colormapRGB(colormap) {
  return COLORMAPS[colormap] ?? COLORMAPS.viridis
}

export function colormapCSS(colormap, steps = 32) {
  const stops = colormapRGB(colormap)
  const parts = []
  for (let i = 0; i < steps; i++) {
    const [r, g, b] = sampleStops(stops, i / (steps - 1))
    parts.push(`rgb(${r},${g},${b}) ${((i / (steps - 1)) * 100).toFixed(1)}%`)
  }
  return `linear-gradient(to right, ${parts.join(',')})`
}

export function colormapHexStops(colormap, count = 10) {
  const stops = colormapRGB(colormap)
  const out = []
  for (let i = 0; i < count; i++) {
    const [r, g, b] = sampleStops(stops, count === 1 ? 0 : i / (count - 1))
    out.push([r, g, b, 255])
  }
  return out
}

export function buildLUT(colormap, min, max, logScale = false) {
  const lut = new Uint8Array(256 * 4)
  const stops = colormapRGB(colormap)
  const lo = Number.isFinite(min) ? min : 0
  const hi = Number.isFinite(max) && max > min ? max : min + 1
  const useLog = logScale && lo > 0
  const logLo = Math.log(lo)
  const logHi = Math.log(hi)
  for (let i = 0; i < 256; i++) {
    let t = i / 255
    if (useLog) {
      const v = lo + t * (hi - lo)
      t = (Math.log(Math.max(v, lo)) - logLo) / (logHi - logLo || 1)
    }
    const [r, g, b] = sampleStops(stops, t)
    lut[i * 4] = r
    lut[i * 4 + 1] = g
    lut[i * 4 + 2] = b
    lut[i * 4 + 3] = 255
  }
  return lut
}

export function valuesToTexture(values, lut, min, max, width, height, opacity = 255) {
  const pixels = new Uint8Array(width * height * 4)
  const lo = Number.isFinite(min) ? min : 0
  const hi = Number.isFinite(max) && max > lo ? max : lo + 1
  const range = hi - lo
  for (let row = 0; row < height; row++) {
    const srcRow = values[row]
    for (let col = 0; col < width; col++) {
      const v = srcRow ? srcRow[col] : null
      const o = (row * width + col) * 4
      if (v == null || !Number.isFinite(v)) {
        pixels[o + 3] = 0
        continue
      }
      let t = (v - lo) / range
      t = CLAMP01(t)
      let idx = Math.round(t * 255)
      if (idx < 0) idx = 0
      if (idx > 255) idx = 255
      pixels[o] = lut[idx * 4]
      pixels[o + 1] = lut[idx * 4 + 1]
      pixels[o + 2] = lut[idx * 4 + 2]
      pixels[o + 3] = opacity
    }
  }
  return pixels
}

export function dataRange(values) {
  let min = Infinity
  let max = -Infinity
  for (const row of values ?? []) {
    for (const v of row ?? []) {
      if (v == null || !Number.isFinite(v)) continue
      if (v < min) min = v
      if (v > max) max = v
    }
  }
  if (!Number.isFinite(min)) return null
  return { min, max }
}
