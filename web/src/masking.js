// masking.js — masking mode started (Masking.svelte draws it and takes its keys): the quote's draft, lines and mask
// asked of the core, then the panel mounted in the quote's own box.
import { mount, unmount } from "svelte";
import { api } from "./api.js";
import Masking from "./Masking.svelte";

/** Masking quote `qid`, drawn in `box` (the quote's own box: what it shows is hidden meanwhile). `finish(draft,
 * mask)` saves it; `cancel()` leaves it as it was. */
export async function startMasking(box, qid, { finish, cancel }) {
  const r = await api(`/api/masking?quote=${encodeURIComponent(qid)}`);
  if (!r.ok) return false;
  let view = null;
  const close = () => { if (view) { const v = view; view = null; unmount(v); } };
  view = mount(Masking, { target: box, props: { box, draft: r.body.draft, lines: r.body.lines, mask: r.body.mask, finish, cancel, close } });
  return true;
}
