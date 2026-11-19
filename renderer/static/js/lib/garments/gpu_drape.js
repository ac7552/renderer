// The drape's solver on the GPU (WebGPU compute): every small step of Drape#step, in the same order, on the
// graphics card. The cloth moves under gravity; seams pull together while it's sewn; its threads (stretch)
// and its bends hold their lengths; folds keep off each other; and each point keeps off the skin (with
// friction), off what's worn under it, outside a skirt's envelope, inside a tuck, off the feet, on the arms
// (a cuff stops at the hand), off the hands, above the floor and at its waistband; bands ride on the edges
// they're sewn to. The same rules as drape.js, written once more for the GPU.
//
// The CPU's drape stays the one the rest of the code works with. A GpuMirror keeps a copy of a Drape on the
// card: Drape#step hands each frame to it (GpuDrape#step), and the worker reads the points back into the
// Drape after each frame (GpuDrape#sync), so what decides when sewing stops, when the cloth is still, and the
// coarse cloth's handing over to the fine one all read drape.x as before. Anything the CPU changes between
// frames (the seams closed, bands let go, a new pose, a new body) is seen and copied over before the next.
//
// The CPU goes through each thread in turn (Gauss-Seidel); here the threads are split into colours, no two of
// one colour sharing a point, and each colour is solved at once: the same solve in a different order. Cloth
// touching itself is solved all at once too (each point takes its own half of every push), where the CPU
// pushes pair by pair.
//
// Which is quicker depends on the card and the cloth: a GPU has a cost per frame however few points there
// are, so a coarse cloth can be quicker on the CPU. Each drape tries a few frames of each and keeps the
// quicker (see GpuDrape#step).
//
//   const gpu = await GpuDrape.start()   // null without WebGPU
//   Drape.gpu = gpu                      // from now on Drape#step uses it where it's quicker
//   ... drape.step() ...; if (gpu.pending.size) await gpu.sync()
import { CLOTHS, SQUEEZE, TETHER } from "lib/garments/drape"
import { ClothKernel, KERNEL_ON } from "lib/garments/cloth_kernel"

const FRAME = 1 / 60, SUBSTEPS = 10, GRAVITY = -9.81
const GROUP = 64
const HASH = 1 << 16
// (As drape.js and body.js have them.)
const HEM_BEND = 0.08
const MAX_SEW_STEP = 0.0025
const CUFF_PAST_WRIST = 0.03, HAND_REACH = 0.12, CUFF_EASE = 0.08
const SHOE_PUSH = 0.006
const HAND_STEP = 0.004, HAND_REACH_OUT = 0.02
const MAX_ELLIPSOIDS = 16
// The trial: frames timed on each before choosing (the first of each not counted: it sets things up).
const TRIAL = 6
// The GPU is kept when it's at least this much quicker.
const GPU_MARGIN = 0.9
// Fewer points than this always stay on the CPU.
const MIN_POINTS = 300

// The frame's numbers, as 4-byte words in one uniform block (P[word]), with where each part of the data
// blobs starts.
const W = {
  n: 0, flags: 1, ells: 2, handsMask: 3,
  h: 4, fall: 5, drag: 6, thick: 7,
  keep: 8, radius: 9, squeeze: 10, cEdge: 11,
  cRib: 12, cBend: 13, cHem: 14, floorY: 15,
  fieldMin: 16, layerMin: 24,   // each: min x, y, z, cell, dims x, y, z, band
  envTop: 32, envBottom: 33, tuckTop: 34, tuckRaise: 35,
  tuckInside: 36, sewStep: 37,
  oW: 40, oSewnAt: 41, oThreads: 42, oFlags: 43,
  oNbStart: 44, oNb: 45, oAttachOf: 46, oAttachSrc: 47,
  oAttachF: 48, oFeet: 49, oFeetU: 50, oArms: 51,
  oHands: 52, oEll: 53,
  // Two torso tables (a skirt's envelope's and a tuck's; usually the same one): floor, rows, sectors, centre, hull.
  t1: 56, t2: 61
}
const WORDS = 68
const FLAG = { STILL: 1, SEWN: 2, LAYERS: 4, ENVELOPE: 8, TUCK_PRESS: 16, QUIET: 32, FEET: 64, ARMS: 128, HANDS: 256, FLOOR: 512, RING: 1024, SNUG: 2048 }
// Per point (U[oFlags + i]): which arm (bits 0-1: 1 left, 2 right), which leg (bits 2-3), on a tucked
// piece (bit 4), on the waistband (bit 5).
const PF = { TUCK: 16, RING: 32 }
// What each constraint is: a thread (0), a rib thread (1), a bend (2), a hem's bend (3), a seam being sewn (4),
// a tether (5: drape.js's TETHER, a thread that only pulls).
const CLASS = { EDGE: 0, RIB: 1, BEND: 2, HEM: 3, SEW: 4, TETHER: 5 }

