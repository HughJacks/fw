// snapshot.svelte.js — the store as the expression engine reads it (hazel.js: hazelRun's snapshot), built on the page:
// every pericope as the core last sent it (GET /api/snapshot, followed as the store changes), with the open pericope's
// own over it, live from its editor's document, so a result follows every key (the user's instant rule). The page
// never reads the store itself.
import { untrack } from "svelte";
import { api } from "../lib/api.js";
import { snapNode, liveFacts } from "../editor/draft.js";
import { onStore } from "../lib/live.js";

/** This moment as the store writes dates: ISO 8601, to the second, with this place's offset. */
function isoNow() {
  const d = new Date(), pad = (n) => String(Math.abs(n)).padStart(2, "0"), off = -d.getTimezoneOffset();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    + `${off < 0 ? "-" : "+"}${pad(Math.trunc(off / 60))}:${pad(off % 60)}`;
}

class Snapshot {
  store = $state.raw(null);   // {now, facts: {id: a block's own facts}, pericopes: [{id, title, kinds, body}]}: the core's
  minute = $state(isoNow());  // (`now` in an expression: moved on each minute, so what reads it follows)
  live = $state.raw(null);    // {id, body}: the open pericope, from its editor's document
  /** What the engine holds (a key cost ~53 ms when the engine read the whole store again): the store as last
   * read whole (`full`), then patches to it as it changes, just the blocks that did (`deltas`, in order), then the open
   * pericope as it's written now (`patch`: hazelPatch, a few ms a key). */
  full = $state.raw("");
  deltas = $state.raw([]);
  patch = $derived.by(() => {
    const live = this.live;
    if (!live) return "";
    const ps = this.store?.pericopes || [], core = this.store?.facts || {};
    const was = ps.find((p) => p.id === live.id);
    const own = was ? { ...was, body: live.body } : { id: live.id, title: "", kinds: [], body: live.body };
    const all = liveFacts(core, live, this.minute), facts = {};
    for (const k of Object.keys(all)) if (!(k in core)) facts[k] = all[k];   // (only the blocks just written: the rest is the base's)
    return JSON.stringify({ pericopes: [own], facts });
  });
  /** Any part changing: what redraws on a change reads (onSnapshot). */
  json = $derived([this.full, this.deltas, this.patch]);
}
export const snapshot = new Snapshot();

let following = null;
/** The core's part fetched, then followed (once, from the first expression drawn). */
export function follow() {
  if (following) return;
  const load = async () => {   // (everything, read whole)
    const r = await api("/api/snapshot");
    if (!r.ok) return;
    snapshot.store = r.body;
    snapshot.full = JSON.stringify({ ...r.body, now: snapshot.minute });
    snapshot.deltas = [];
  };
  const some = async (ids) => {   // (just what changed: merged into the store, a patch for the engine)
    if (!ids.length) return;
    const r = await api(`/api/snapshot?ids=${encodeURIComponent(ids.join(","))}`);
    if (!r.ok) return load();
    const gone = new Set(r.body.gone), mine = new Map(r.body.pericopes.map((p) => [p.id, p]));
    const ps = (snapshot.store?.pericopes || []).filter((p) => !gone.has(p.id)).map((p) => mine.get(p.id) ?? p);
    for (const p of r.body.pericopes) if (!ps.some((q) => q.id === p.id)) ps.push(p);
    const facts = { ...(snapshot.store?.facts || {}), ...r.body.facts };
    for (const id of gone) delete facts[id];
    snapshot.store = { ...snapshot.store, pericopes: ps, facts };
    snapshot.deltas = [...snapshot.deltas, JSON.stringify({ ...r.body, changed: ids })];
  };
  let queue = Promise.resolve();   // (one at a time, in order: an older answer never lands after a newer)
  following = queue = load();
  onStore((ids) => {   // (the first word too: a change between the load and it isn't missed)
    queue = queue.then(() => (!ids || ids.length > 150 || snapshot.deltas.length > 200 ? load() : some(ids)));
  });
  setInterval(() => {   // (the minute moved on: a patch, not the store read again)
    snapshot.minute = isoNow();
    snapshot.deltas = [...snapshot.deltas, JSON.stringify({ now: snapshot.minute, changed: ["now"] })];
  }, 60000);
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
