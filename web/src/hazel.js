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
import { snapshot } from "./snapshot.svelte.js";

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

const answer = (call) => {
  if (state !== "ready") return null;
  try { return JSON.parse(call(snapshot.json)); } catch (e) { return { kind: "error", message: String(e), errors: [] }; }
};

/** Source `source` evaluated (the answer above), or null until the engine's loaded; an empty source: {kind: "empty"}.
 * `self`: the expression block's id, where it sits (above and below are its peers there). */
export function run(source, self = "") {
  if (!(source || "").trim()) return state === "ready" ? { kind: "empty", errors: [] } : null;
  return answer((snap) => globalThis.hazelRun(source, snap, self || ""));
}
