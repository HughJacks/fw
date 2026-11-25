// live.js — the page's one way of hearing that the store changed (TYPE.md "Live: the rule"): the core pushes the
// store's stamp as it changes (GET /api/live, server-sent events), and everything the page shows from the store
// follows it through `onStore`, never a loop of its own. A hidden tab lets go of its stream (a browser keeps only a
// few connections to one place open) and, shown again, catches up: the stream says where the store is, and a
// change made meanwhile is told then.

let source = null, stamp = null;
const followers = new Set();

function tell() {
  for (const f of [...followers]) {
    if (f.seen === stamp) continue;
    f.seen = stamp;
    if (f.skip) f.skip = false; else f.changed();
  }
}

function connect() {
  if (source || document.hidden) return;
  source = new EventSource("/api/live");
  source.onmessage = (e) => { stamp = JSON.parse(e.data).stamp; tell(); };
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) { source?.close(); source = null; return; }
  connect();
});

/** `changed()` whenever the store changes from now on (and when the stream first speaks, if it hadn't yet: a change
 * between a view's first fetch and then isn't missed). Returns what stops it. With `{ first: false }` that first word
 * is only taken as where the store is. */
export function onStore(changed, { first = true } = {}) {
  connect();
  const f = { changed, seen: stamp, skip: !first && stamp === null };
  followers.add(f);
  return () => followers.delete(f);
}