const SHADER = /* wgsl */ `
const GROUP = ${GROUP}u;
const HASH = ${HASH}u;
@group(0) @binding(0) var<uniform> P: array<vec4<u32>, ${WORDS / 4}>;
// The cloth: x (where it is) [0, n), v (its speed) [n, 2n), p (where it's going this small step) [2n, 3n),
// and a scratch [3n, 4n) (a push from the cloth near it; how far along its arm).
@group(0) @binding(1) var<storage, read_write> S: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> F: array<f32>;
@group(0) @binding(3) var<storage, read> U: array<u32>;
// The hashed grid for cloth touching itself (head [0, HASH), next [HASH, HASH + n)), then each arm's overshoot.
@group(0) @binding(4) var<storage, read_write> A: array<atomic<i32>>;
@group(0) @binding(5) var dist: texture_3d<f32>;
@group(0) @binding(6) var norm: texture_3d<f32>;
@group(0) @binding(7) var ldist: texture_3d<f32>;
@group(0) @binding(8) var lnorm: texture_3d<f32>;
struct Colour { offset: u32, count: u32 }
@group(1) @binding(0) var<uniform> C: Colour;

fn pu(k: u32) -> u32 { return P[k / 4u][k % 4u]; }
fn pf(k: u32) -> f32 { return bitcast<f32>(pu(k)); }
fn has(f: u32) -> bool { return (pu(${W.flags}u) & f) != 0u; }
fn X(i: u32) -> vec3<f32> { return S[i].xyz; }
fn V(i: u32) -> vec3<f32> { return S[pu(0u) + i].xyz; }
fn Pp(i: u32) -> vec3<f32> { return S[2u * pu(0u) + i].xyz; }
fn setP(i: u32, q: vec3<f32>) { S[2u * pu(0u) + i] = vec4<f32>(q, 0.0); }

@compute @workgroup_size(GROUP) fn predict(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x;
  // (The arms' overshoot starts each small step at nothing.)
  if (i < 2u) { atomicStore(&A[HASH + pu(0u) + i], 0); }
  if (i >= pu(0u)) { return; }
  var v = V(i); v.y += pf(${W.fall}u);
  S[pu(0u) + i] = vec4<f32>(v, 0.0);
  setP(i, X(i) + v * pf(${W.h}u));
}

// One colour of constraints: none of them shares a point, so each moves its two points without a race.
@compute @workgroup_size(GROUP) fn solve(@builtin(global_invocation_id) id: vec3<u32>) {
  let k = id.x; if (k >= C.count) { return; }
  let o = pu(${W.oThreads}u) + 4u * (C.offset + k);
  let a = U[o]; let b = U[o + 1u]; let rest = bitcast<f32>(U[o + 2u]); let cls = U[o + 3u];
  let pa = Pp(a); let pb = Pp(b);
  let d = pa - pb; let len = length(d);
  if (cls == ${CLASS.SEW}u) {
    // A seam being sewn: its two points move together a little at a time (Drape#pullSeams).
    if (len < 1e-6) { return; }
    let close = min(len, pf(${W.sewStep}u)) / len * 0.5;
    setP(a, pa - d * close); setP(b, pb + d * close);
    return;
  }
  if (len < 1e-9) { return; }
  // A tether only pulls: slack, it does nothing.
  if (cls == ${CLASS.TETHER}u && len <= rest) { return; }
  let wa = F[pu(${W.oW}u) + a]; let wb = F[pu(${W.oW}u) + b];
  var alpha = pf(${W.cEdge}u);
  if (cls == ${CLASS.TETHER}u) { alpha *= ${TETHER || 1}.0; }
  if (cls == ${CLASS.RIB}u) { alpha = pf(${W.cRib}u); }
  if (cls == ${CLASS.BEND}u) { alpha = pf(${W.cBend}u); }
  if (cls == ${CLASS.HEM}u) { alpha = pf(${W.cHem}u); }
  if (cls <= ${CLASS.RIB}u && len < rest) { alpha *= pf(${W.squeeze}u); }
  let lambda = -(len - rest) / (wa + wb + alpha);
  let s = d / len * lambda;
  setP(a, pa + s * wa); setP(b, pb - s * wb);
}

// Cloth touching itself: a hashed grid of the points (as Drape#selfCollide's).
fn keyOf(c: vec3<i32>) -> u32 { return u32((c.x * 73856093) ^ (c.y * 19349663) ^ (c.z * 83492791)) & (HASH - 1u); }
@compute @workgroup_size(GROUP) fn hashClear(@builtin(global_invocation_id) id: vec3<u32>) {
  if (id.x < HASH) { atomicStore(&A[id.x], -1); }
}
@compute @workgroup_size(GROUP) fn hashInsert(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x; if (i >= pu(0u)) { return; }
  let prev = atomicExchange(&A[keyOf(vec3<i32>(floor(Pp(i) / pf(${W.radius}u))))], i32(i));
  atomicStore(&A[HASH + i], prev);
}
fn underTuck(q: vec3<f32>) -> bool {
  let top = pf(${W.tuckTop}u); let raise = pf(${W.tuckRaise}u);
  if (q.y > top + raise) { return false; }
  return q.y <= top + raise * max(0.0, -cos(atan2(q.x, q.z - centreAt(${W.t2}u, q.y))));
}
fn quiet(i: u32, q: vec3<f32>) -> bool {
  return has(${FLAG.QUIET}u) && (U[pu(${W.oFlags}u) + i] & ${PF.TUCK}u) != 0u && underTuck(q);
}
@compute @workgroup_size(GROUP) fn selfPush(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x; let n = pu(0u); if (i >= n) { return; }
  let r = pf(${W.radius}u); let r2 = r * r;
  let pi = Pp(i);
  let qi = quiet(i, pi);
  let c = vec3<i32>(floor(pi / r));
  let nb0 = U[pu(${W.oNbStart}u) + i]; let nb1 = U[pu(${W.oNbStart}u) + i + 1u];
  var push = vec3<f32>(0.0);
  for (var ox = -1; ox <= 1; ox++) { for (var oy = -1; oy <= 1; oy++) { for (var oz = -1; oz <= 1; oz++) {
    var j = atomicLoad(&A[keyOf(c + vec3<i32>(ox, oy, oz))]);
    var guard = 0u;
    loop {
      if (j < 0 || guard > 1024u) { break; }
      guard++;
      let ju = u32(j);
      if (ju != i) {
        let pj = Pp(ju);
        let d = pj - pi; let d2 = dot(d, d);
        if (d2 < r2 && d2 >= 1e-14 && !(qi && quiet(ju, pj))) {
          var adjacent = false;
          for (var k = nb0; k < nb1; k++) { if (U[pu(${W.oNb}u) + k] == ju) { adjacent = true; break; } }
          if (!adjacent) { let dd = sqrt(d2); push -= d * ((r - dd) / dd * 0.5); }
        }
      }
      j = atomicLoad(&A[HASH + ju]);
    }
  } } }
  S[3u * n + i] = vec4<f32>(push, 0.0);
}
@compute @workgroup_size(GROUP) fn selfApply(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x; let n = pu(0u); if (i >= n) { return; }
  setP(i, Pp(i) + S[3u * n + i].xyz);
}

// The skin's distance at a point and its normal there (blended from the 8 grid points round it), as
// SkinField#at does it, with its ellipsoids (the egg head); the band (far outside) off the grid, with no normal.
fn gridAt(q: vec3<f32>, layer: bool) -> vec4<f32> {
  let base = select(${W.fieldMin}u, ${W.layerMin}u, layer);
  let mn = vec3<f32>(pf(base), pf(base + 1u), pf(base + 2u)); let cell = pf(base + 3u);
  let dims = vec3<f32>(f32(pu(base + 4u)), f32(pu(base + 5u)), f32(pu(base + 6u))); let band = pf(base + 7u);
  let f = (q - mn) / cell; let c = floor(f);
  if (any(c < vec3<f32>(0.0)) || any(c >= dims - vec3<f32>(1.0))) { return vec4<f32>(band, 0.0, 0.0, 0.0); }
  let u = f - c; let g = vec3<i32>(c);
  var d = 0.0; var m = vec3<f32>(0.0);
  for (var k = 0; k < 8; k++) {
    let o = vec3<i32>(k & 1, (k >> 1u) & 1, k >> 2u);
    let wgt = select(1.0 - u.x, u.x, o.x == 1) * select(1.0 - u.y, u.y, o.y == 1) * select(1.0 - u.z, u.z, o.z == 1);
    if (layer) { d += textureLoad(ldist, g + o, 0).x * wgt; m += textureLoad(lnorm, g + o, 0).xyz * wgt; }
    else { d += textureLoad(dist, g + o, 0).x * wgt; m += textureLoad(norm, g + o, 0).xyz * wgt; }
  }
  let l = length(m);
  if (l < 1e-3 / 127.0) { return vec4<f32>(band, 0.0, 0.0, 0.0); }
  return vec4<f32>(d, m / l);
}
fn fieldAt(q: vec3<f32>) -> vec4<f32> {
  var best = gridAt(q, false);
  for (var k = 0u; k < pu(${W.ells}u); k++) {
    let o = pu(${W.oEll}u) + 6u * k;
    let centre = vec3<f32>(F[o], F[o + 1u], F[o + 2u]); let radii = vec3<f32>(F[o + 3u], F[o + 4u], F[o + 5u]);
    let pp = (q - centre) / radii;
    let k0 = sqrt(dot(pp, pp));
    let g = pp / radii;
    let k1 = sqrt(dot(g, g));
    if (k1 < 1e-9) { continue; }
    let e = k0 * (k0 - 1.0) / k1;
    if (e < best.x) { best = vec4<f32>(e, g / k1); }
  }
  return best;
}

// The torso's table (body.js's): its middle by height, and its convex outline's reach by angle.
fn rowOf(t: u32, y: f32) -> u32 {
  let r = floor((y - pf(t)) / 0.01);
  return u32(clamp(r, 0.0, f32(pu(t + 1u)) - 1.0));
}
fn centreAt(t: u32, y: f32) -> f32 { return F[pu(t + 3u) + rowOf(t, y)]; }
fn envelopeAt(t: u32, y: f32, a: f32) -> f32 {
  let r = rowOf(t, y); let sectors = pu(t + 2u); let s = f32(sectors);
  let tt = ((a / 6.283185307179586) * s - 0.5 + s) % s;
  let k = u32(floor(tt)) % sectors; let u = tt - floor(tt);
  let h = pu(t + 4u) + r * sectors;
  return F[h + k] * (1.0 - u) + F[h + (k + 1u) % sectors] * u;
}

// A foot's outline at a height (an anticlockwise [x, z] polygon): row r's (start in F, count) in its table.
fn hullRow(foot: u32, r: u32) -> vec2<u32> {
  let o = U[pu(${W.oFeetU}u) + foot] + 2u * r;
  return vec2<u32>(U[o], U[o + 1u]);
}
fn hullPoint(h: vec2<u32>, k: u32) -> vec2<f32> { return vec2<f32>(F[h.x + 2u * k], F[h.x + 2u * k + 1u]); }
fn insideHull(h: vec2<u32>, px: f32, pz: f32) -> bool {
  for (var k = 0u; k < h.y; k++) {
    let a = hullPoint(h, k); let c = hullPoint(h, (k + 1u) % h.y);
    if ((c.x - a.x) * (pz - a.y) - (c.y - a.y) * (px - a.x) < 0.0) { return false; }
  }
  return true;
}
// Drape#stayOffFeet for one point (side 1: the left foot, 2: the right). Returns where it goes.
fn offFoot(side: u32, q: vec3<f32>, x: vec3<f32>) -> vec3<f32> {
  let foot = side - 1u;
  let o = pu(${W.oFeet}u) + 12u * foot;
  let top = F[o]; let floorY = F[o + 1u]; let step = F[o + 2u]; let rows = u32(F[o + 3u]);
  let thick = pf(${W.thick}u);
  let y = q.y;
  if (rows == 0u || y > top) { return q; }
  if (has(${FLAG.SNUG}u)) {
    let low = F[o + 4u];
    if (y < low) { return vec3<f32>(x.x + (q.x - x.x) * 0.3, low, x.z + (q.z - x.z) * 0.3); }
  }
  let rf = floor((y - floorY) / step);
  if (rf < 0.0 || rf >= f32(rows)) { return q; }
  let r = u32(rf);
  let h = hullRow(foot, r);
  if (h.y == 0u) { return q; }
  let px = q.x; let pz = q.z;
  var best = 1e30; var bx = 0.0; var bz = 0.0; var inside = true;
  for (var k = 0u; k < h.y; k++) {
    let a = hullPoint(h, k); let c = hullPoint(h, (k + 1u) % h.y);
    let ex = c.x - a.x; let ez = c.y - a.y; var len = sqrt(ex * ex + ez * ez); if (len == 0.0) { len = 1.0; }
    let d = (ex * (pz - a.y) - ez * (px - a.x)) / len;
    if (d < -thick) { inside = false; break; }
    if (d < best) { best = d; bx = ez / len; bz = -ex / len; }
  }
  if (!inside) { return q; }
  var rr = r;
  loop {
    if (rr + 1u >= rows) { break; }
    let next = hullRow(foot, rr + 1u);
    if (next.y == 0u || !insideHull(next, px, pz)) { break; }
    rr++;
  }
  let up = floorY + f32(rr + 1u) * step - y;
  let shod = F[o + 5u] > 0.5;
  let onTop = select(true, (px - F[o + 6u]) * F[o + 8u] + (pz - F[o + 7u]) * F[o + 9u] > F[o + 10u], shod);
  if (onTop && up < best) {
    return vec3<f32>(x.x + (px - x.x) * 0.3, y + up + thick, x.z + (pz - x.z) * 0.3);
  }
  let shove = select(best + thick, min(best + thick, ${SHOE_PUSH}), shod);
  return vec3<f32>(px + bx * shove, y, pz + bz * shove);
}

// Where a point falls along an arm (t, metres from the shoulder; negative before it) and how far it is from
// the arm's line (body.js's locate).
fn armLocate(o: u32, q: vec3<f32>) -> vec2<f32> {
  let c0 = vec3<f32>(F[o], F[o + 1u], F[o + 2u]);
  let c1 = vec3<f32>(F[o + 3u], F[o + 4u], F[o + 5u]);
  let before = dot(q - c0, normalize(c1 - c0));
  if (before < 0.0) { return vec2<f32>(before, length(q - c0)); }
  var best = vec2<f32>(0.0, 1e30);
  for (var k = 1u; k < 4u; k++) {
    let a = vec3<f32>(F[o + 3u * (k - 1u)], F[o + 3u * (k - 1u) + 1u], F[o + 3u * (k - 1u) + 2u]);
    let b = vec3<f32>(F[o + 3u * k], F[o + 3u * k + 1u], F[o + 3u * k + 2u]);
    let d = b - a; let span = dot(d, d);
    let u = clamp(dot(q - a, d) / span, 0.0, 1.0);
    let dd = length(q - (a + d * u));
    if (dd < best.y) { best = vec2<f32>(F[o + 12u + k - 1u] + u * sqrt(span), dd); }
  }
  return best;
}

// Off the skin (with friction), off what's worn under, out to a skirt's envelope, into a tuck, off the feet;
// and where each sleeve point is along its arm, for the cuffs (collideHold moves them).
@compute @workgroup_size(GROUP) fn collide(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x; let n = pu(0u); if (i >= n) { return; }
  let x = X(i); var q = Pp(i);
  let thick = pf(${W.thick}u); let keep = pf(${W.keep}u);
  let flags = U[pu(${W.oFlags}u) + i];
  let s = fieldAt(q);
  if (s.x < thick) {
    let nrm = s.yzw;
    q += nrm * (thick - s.x);
    let m = q - x; let t = m - dot(m, nrm) * nrm;
    q -= t * (1.0 - keep);
  } else if (has(${FLAG.TUCK_PRESS}u) && (flags & ${PF.TUCK}u) != 0u && s.x < 0.05 && dot(s.yzw, s.yzw) > 0.5 && underTuck(q)) {
    // Tucked in, pressed onto the body all the way round, into its hollows too.
    q -= s.yzw * (s.x - thick);
  }
  let arm = flags & 3u;
  if (has(${FLAG.LAYERS}u) && arm == 0u) {
    let l = gridAt(q, true);
    if (l.x < thick) { q += l.yzw * (thick - l.x); }
  }
  if (has(${FLAG.ENVELOPE}u) && q.y <= pf(${W.envTop}u) && q.y >= pf(${W.envBottom}u)) {
    let cz = centreAt(${W.t1}u, q.y);
    let z = q.z - cz; let r = sqrt(q.x * q.x + z * z);
    if (r >= 1e-6) {
      let reach = envelopeAt(${W.t1}u, q.y, atan2(q.x, z)) + thick;
      if (r < reach) { let k = reach / r; q = vec3<f32>(q.x * k, q.y, cz + z * k); }
    }
  }
  if (has(${FLAG.TUCK_PRESS}u) && (flags & ${PF.TUCK}u) != 0u && underTuck(q)) {
    let cz = centreAt(${W.t2}u, q.y);
    let z = q.z - cz; let r = sqrt(q.x * q.x + z * z);
    let reach = envelopeAt(${W.t2}u, q.y, atan2(q.x, z)) + pf(${W.tuckInside}u);
    if (r > reach) { let k = reach / r; q = vec3<f32>(q.x * k, q.y, cz + z * k); }
  }
  let leg = (flags >> 2u) & 3u;
  if (has(${FLAG.FEET}u) && leg != 0u) { q = offFoot(leg, q, x); }
  if (has(${FLAG.ARMS}u) && arm != 0u) {
    let o = pu(${W.oArms}u) + 24u * (arm - 1u);
    let at = armLocate(o, q);
    let limit = F[o + 16u];
    S[3u * n + i] = vec4<f32>(select(at.x, -1e30, at.y > ${HAND_REACH}), 0.0, 0.0, 0.0);
    if (at.x > limit && at.y <= ${HAND_REACH}) { atomicMax(&A[HASH + n + arm - 1u], bitcast<i32>(at.x - limit)); }
  }
  setP(i, q);
}

// body.js's keepOffHands for one point and one hand: cloth in the hand's slab goes in past its inner face,
// stopping at the skin.
fn offHand(o: u32, q0: vec3<f32>) -> vec3<f32> {
  let wrist = vec3<f32>(F[o], F[o + 1u], F[o + 2u]);
  let along = vec3<f32>(F[o + 3u], F[o + 4u], F[o + 5u]);
  let inward = vec3<f32>(F[o + 6u], F[o + 7u], F[o + 8u]);
  let across = vec3<f32>(F[o + 9u], F[o + 10u], F[o + 11u]);
  let span = F[o + 12u]; let start = F[o + 13u]; let pad = F[o + 14u]; let steps = u32(F[o + 15u]);
  let thick = pf(${W.thick}u);
  let room = thick + pad; let far = span + 0.08;
  let r = q0 - wrist;
  if (any(abs(r) > vec3<f32>(far))) { return q0; }
  let t = dot(r, along);
  if (t < start || t > span + 0.01) { return q0; }
  let s = min(steps - 1u, u32(floor(t / 0.01 + 0.5)));
  let inner = F[u32(F[o + 16u]) + s]; let outer = F[u32(F[o + 17u]) + s];
  let lo = F[u32(F[o + 18u]) + s]; let hi = F[u32(F[o + 19u]) + s];
  let b = dot(r, across);
  if (b < lo - room || b > hi + room) { return q0; }
  let a = dot(r, inward);
  if (a >= inner + room || a < outer - ${HAND_REACH_OUT}) { return q0; }
  var push = inner + room - a;
  for (var k = ${HAND_STEP}; k < push + ${HAND_STEP}; k += ${HAND_STEP}) {
    let tt = min(k, push);
    if (fieldAt(q0 + inward * tt).x < thick) { push = max(0.0, tt - ${HAND_STEP}); break; }
  }
  var q = q0 + inward * push;
  let s2 = fieldAt(q);
  if (s2.x < thick) { q += s2.yzw * (thick - s2.x); }
  if (distance(q, q0) < 1e-6) { return q0; }
  return q;
}

// The cuffs held at the hands, off the hands, on the floor, at the waistband.
@compute @workgroup_size(GROUP) fn collideHold(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x; let n = pu(0u); if (i >= n) { return; }
  let x = X(i); var q = Pp(i);
  let flags = U[pu(${W.oFlags}u) + i];
  let arm = flags & 3u;
  if (has(${FLAG.ARMS}u) && arm != 0u) {
    let over = bitcast<f32>(atomicLoad(&A[HASH + n + arm - 1u]));
    if (over > 0.0) {
      let o = pu(${W.oArms}u) + 24u * (arm - 1u);
      let limit = F[o + 16u]; let eased = F[o + 17u];
      let at = S[3u * n + i].x;
      if (at > eased) {
        let u = min(1.0, (at - eased) / (limit + over - eased));
        let back = over * u * u * (3.0 - 2.0 * u);
        q -= vec3<f32>(F[o + 18u], F[o + 19u], F[o + 20u]) * back;
      }
    }
  }
  if (has(${FLAG.HANDS}u)) {
    for (var k = 0u; k < 4u; k++) {
      if ((pu(${W.handsMask}u) & (1u << k)) != 0u) { q = offHand(pu(${W.oHands}u) + 20u * k, q); }
    }
  }
  if (has(${FLAG.FLOOR}u) && q.y < pf(${W.floorY}u)) {
    q = vec3<f32>(x.x + (q.x - x.x) * 0.3, pf(${W.floorY}u), x.z + (q.z - x.z) * 0.3);
  }
  if (has(${FLAG.RING}u) && (flags & ${PF.RING}u) != 0u) {
    if (has(${FLAG.SEWN}u)) { q.y = max(q.y, F[pu(${W.oSewnAt}u) + i] - 0.01); } else { q.y = x.y; }
  }
  setP(i, q);
}

// Bands ride on the edges they're sewn to; then each point takes its new place and its speed.
@compute @workgroup_size(GROUP) fn finish(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x; let n = pu(0u); if (i >= n) { return; }
  var q = Pp(i);
  let k = U[pu(${W.oAttachOf}u) + i];
  if (k != 0xffffffffu) {
    let a = U[pu(${W.oAttachSrc}u) + 2u * k]; let b = U[pu(${W.oAttachSrc}u) + 2u * k + 1u];
    let o = pu(${W.oAttachF}u) + 5u * k;
    let t = F[o]; let off = F[o + 1u];
    q = Pp(a) * (1.0 - t) + Pp(b) * t + vec3<f32>(F[o + 2u], F[o + 3u], F[o + 4u]) * off;
  }
  let x = X(i);
  let v = select((q - x) / pf(${W.h}u) * pf(${W.drag}u), vec3<f32>(0.0), has(${FLAG.STILL}u));
  S[n + i] = vec4<f32>(v, 0.0);
  S[i] = vec4<f32>(q, 0.0);
}
`

