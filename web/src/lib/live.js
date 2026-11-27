// live.js — the page's one way of hearing that the store changed (TYPE.md "Live: the rule"): the core pushes the
// store's stamp as it changes (GET /api/live, server-sent events), and everything the page shows from the store
// follows it through `onStore`, never a loop of its own. A hidden tab lets go of its stream (a browser keeps only a
// few connections to one place open) and, shown again, catches up: the stream says where the store is, and a
// change made meanwhile is told then.

let source = null, stamp = null, changed = null;   // (changed: the blocks the last word said changed; null, not known)
const followers = new Set();

function tell() {
  for (const f of [...followers]) {
    if (f.seen === stamp) continue;
    const first = f.seen === null || f.seen === undefined;
    f.seen = stamp;
    if (f.skip) f.skip = false; else f.changed(first ? null : changed);   // (a first word: everything, as not known)
  }
}

function connect() {
  if (source || document.hidden) return;
  source = new EventSource("/api/live");
  source.onmessage = (e) => { const m = JSON.parse(e.data); stamp = m.stamp; changed = m.changed ?? null; tell(); };
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) { source?.close(); source = null; return; }
  connect();
});

/** `changed(ids)` whenever the store changes from now on (ids: the blocks that changed, or null when that's not
 * known: read everything) (and when the stream first speaks, if it hadn't yet: a change
 * between a view's first fetch and then isn't missed). Returns what stops it. With `{ first: false }` that first word
 * is only taken as where the store is. */
export function onStore(changed, { first = true } = {}) {
  connect();
  const f = { changed, seen: stamp, skip: !first && stamp === null };
  followers.add(f);
  return () => followers.delete(f);
}
