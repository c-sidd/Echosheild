self.onmessage = (event) => {
  const { id, values, lut, min, max, width, height, opacity } = event.data
  const pixels = new Uint8Array(width * height * 4)
  const lo = Number.isFinite(min) ? min : 0
  const hi = Number.isFinite(max) && max > lo ? max : lo + 1
  const range = hi - lo

  for (let row = 0; row < height; row += 1) {
    const sourceRow = values[row]
    for (let col = 0; col < width; col += 1) {
      const value = sourceRow ? sourceRow[col] : null
      const offset = (row * width + col) * 4
      if (value == null || !Number.isFinite(value)) {
        pixels[offset + 3] = 0
        continue
      }
      let index = Math.round(Math.max(0, Math.min(1, (value - lo) / range)) * 255)
      index = Math.max(0, Math.min(255, index))
      pixels[offset] = lut[index * 4]
      pixels[offset + 1] = lut[index * 4 + 1]
      pixels[offset + 2] = lut[index * 4 + 2]
      pixels[offset + 3] = opacity
    }
  }

  self.postMessage({ id, pixels }, [pixels.buffer])
}