// Constraints (pairs of points, rest lengths, and a number for each, its compliance or its kind) coloured
// greedily so no two of one colour share a point: { threads (Uint8Array, 16 bytes each: a, b, rest, that
// number), colours: [[offset, count], ...] }.
export function coloured(lists) {
  const all = []
  for (const { pairs, rest, alphaOf } of lists) {
    const used = new Map()
    const colourOf = new Int32Array(rest.length)
    let most = 0
    for (let e = 0; e < rest.length; e++) {
      const a = pairs[2 * e], b = pairs[2 * e + 1]
      const ua = used.get(a) ?? 0n, ub = used.get(b) ?? 0n
      let c = 0
      while (((ua | ub) >> BigInt(c)) & 1n) c++
      colourOf[e] = c; most = Math.max(most, c + 1)
      used.set(a, ua | (1n << BigInt(c))); used.set(b, ub | (1n << BigInt(c)))
    }
    const groups = Array.from({ length: most }, () => [])
    for (let e = 0; e < rest.length; e++) groups[colourOf[e]].push(e)
    for (const group of groups) all.push(group.map(e => [pairs[2 * e], pairs[2 * e + 1], rest[e], alphaOf(e)]))
  }
  const total = all.reduce((n, g) => n + g.length, 0)
  const buffer = new ArrayBuffer(16 * Math.max(1, total)), u = new Uint32Array(buffer), f = new Float32Array(buffer)
  const colours = []
  let k = 0
  for (const group of all) {
    colours.push([k, group.length])
    for (const [a, b, rest, alpha] of group) { u[4 * k] = a; u[4 * k + 1] = b; f[4 * k + 2] = rest; f[4 * k + 3] = alpha; k++ }
  }
  return { threads: new Uint8Array(buffer), colours }
}

