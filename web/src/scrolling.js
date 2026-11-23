// scrolling.js — the page scrolled on purpose, as a list's selection moves or one is entered (the user, 2026-11-23:
// "we want our cursor navigate and auto scrolling to feel a bit more intentional and smooth"): smoothly (at once in the
// tests and with reduced motion: motion.js `still`), and with room kept between what's selected and the window's edges
// (PAD), never just to the edge.
import { still } from "./motion.js";

/** Room between what's revealed and the window's edges (the top line, 30px, counted in at the top). */
export const PAD = 56;

/** The page scrolled by `dy`, smoothly (but in still mode). */
export function scrollPage(dy) {
  if (Math.abs(dy) < 1) return;
  scrollBy({ top: dy, behavior: still ? "instant" : "smooth" });
}

/** Element `el` brought into view with PAD of room from the window's edges: nothing done if it's in there already;
 * else scrolled just far enough (up: its top PAD under the window's top; down: its bottom PAD over the bottom). */
export function reveal(el, pad = PAD) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  if (r.top < pad) scrollPage(r.top - pad);
  else if (r.bottom > innerHeight - pad) scrollPage(r.bottom - (innerHeight - pad));
}

/** A list's rows, `first` to `last`, shown whole, the first PAD under the window's top, when they fit with `keep` px
 * more under them (the header below the backlinks, say); longer, they run off the top, `last` (the selected row
 * nearest what follows) kept in view with its room. */
export function showList(first, last, keep = 0) {
  if (!first || !last) return;
  const top = first.getBoundingClientRect().top, bottom = last.getBoundingClientRect().bottom;
  if (bottom - top <= innerHeight - 2 * PAD - keep) scrollPage(top - PAD);
  else reveal(last);
}
