// results.js — a search's selection kept across the search service's answer (the user, 2026-11-18: suggestions shouldn't "just
// pop in"). The rows themselves are drawn by Home.svelte and SearchBox.svelte: a placeholder while the search service's answer
// is on its way, then rows already there move (Svelte's flip) and new ones ease in.


/** The index in `rows` of the row keyed `key` (the one selected before a redraw), else `fallback`. */
export const keep = (rows, key, fallback) => {
  const n = key == null ? -1 : rows.findIndex((r) => r.key === key);
  return n >= 0 ? n : fallback;
};

/** How long rows take to move, ms: none for whoever asks for reduced motion. */
export const MOVE = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 240;