// The card, the shader's pipelines, and the drapes on it. One a worker.
export class GpuDrape {
  // A GpuDrape on this device's card, or null where there's no WebGPU (or it fails to start).
  // force: every drape on the card, without trying the CPU (?gpu=force, for checking the GPU's drapes).
  static async start({ powerPreference = "high-performance", force = false } = {}) {
    try {
      if (typeof navigator === "undefined" || !navigator.gpu) return null
      const adapter = await navigator.gpu.requestAdapter({ powerPreference })
      if (!adapter) return null
      const device = await adapter.requestDevice()
      device.pushErrorScope("validation")
      const gpu = new GpuDrape(device, adapter)
      gpu.force = force
      const error = await device.popErrorScope()
      if (error) { device.destroy(); console.warn("[gpu] drape:", error.message); return null }
      return gpu
    } catch (error) {
      console.warn("[gpu] drape:", error?.message ?? error)
      return null
    }
  }

  constructor(device, adapter) {
    this.device = device
    this.adapter = adapter
    this.failed = null
    this.pending = new Set()
    device.lost?.then(info => { if (!this.stopped) this.fail(`the GPU was lost (${info.message})`) })
    device.addEventListener?.("uncapturederror", event => this.fail(event.error?.message ?? "a GPU error"))
    const module = device.createShaderModule({ code: SHADER })
    const B = GPUShaderStage.COMPUTE
    this.layout = device.createBindGroupLayout({ entries: [
      { binding: 0, visibility: B, buffer: { type: "uniform" } },
      { binding: 1, visibility: B, buffer: { type: "storage" } },
      { binding: 2, visibility: B, buffer: { type: "read-only-storage" } },
      { binding: 3, visibility: B, buffer: { type: "read-only-storage" } },
      { binding: 4, visibility: B, buffer: { type: "storage" } },
      // (Distances are 32-bit floats, read whole; normals 8-bit.)
      ...[5, 6, 7, 8].map(binding => ({ binding, visibility: B, texture: { sampleType: binding % 2 ? "unfilterable-float" : "float", viewDimension: "3d" } }))
    ] })
    this.colourLayout = device.createBindGroupLayout({ entries: [
      { binding: 0, visibility: B, buffer: { type: "uniform", hasDynamicOffset: true, minBindingSize: 8 } }
    ] })
    const layout = device.createPipelineLayout({ bindGroupLayouts: [this.layout, this.colourLayout] })
    this.pipelines = Object.fromEntries(["predict", "solve", "hashClear", "hashInsert", "selfPush", "selfApply", "collide", "collideHold", "finish"]
      .map(entryPoint => [entryPoint, device.createComputePipeline({ layout, compute: { module, entryPoint } })]))
    // A field with nothing in it (for a drape with nothing worn under it).
    this.emptyField = this.fieldTextures({ dims: [2, 2, 2], distance: new Float32Array(8).fill(1), normal: new Int8Array(24) })
  }

