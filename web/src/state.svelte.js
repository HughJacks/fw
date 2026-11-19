// state.svelte.js — the page's shared state, as Svelte 5 runes (the user, 2026-11-18: "runes for everything because
// the data is dependent"). What the page shows is $state here; components derive the rest ($derived).
//
// status: what the page says (the old bottom bar's left side; its key hints are gone, 2026-11-18).

export const status = $state({ text: "" });
// ui: what the page is in the middle of (capturing: a command's id while the keys page waits for its new keys)
export const ui = $state({ capturing: null, asking: null });   // (asking: the question in the page, {question, yes, answer}: ask.js, Ask.svelte)

/** The view open in #main (App.svelte draws it): {kind: "home" | "pericope" | "keys", props}, a new object for each
 * opening (a new one, even of the same place, is drawn afresh); `instance` the component drawn for it (its leave(),
 * a pericope's editor()). Raw: its props (a whole pericope, as the core sent it) aren't made deeply reactive. */
class Page {
  view = $state.raw(null);
  instance = null;
}
export const page = new Page();
