// hazel.js — the expression engine: Hazel's parser, types and evaluator, with fw's prelude (Ref, Block, the store's
// built-ins), compiled to JavaScript (the hazel copy's src/fwbridge, fw/build.sh into vendor/, served as dist/hazel.js),
// loaded once after the page opens (so nothing waits on it), then asked synchronously, with the page's snapshot of the
// store (snapshot.svelte.js).
//   run(source)   a source evaluated
// Each returns the bridge's answer, or null while it loads:
//   {kind: "block", type, block}   a Block value as a tree ({t: text|quote|paraphrase|blocks|hole, …})
//   {kind: "value", type, printed} any other value, as Hazel prints it
//   {kind: "function", type}       a function (shown as its type, dim)
//   {kind: "error", message}       it can't be run
// and `errors`: [{term, message}], Hazel's words for each static error (the value comes anyway, around them).
import { snapshot } from "../state/snapshot.svelte.js";
import { TEST } from "../lib/api.js";

let state = "idle";   // idle | loading | ready | failed
const waiting = new Set();

/** Load the engine (once); `then()` runs when it's ready. */
export function load(then = null) {
  if (then) waiting.add(then);
  if (state === "ready") { for (const f of waiting) f(); waiting.clear(); return; }
  if (state !== "idle") return;
  state = "loading";
  const s = document.createElement("script");
  s.src = "/dist/hazel.js";
  s.async = true;
  s.onload = () => { state = typeof globalThis.hazelRun === "function" ? "ready" : "failed"; for (const f of waiting) f(); waiting.clear(); };
  s.onerror = () => { state = "failed"; for (const f of waiting) f(); waiting.clear(); };
  document.head.appendChild(s);
}

/** Whether it's loaded (and how): "idle", "loading", "ready", "failed". */
export const status = () => state;

let held = { full: null, n: 0, patch: null };   // (what the engine holds now: snapshot.svelte.js's parts)
// Results kept: by code, block and viewer,
// each with what it read; dropped when something it read changes (a patch's changed blocks), all of them when the
// store is read again.
const cache = new Map();
const keyOf = (source, self, here) => `${self}\u0000${here}\u0000${source}`;

/** Every block in a patch (its pericopes, their blocks at any depth), each as JSON (its whole subtree: a change inside
 * a block is a change to it), and its facts. */
function patchParts(patch) {
  const out = new Map();
  if (!patch) return out;
  const j = JSON.parse(patch);
  const walk = (n) => { if (!n) return; if (n.id) out.set(n.id, JSON.stringify(n)); for (const k of n.children || []) walk(k); };
  for (const p of j.pericopes || []) { out.set(p.id, JSON.stringify(p)); walk(p.body); }
  for (const [id, f] of Object.entries(j.facts || {})) out.set(`facts:${id}`, JSON.stringify(f));
  return out;
}
/** What changed between two patches: the ids whose part differs, or that one of them hasn't. */
function changedBetween(was, now) {
  const a = patchParts(was), b = patchParts(now), out = new Set();
  for (const [k, v] of a) if (b.get(k) !== v) out.add(k.replace(/^facts:/, ""));
  for (const k of b.keys()) if (!a.has(k)) out.add(k.replace(/^facts:/, ""));
  return out;
}
/** Results that read any of `ids` dropped. */
function forget(ids) {
  if (!ids.size) return;
  for (const [k, e] of cache) if (e.reads.some((x) => ids.has(x))) cache.delete(k);
}
const answer = (call) => {
  if (state !== "ready") return null;
  try {
    const of = (patch) => patch.slice(0, 60).match(/"id":"([^"]+)"/)?.[1] ?? null;   // (whose pericope a patch is)
    // (the store, read again: when it changes, and when the patch is for another pericope or none, so the old one's
    // patch never lingers over the store's)
    if (held.full !== snapshot.full || (held.patch && of(held.patch) !== of(snapshot.patch))) {
      if (TEST) (globalThis.fwRuns ||= []).push(`(read whole: ${held.full !== snapshot.full ? "the store" : "another pericope"})`);
      globalThis.hazelRun("0", snapshot.full, "", "");
      held = { full: snapshot.full, n: 0, patch: null };
      cache.clear();   // (the store read again: nothing kept)
    }
    if (held.n < snapshot.deltas.length) {   // (changes from elsewhere, just their blocks; what read them, forgotten)
      for (; held.n < snapshot.deltas.length; held.n++) {
        const d = snapshot.deltas[held.n], j = JSON.parse(d);
        if (TEST) (globalThis.fwRuns ||= []).push(`(patch: ${(j.changed || []).length} changed: ${(j.changed || []).join(" ")} / pericopes ${(j.pericopes || []).map((p) => p.id).join(" ")} / facts ${Object.keys(j.facts || {}).join(" ")})`);
        globalThis.hazelPatch(d);
        forget(new Set([...(j.changed || []), ...(j.gone || []), ...(j.pericopes || []).map((p) => p.id), ...Object.keys(j.facts || {})]));
      }
      if (held.patch) globalThis.hazelPatch(held.patch);   // (what's written now, over the store's copy of it again)
    }
    if (held.patch !== snapshot.patch) {   // (what's written now; what it changed, forgotten)
      forget(changedBetween(held.patch, snapshot.patch));
      if (snapshot.patch) globalThis.hazelPatch(snapshot.patch);
      held.patch = snapshot.patch;
    }
    return call(null);
  } catch (e) { return { kind: "error", message: String(e), errors: [] }; }
};

/** Source `source` evaluated (the answer above), or null until the engine's loaded; an empty source: {kind: "empty"}.
 * `self`: the expression block's id, where it sits (above and below are its peers there). */
export function run(source, self = "", here = "") {   // (here: the pericope it's viewed from, the page's; TYPE.md)
  if (!(source || "").trim()) return state === "ready" ? { kind: "empty", errors: [] } : null;
  return answer((snap) => {
    const k = keyOf(source, self || "", here || ""), kept = cache.get(k);
    if (kept) return kept.r;   // (nothing it read has changed: the same answer, the same object)
    if (TEST) (globalThis.fwRuns ||= []).push(source);   // (the tests count what was worked out again)
    const r = JSON.parse(globalThis.hazelRun(source, snap, self || "", here || ""));
    cache.set(k, { r, reads: r.reads || [] });
    return r;
  });
}