  get description() {
    const info = this.adapter.info ?? {}
    return [info.vendor, info.architecture, info.description].filter(Boolean).join(" ") || "the GPU"
  }

  fail(reason) {
    if (this.failed) return
    this.failed = reason
    console.warn("[gpu] drape: back to the CPU:", reason)
  }

  stop() {
    this.stopped = true
    this.device.destroy()
  }

  // The skin's field as two 3D textures: distance, and the normal (as SkinField keeps it, -127..127).
  fieldTextures(field) {
    const device = this.device
    const [nx, ny, nz] = field.dims
    const usage = GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST
    const dist = device.createTexture({ size: [nx, ny, nz], dimension: "3d", format: "r32float", usage })
    device.queue.writeTexture({ texture: dist }, field.distance, { bytesPerRow: 4 * nx, rowsPerImage: ny }, [nx, ny, nz])
    const normals = new Int8Array(4 * nx * ny * nz)
    for (let g = 0; g < nx * ny * nz; g++) { normals[4 * g] = field.normal[3 * g]; normals[4 * g + 1] = field.normal[3 * g + 1]; normals[4 * g + 2] = field.normal[3 * g + 2] }
    const norm = device.createTexture({ size: [nx, ny, nz], dimension: "3d", format: "rgba8snorm", usage })
    device.queue.writeTexture({ texture: norm }, normals, { bytesPerRow: 4 * nx, rowsPerImage: ny }, [nx, ny, nz])
    return { dist, norm }
  }

  // Drape#step's frame on the card, when that's where this drape goes (see the trial). Returns false to have
  // the CPU do it.
  step(drape, options) {
    if (this.failed || drape.noGpu) return false
    const trial = drape.gpuTrial ??= { cpu: [], gpu: [], choice: this.force ? "gpu" : drape.x.length / 3 < MIN_POINTS ? "cpu" : null }
    if (trial.choice === "cpu") return false
    // Trying: the CPU's frames first (timed by Drape#step: see cpuTime), then the card's.
    if (!trial.choice && trial.cpu.length < TRIAL) return false
    try {
      const mirror = drape.gpuMirror ??= new GpuMirror(this, drape)
      mirror.frame(options)
      this.pending.add(mirror)
      return true
    } catch (error) {
      this.fail(String(error?.stack ?? error))
      this.release(drape)
      return false
    }
  }

  // How long the CPU took over a frame of this drape (Drape#step says, while the trial runs).
  cpuTime(drape, ms) {
    const trial = drape.gpuTrial
    if (trial && !trial.choice) trial.cpu.push(ms)
  }

  // Waits for the card's frames and reads their points back into each drape. A drape whose frame failed (or
  // a lost GPU) stays where it last was, and goes on on the CPU.
  async sync() {
    const mirrors = [...this.pending]
    this.pending.clear()
    for (const mirror of mirrors) {
      const drape = mirror.drape
      const t = performance.now()
      try {
        if (this.failed) throw new Error(this.failed)
        await mirror.pull()
      } catch (error) {
        this.fail(String(error?.message ?? error))
        drape.v.fill(0)
        this.release(drape)
        continue
      }
      const trial = drape.gpuTrial
      if (trial && !trial.choice) {
        trial.gpu.push(mirror.encodeMs + performance.now() - t)
        if (trial.gpu.length >= TRIAL + 1) {
          const cpu = median(trial.cpu.slice(1)), gpu = median(trial.gpu.slice(1))
          trial.choice = gpu < cpu * GPU_MARGIN ? "gpu" : "cpu"
          trial.ms = { cpu, gpu }
          console.info(`[gpu] drape of ${drape.x.length / 3} points: ${cpu.toFixed(2)} ms a frame on the CPU, ${gpu.toFixed(2)} on the GPU; the ${trial.choice.toUpperCase()} from here`)
          if (trial.choice === "cpu") {
            // (Its speeds, for the CPU to go on from.)
            await mirror.pullSpeed().catch(() => drape.v.fill(0))
            this.release(drape)
          }
        }
      }
    }
  }

  // A drape's copy on the card let go (its garment's gone, or it's back on the CPU).
  release(drape) {
    const mirror = drape.gpuMirror
    if (!mirror) return
    mirror.destroy()
    this.pending.delete(mirror)
    drape.gpuMirror = null
    if (this.failed) drape.noGpu = true
  }
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.floor(sorted.length / 2)] ?? Infinity
}

