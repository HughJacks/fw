// snapshot.svelte.js — the store as the expression engine reads it (hazel.js: hazelRun's snapshot), built on the page:
// every pericope as the core last sent it (GET /api/snapshot, followed as the store changes), with the open pericope's
// own over it, live from its editor's document, so a result follows every key (the user's instant rule). The page
// never reads the store itself.
import { untrack } from "svelte";
import { api } from "./api.js";
import { snapNode } from "./draft.js";

const FOLLOW = 1000;   // ms between asking whether the store has changed (as Pericope.svelte follows it)

class Snapshot {
  store = $state.raw(null);   // {pericopes: [{id, title, kinds, body}]}: the core's
  live = $state.raw(null);    // {id, body}: the open pericope, from its editor's document
  /** The snapshot as the engine takes it: a JSON string (one per change, so the engine parses it once). */
  json = $derived.by(() => {
    const ps = this.store?.pericopes || [];
    const live = this.live;
    if (!live) return JSON.stringify({ pericopes: ps });
    const at = ps.findIndex((p) => p.id === live.id);
    const own = at >= 0 ? { ...ps[at], body: live.body } : { id: live.id, title: "", kinds: [], body: live.body };
    return JSON.stringify({ pericopes: at >= 0 ? ps.with(at, own) : [...ps, own] });
  });
}
export const snapshot = new Snapshot();

let following = null;
/** The core's part fetched, then followed (once, from the first expression drawn). */
export function follow() {
  if (following) return;
  let stamp = null;
  const load = async () => {
    const r = await api("/api/snapshot");
    if (r.ok) snapshot.store = r.body;
  };
  following = load();
  setInterval(async () => {
    const r = await api("/api/stamp");
    if (!r.ok) return;
    if (stamp !== null && r.body.stamp !== stamp) await load();
    stamp = r.body.stamp;
  }, FOLLOW);
}

/** The open pericope `id`'s document (ProseMirror JSON) as the engine reads it, live. */
export function setLive(id, doc) {
  snapshot.live = id ? { id, body: { ...snapNode(doc), id } } : null;
}

/** `draw` run now and again whenever the snapshot changes (an expression's result, following every key); returns
 * what stops it. */
export function onSnapshot(draw) {
  follow();
  return $effect.root(() => {
    $effect(() => {
      snapshot.json;
      untrack(draw);
    });
  });
}
