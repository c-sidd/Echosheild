let worker = null
let nextId = 1
const pending = new Map()

function getWorker() {
  if (worker) return worker
  worker = new Worker(new URL('./textureWorker.js', import.meta.url), { type: 'module' })
  worker.onmessage = (event) => {
    const { id, pixels } = event.data
    const resolve = pending.get(id)
    if (!resolve) return
    pending.delete(id)
    resolve(new Uint8Array(pixels))
  }
  worker.onerror = (error) => {
    for (const [, handlers] of pending) handlers.reject(error)
    pending.clear()
    worker?.terminate()
    worker = null
  }
  return worker
}

export function valuesToTextureAsync(values, lut, min, max, width, height, opacity = 255) {
  return new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject })
    getWorker().postMessage({
      id,
      values,
      lut: Array.from(lut),
      min,
      max,
      width,
      height,
      opacity,
    })
  })
}

export function disposeTextureWorker() {
  worker?.terminate()
  worker = null
  for (const [, handlers] of pending) handlers.reject(new Error('texture worker disposed'))
  pending.clear()
}