// One drape's copy on the card: its points, its constraints and the body's shapes it keeps to.
class GpuMirror {
  constructor(gpu, drape) {
    this.gpu = gpu
    this.device = gpu.device
    this.drape = drape
    this.uniform = this.device.createBuffer({ size: 4 * WORDS, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST })
    this.words = new ArrayBuffer(4 * WORDS)
    this.wu = new Uint32Array(this.words)
    this.wf = new Float32Array(this.words)
    this.seen = {}
    this.n = 0
    this.lastX = null
    this.encodeMs = 0
  }

  // Whatever the CPU changed since the last frame, copied over: the cloth's make-up (seams closed), bands let
  // go, the body (a new pose), the cloth moved (laid on a new body, or handed over from the coarse cloth).
  refresh() {
    const d = this.drape
    if (d.ring && d.sewn && !d.ring.sewnAt) {
      // (As Drape#holdRing does at the first small step once sewn: where the waistband is then.)
      const points = d.map ? d.ring.order.map(i => d.map[i]) : d.ring.order
      d.ring.sewnAt = new Map(points.map(j => [j, d.x[3 * j + 1]]))
    }
    const now = {
      edges: d.edges, bends: d.bends, tethers: d.tethers, sewing: d.sewing, map: d.map, n: d.x.length / 3,
      field: d.field, layers: d.field?.layers ?? null,
      attach: d.attach, envelope: d.envelope, tuck: d.tuck, feet: d.feet, arms: d.arms, hands: d.hands,
      ring: d.ring?.sewnAt ?? d.ring, snug: d.snug, w: d.w
    }
    const changed = key => now[key] !== this.seen[key]
    let data = false
    if (["edges", "bends", "tethers", "sewing", "map", "n"].some(changed)) { this.buildState(now.n); data = true }
    if (changed("field") || changed("layers")) { this.buildFields(); data = true }
    if (data || Object.keys(now).some(changed)) this.buildData()
    this.seen = now
    // The cloth moved on the CPU: its points and speeds copied over.
    if (!this.lastX || !sameArray(this.lastX, d.x)) this.upload()
  }

  // The points' buffer, the hashed grid, the constraints in colours.
  buildState(n) {
    const device = this.device, d = this.drape
    this.n = n
    for (const b of [this.state, this.atomics, this.ranges, this.staging]) b?.destroy()
    this.state = device.createBuffer({ size: 64 * n, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.COPY_SRC })
    this.atomics = device.createBuffer({ size: 4 * (HASH + n + 4), usage: GPUBufferUsage.STORAGE })
    this.staging = device.createBuffer({ size: 16 * n, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ })
    const sewing = d.sewn ? new Int32Array(0) : d.sewing ?? new Int32Array(0)
    const sewCount = sewing.length / 2
    const tethers = d.tethers ?? new Int32Array(0), tetherRest = d.tetherRest ?? new Float32Array(0)
    const { threads, colours } = coloured([
      { pairs: sewing, rest: new Float32Array(sewCount), alphaOf: () => CLASS.SEW },
      { pairs: tethers, rest: tetherRest, alphaOf: () => CLASS.TETHER },
      { pairs: d.edges, rest: d.rest, alphaOf: e => (d.edgeRib[e] ? CLASS.RIB : CLASS.EDGE) },
      { pairs: d.bends, rest: d.bendRest, alphaOf: e => (d.bendHem[e] ? CLASS.HEM : CLASS.BEND) }
    ])
    // (Each one's kind was written as a float; the shader reads it as a whole number.)
    const f = new Float32Array(threads.buffer), u = new Uint32Array(threads.buffer)
    for (let k = 3; k < u.length; k += 4) u[k] = f[k]
    this.threads = u
    // Which colours are the seams' (the first list's), which the tethers' (the second's), and which the threads'
    // and bends'.
    this.sewColours = []
    this.tetherColours = []
    this.solveColours = []
    let total = 0
    colours.forEach(([, count], c) => { (total < sewCount ? this.sewColours : total < sewCount + tetherRest.length ? this.tetherColours : this.solveColours).push(c); total += count })
    this.colours = colours
    const ranges = new Uint32Array(64 * Math.max(1, colours.length))
    colours.forEach(([offset, count], c) => { ranges[64 * c] = offset; ranges[64 * c + 1] = count })
    this.ranges = device.createBuffer({ size: ranges.byteLength, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST })
    device.queue.writeBuffer(this.ranges, 0, ranges)
    this.colourGroup = device.createBindGroup({ layout: this.gpu.colourLayout, entries: [{ binding: 0, resource: { buffer: this.ranges, size: 8 } }] })
    this.lastX = null
  }

  buildFields() {
    const d = this.drape
    for (const t of [this.skin, this.layer]) if (t && t !== this.gpu.emptyField) { t.dist.destroy(); t.norm.destroy() }
    this.skin = d.field?.distance ? this.gpu.fieldTextures(d.field) : this.gpu.emptyField
    this.layer = d.field?.layers?.distance ? this.gpu.fieldTextures(d.field.layers) : this.gpu.emptyField
  }

