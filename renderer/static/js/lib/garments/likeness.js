// How alike two pictures of a garment look. The full app asked an AI model (DINOv2) for that; the renderer runs no
// models, so there's never an answer (null), and the 3D view's check goes on without it (look_check.js), as it did
// whenever the model couldn't load.

export function warmLikeness() {}

export async function likeness() { return null }

export function cosine(x, y) {
  let dot = 0, nx = 0, ny = 0
  for (let i = 0; i < x.length; i++) { dot += x[i] * y[i]; nx += x[i] * x[i]; ny += y[i] * y[i] }
  return dot / Math.sqrt(nx * ny || 1)
}

export async function photoSummary() { return null }

export function likenessReady() { return false }

export async function likenessWithin() { return false }

export async function likenessQuick() { return false }
