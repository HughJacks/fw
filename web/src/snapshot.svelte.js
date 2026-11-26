// snapshot.svelte.js — the store as the expression engine reads it (hazel.js: hazelRun's snapshot), built on the page:
// every pericope as the core last sent it (GET /api/snapshot, followed as the store changes), with the open pericope's
// own over it, live from its editor's document, so a result follows every key (the user's instant rule). The page
// never reads the store itself.
import { untrack } from "svelte";
import { api } from "./api.js";
import { snapNode, liveFacts } from "./draft.js";
import { onStore } from "./live.js";

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
  /** The snapshot as the engine takes it: a JSON string (one per change, so the engine parses it once). */
  json = $derived.by(() => {
    const ps = this.store?.pericopes || [];
    const live = this.live, rest = { now: this.minute, facts: liveFacts(this.store?.facts || {}, live, this.minute) };
    if (!live) return JSON.stringify({ ...rest, pericopes: ps });
    const at = ps.findIndex((p) => p.id === live.id);
    const own = at >= 0 ? { ...ps[at], body: live.body } : { id: live.id, title: "", kinds: [], body: live.body };
    return JSON.stringify({ ...rest, pericopes: at >= 0 ? ps.with(at, own) : [...ps, own] });
  });
}
export const snapshot = new Snapshot();

let following = null;
/** The core's part fetched, then followed (once, from the first expression drawn). */
export function follow() {
  if (following) return;
  const load = async () => {
    const r = await api("/api/snapshot");
    if (r.ok) snapshot.store = r.body;
  };
  following = load();
  setInterval(() => { snapshot.minute = isoNow(); }, 60000);
  onStore(load);   // (the first word too: a change between the load and it isn't missed)
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