  // Everything else the shader reads, packed in a float blob (F) and a whole-number blob (U), with where each
  // part starts in the frame's words.
  buildData() {
    const d = this.drape, n = this.n
    const F = [], U = Array.from(this.threads)
    const wu = this.wu, wf = this.wf
    const put = (list, values) => { const at = list.length; for (const v of values) list.push(v); return at }
    wu[W.oThreads] = 0
    wu[W.oW] = put(F, d.w)
    // Per point: its arm, its leg, on a tucked piece, on the waistband.
    const map = d.map
    const flags = new Uint32Array(n)
    const sides = (own, shift) => {
      for (let i = 0; i < own.length; i++) if (own[i]) flags[map ? map[i] : i] |= (own[i] > 0 ? 1 : 2) << shift
    }
    sides(d.armSide, 0)
    sides(d.legSide, 2)
    if (d.tuck?.press) for (let i = 0; i < d.tucks.length; i++) if (d.tucks[i]) flags[map ? map[i] : i] |= PF.TUCK
    const sewnAt = new Float32Array(n)
    if (d.ring) {
      const points = map ? d.ring.order.map(i => map[i]) : d.ring.order
      for (const j of points) { flags[j] |= PF.RING; sewnAt[j] = d.ring.sewnAt?.get(j) ?? 0 }
    }
    wu[W.oFlags] = put(U, flags)
    wf[W.oSewnAt] = 0
    wu[W.oSewnAt] = put(F, sewnAt)
    const start = d.neighbourStart?.length >= n + 1 ? d.neighbourStart.subarray(0, n + 1) : new Int32Array(n + 1)
    wu[W.oNbStart] = put(U, start)
    wu[W.oNb] = put(U, d.neighbours?.length ? d.neighbours : [0])
    // Bands held on their edges.
    const attachOf = new Uint32Array(n).fill(0xffffffff)
    const src = [], af = []
    if (d.attach) {
      const { points, from, to, u, offset, direction } = d.attach
      for (let k = 0; k < points.length; k++) {
        attachOf[points[k]] = k
        src.push(from[k], to[k])
        af.push(u[k], offset[k], direction[3 * k], direction[3 * k + 1], direction[3 * k + 2])
      }
    }
    wu[W.oAttachOf] = put(U, attachOf)
    wu[W.oAttachSrc] = put(U, src.length ? src : [0, 0])
    wu[W.oAttachF] = put(F, af.length ? af : [0])
    // The torso's tables: the envelope's, and the tuck's (put once when they're the same).
    const table = (t, at) => {
      if (!t) { wf[at] = 0; wu[at + 1] = 1; wu[at + 2] = 1; wu[at + 3] = put(F, [0]); wu[at + 4] = put(F, [0]); return }
      wf[at] = t.floor; wu[at + 1] = t.rows; wu[at + 2] = t.sectors
      wu[at + 3] = put(F, t.centre); wu[at + 4] = put(F, t.hull)
    }
    table(d.envelope?.table, W.t1)
    if (d.tuck?.table && d.tuck.table === d.envelope?.table) for (let k = 0; k < 5; k++) wu[W.t2 + k] = wu[W.t1 + k]
    else table(d.tuck?.table, W.t2)
    // The feet: each one's numbers, and its outlines by height ([x, z] points in F; each row's start and count
    // in a table in U).
    const feetF = new Array(24).fill(0), rowsOf = [[], []]
    if (d.feet) {
      ;["L", "R"].forEach((side, k) => {
        const foot = d.feet[side]
        if (!foot) return
        const low = d.snug ? ((foot.snugAt ??= new Map()).get(d.snug) ?? foot.snugAt.set(d.snug, foot.lowest(d.snug)).get(d.snug)) : -1e9
        const values = [foot.top, foot.floor, foot.step, foot.hulls.length, low, foot.ankle ? 1 : 0,
          foot.ankle?.[0] ?? 0, foot.ankle?.[2] ?? 0, foot.forward?.[0] ?? 0, foot.forward?.[1] ?? 0, foot.reach ?? 0, 0]
        for (let j = 0; j < 12; j++) feetF[12 * k + j] = values[j]
        for (const hull of foot.hulls) {
          if (!hull) { rowsOf[k].push(0, 0); continue }
          rowsOf[k].push(F.length, hull.length)
          for (const [x, z] of hull) F.push(x, z)
        }
      })
    }
    wu[W.oFeet] = put(F, feetF)
    {
      const head = U.length
      U.push(head + 2, head + 2 + rowsOf[0].length, ...rowsOf[0], ...rowsOf[1])
      wu[W.oFeetU] = head
    }
    // The arms: each one's line (4 points), its lengths, where its cuff stops and the way back up it.
    const arms = new Array(48).fill(0)
    if (d.arms) {
      ;["L", "R"].forEach((side, k) => {
        const arm = d.arms[side]
        if (!arm) return
        const limit = arm.lengths[2] + CUFF_PAST_WRIST
        const { direction } = arm.along(limit)
        const values = [...arm.chain.flat(), ...arm.lengths, limit, limit - CUFF_EASE, ...direction]
        for (let j = 0; j < values.length; j++) arms[24 * k + j] = values[j]
      })
    }
    wu[W.oArms] = put(F, arms)
    // The hands (and forearms) pants stay off.
    const hands = new Array(80).fill(0)
    let mask = 0
    if (d.hands) {
      Object.values(d.hands).slice(0, 4).forEach((hand, k) => {
        if (!hand) return
        mask |= 1 << k
        const at = key => put(F, hand[key])
        const values = [...hand.wrist, ...hand.along, ...hand.inward, ...hand.across, hand.length, hand.start ?? 0, hand.pad ?? 0, hand.inner.length,
          at("inner"), at("outer"), at("lo"), at("hi")]
        for (let j = 0; j < values.length; j++) hands[20 * k + j] = values[j]
      })
    }
    wu[W.oHands] = put(F, hands)
    wu[W.handsMask] = mask
    const ells = (d.field?.ellipsoids ?? []).slice(0, MAX_ELLIPSOIDS)
    wu[W.ells] = ells.length
    wu[W.oEll] = put(F, ells.length ? ells.flatMap(({ centre, radii }) => [...centre, ...radii]) : [0])
    // The fields' grids.
    const grid = (field, at) => {
      if (!field?.distance) { wf[at] = 0; wf[at + 1] = 0; wf[at + 2] = 0; wf[at + 3] = 1; wu[at + 4] = 2; wu[at + 5] = 2; wu[at + 6] = 2; wf[at + 7] = 1; return }
      wf[at] = field.min[0]; wf[at + 1] = field.min[1]; wf[at + 2] = field.min[2]; wf[at + 3] = field.cell
      wu[at + 4] = field.dims[0]; wu[at + 5] = field.dims[1]; wu[at + 6] = field.dims[2]; wf[at + 7] = field.band
    }
    grid(d.field, W.fieldMin)
    grid(d.field?.layers, W.layerMin)
    const device = this.device
    this.F?.destroy(); this.U?.destroy()
    const floats = Float32Array.from(F.length ? F : [0]), ints = Uint32Array.from(U.length ? U : [0], v => v >>> 0)
    this.F = device.createBuffer({ size: Math.ceil(floats.byteLength / 16) * 16, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST })
    device.queue.writeBuffer(this.F, 0, floats)
    this.U = device.createBuffer({ size: Math.ceil(ints.byteLength / 16) * 16, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST })
    device.queue.writeBuffer(this.U, 0, ints)
    this.group = device.createBindGroup({ layout: this.gpu.layout, entries: [
      { binding: 0, resource: { buffer: this.uniform } },
      { binding: 1, resource: { buffer: this.state } },
      { binding: 2, resource: { buffer: this.F } },
      { binding: 3, resource: { buffer: this.U } },
      { binding: 4, resource: { buffer: this.atomics } },
      { binding: 5, resource: this.skin.dist.createView() }, { binding: 6, resource: this.skin.norm.createView() },
      { binding: 7, resource: this.layer.dist.createView() }, { binding: 8, resource: this.layer.norm.createView() }
    ] })
  }

  // The CPU's points and speeds onto the card.
  upload() {
    const d = this.drape, n = this.n
    const data = new Float32Array(8 * n)
    for (let i = 0; i < n; i++) {
      data[4 * i] = d.x[3 * i]; data[4 * i + 1] = d.x[3 * i + 1]; data[4 * i + 2] = d.x[3 * i + 2]
      data[4 * (n + i)] = d.v[3 * i]; data[4 * (n + i) + 1] = d.v[3 * i + 1]; data[4 * (n + i) + 2] = d.v[3 * i + 2]
    }
    this.device.queue.writeBuffer(this.state, 0, data)
    this.lastX = Float32Array.from(d.x)
  }

