// masking.js — masking mode started (Masking.svelte draws it and takes its keys): the quote's draft, lines and mask
// asked of the core, then the panel mounted in the quote's own box.
import { mount, unmount } from "svelte";
import { api } from "../lib/api.js";
import Masking from "../ui/Masking.svelte";
import { ui } from "../state/state.svelte.js";

/** Masking quote `qid`, drawn in `box` (the quote's own box: what it shows is hidden meanwhile). `finish(draft,
 * mask)` saves it; `cancel()` leaves it as it was. */
const open = new Map();   // box -> close(): the panels open (each counted in ui.menus while it is)
export async function startMasking(box, qid, { finish, cancel }) {
  const r = await api(`/api/masking?quote=${encodeURIComponent(qid)}`);
  if (!r.ok) return false;
  let view = null;
  const close = () => { if (view) { const v = view; view = null; open.delete(box); unmount(v); ui.menus--; } };
  open.set(box, close);
  view = mount(Masking, { target: box, props: { box, draft: r.body.draft, lines: r.body.lines, mask: r.body.mask, finish, cancel, close } });
  ui.menus++;   // (open over the text: state.svelte.js)
  return true;
}

/** Any masking panel inside `dom` taken down (its quote's box going away: QuoteView.destroy), so none is left counted. */
export function stopMasking(dom) {
  for (const [box, close] of [...open]) if (dom.contains(box)) close();
}