  // One frame (Drape#step's options), sent to the card; its points come back with pull.
  frame({ gravity = true, sew = !this.drape.sewn, still = false } = {}) {
    const t = performance.now()
    const d = this.drape
    this.refresh()
    const h = FRAME / SUBSTEPS
    const params = d.params
    const wu = this.wu, wf = this.wf
    wu[W.n] = this.n
    let flags = 0
    if (still) flags |= FLAG.STILL
    if (d.sewn) flags |= FLAG.SEWN
    if (d.field?.layers?.distance) flags |= FLAG.LAYERS
    if (d.envelope) flags |= FLAG.ENVELOPE
    if (d.tuck?.press) flags |= FLAG.TUCK_PRESS
    if (d.tuck?.press && d.map) flags |= FLAG.QUIET
    if (d.feet) flags |= FLAG.FEET
    if (d.snug) flags |= FLAG.SNUG
    if (d.arms) flags |= FLAG.ARMS
    if (d.hands && wu[W.handsMask]) flags |= FLAG.HANDS
    if (d.floor !== null && d.floor !== undefined) flags |= FLAG.FLOOR
    if (d.ring) flags |= FLAG.RING
    wu[W.flags] = flags
    wf[W.h] = h
    wf[W.fall] = GRAVITY * h * (gravity === true ? 1 : Number(gravity) || 0)
    wf[W.drag] = Math.exp(-params.drag * (gravity === true ? 1 : 4) * h)
    wf[W.thick] = params.thickness
    wf[W.keep] = d.friction
    wf[W.radius] = d.selfRadius > 0 ? d.selfRadius : 1
    wf[W.squeeze] = SQUEEZE
    wf[W.cEdge] = params.stretch / (h * h)
    wf[W.cRib] = CLOTHS.rib.stretch / (h * h)
    wf[W.cBend] = params.bend / (h * h)
    wf[W.cHem] = (params.bend / (h * h)) * HEM_BEND
    wf[W.floorY] = d.floor ?? -1e9
    wf[W.envTop] = d.envelope?.top ?? 0
    wf[W.envBottom] = d.envelope?.bottom ?? -1e9
    wf[W.tuckTop] = d.tuck?.top ?? 0
    wf[W.tuckRaise] = d.tuck?.raise ?? 0
    wf[W.tuckInside] = d.tuck?.inside ?? 0
    wf[W.sewStep] = 2 * MAX_SEW_STEP
    const device = this.device
    device.queue.writeBuffer(this.uniform, 0, this.words)
    const groups = Math.ceil(this.n / GROUP)
    const self = d.sewn && d.selfRadius > 0
    const encoder = device.createCommandEncoder()
    const pass = encoder.beginComputePass()
    const p = this.gpu.pipelines
    pass.setBindGroup(0, this.group)
    pass.setBindGroup(1, this.colourGroup, [0])
    const colours = list => {
      for (const c of list) {
        const count = this.colours[c][1]
        if (!count) continue
        pass.setBindGroup(1, this.colourGroup, [256 * c])
        pass.dispatchWorkgroups(Math.ceil(count / GROUP))
      }
    }
    for (let s = 0; s < SUBSTEPS; s++) {
      pass.setPipeline(p.predict); pass.dispatchWorkgroups(groups)
      pass.setPipeline(p.solve)
      if (sew) colours(this.sewColours)
      // (Tethers once it's sewn, as Drape#stepCpu.)
      if (d.sewn && !sew) colours(this.tetherColours)
      colours(this.solveColours)
      if (self && s % 2 === 1) {
        pass.setPipeline(p.hashClear); pass.dispatchWorkgroups(HASH / GROUP)
        pass.setPipeline(p.hashInsert); pass.dispatchWorkgroups(groups)
        pass.setPipeline(p.selfPush); pass.dispatchWorkgroups(groups)
        pass.setPipeline(p.selfApply); pass.dispatchWorkgroups(groups)
      }
      pass.setPipeline(p.collide); pass.dispatchWorkgroups(groups)
      pass.setPipeline(p.collideHold); pass.dispatchWorkgroups(groups)
      pass.setPipeline(p.finish); pass.dispatchWorkgroups(groups)
    }
    pass.end()
    encoder.copyBufferToBuffer(this.state, 0, this.staging, 0, 16 * this.n)
    device.pushErrorScope("validation")
    device.queue.submit([encoder.finish()])
    this.errors = device.popErrorScope()
    this.encodeMs = performance.now() - t
  }

  // The frame's points read back into the drape.
  async pull() {
    const error = await this.errors
    if (error) throw new Error(error.message)
    await this.staging.mapAsync(GPUMapMode.READ)
    const four = new Float32Array(this.staging.getMappedRange())
    const x = this.drape.x, n = this.n
    for (let i = 0; i < n; i++) { x[3 * i] = four[4 * i]; x[3 * i + 1] = four[4 * i + 1]; x[3 * i + 2] = four[4 * i + 2] }
    this.staging.unmap()
    this.lastX.set(x)
  }

  // The points' speeds read back too (for the CPU to go on from).
  async pullSpeed() {
    const n = this.n
    const staging = this.device.createBuffer({ size: 16 * n, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ })
    const encoder = this.device.createCommandEncoder()
    encoder.copyBufferToBuffer(this.state, 16 * n, staging, 0, 16 * n)
    this.device.queue.submit([encoder.finish()])
    await staging.mapAsync(GPUMapMode.READ)
    const four = new Float32Array(staging.getMappedRange())
    const v = this.drape.v
    for (let i = 0; i < n; i++) { v[3 * i] = four[4 * i]; v[3 * i + 1] = four[4 * i + 1]; v[3 * i + 2] = four[4 * i + 2] }
    staging.unmap()
    staging.destroy()
  }

  destroy() {
    for (const b of [this.state, this.atomics, this.staging, this.ranges, this.F, this.U, this.uniform]) b?.destroy()
    for (const t of [this.skin, this.layer]) if (t && t !== this.gpu.emptyField) { t.dist.destroy(); t.norm.destroy() }
  }
}

function sameArray(a, b) {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
  return true
}

// A copy of a drape to step without touching the one shown: its moving arrays copied, the rest shared.
function copyOf(drape) {
  const copy = Object.assign(Object.create(Object.getPrototypeOf(drape)), drape)
  copy.x = Float32Array.from(drape.x); copy.p = Float32Array.from(drape.p); copy.v = Float32Array.from(drape.v)
  copy.params = { ...drape.params }
  copy.kernel = null
  copy.clear = null
  copy.gpuMirror = null
  copy.gpuTrial = null
  if (drape.ring) copy.ring = { ...drape.ring }
  return copy
}

// Drape#step on the CPU against the GPU's on the same cloth, from where it lies: `frames` frames each, timed,
// and how far apart the two end up (they solve the same rules in a different order, so close, not the same).
// Returns { points, frames, cpu: { msPerFrame }, gpu: { msPerFrame, firstMs, adapter } | { unavailable },
// apart: { rms, most } (m) }.
export async function benchDrape(drape, { frames = 120, gpu = null } = {}) {
  const result = { points: drape.x.length / 3, frames, cpu: {}, gpu: null }
  const cpu = copyOf(drape)
  cpu.noGpu = true
  // (In WebAssembly, as the CPU drapes, where it's there: its own copy of the arrays.)
  if (KERNEL_ON && !drape.noKernel) cpu.kernel = new ClothKernel(cpu)
  let t = performance.now()
  for (let f = 0; f < frames; f++) cpu.stepCpu({ gravity: true, sew: false })
  result.cpu.msPerFrame = (performance.now() - t) / frames
  const own = gpu ?? await GpuDrape.start()
  if (!own) { result.gpu = { unavailable: "no WebGPU here" }; return result }
  const copy = copyOf(drape)
  copy.gpuTrial = { cpu: [], gpu: [], choice: "gpu" }
  try {
    t = performance.now()
    own.step(copy, { gravity: true, sew: false }); await own.sync()
    const firstMs = performance.now() - t
    t = performance.now()
    for (let f = 1; f < frames; f++) { own.step(copy, { gravity: true, sew: false }); await own.sync() }
    if (own.failed) { result.gpu = { unavailable: own.failed }; return result }
    result.gpu = { msPerFrame: (performance.now() - t) / Math.max(1, frames - 1), firstMs, adapter: own.description }
    let sum = 0, most = 0
    for (let i = 0; i < copy.x.length; i += 3) {
      const d = Math.hypot(copy.x[i] - cpu.x[i], copy.x[i + 1] - cpu.x[i + 1], copy.x[i + 2] - cpu.x[i + 2])
      sum += d * d; most = Math.max(most, d)
    }
    result.apart = { rms: Math.sqrt(sum / (copy.x.length / 3)), most }
  } finally {
    own.release(copy)
    if (!gpu) own.stop()
  }
  return result
}
