import { untrack } from "svelte";
// state.svelte.js — the page's shared state, as Svelte 5 runes ("runes for everything because
// the data is dependent"). What the page shows is $state here; components derive the rest ($derived).
//
// status: what the page says (the old bottom bar's left side; its key hints are gone).

// (`from`: whose the line is, the last to say something: "page" (`text`, said by the page: home, the keys page) or
// "pericope" (what the pericope open says, derived from its editors' messages: Pericope.svelte's said()); App.svelte
// draws it)
export const status = $state({ text: "", from: "page" });
/** The page says `text` (the line is the page's until the pericope says something). */
export function say(text) { status.text = text; status.from = "page"; }
// ui: what the page is in the middle of (capturing: a command's id while the keys page waits for its new keys; menus:
// how many menus or masking panels are open over the text, so nothing asks the page's DOM whether one is)
export const ui = $state({ capturing: null, asking: null, menus: 0 });   // (asking: the question in the page, {question, yes, answer}: ask.js, Ask.svelte)
/** A menu open (in an $effect: closed when it ends). */
export function opened() {
  untrack(() => ui.menus++);
  return () => untrack(() => ui.menus--);
}

/** Where you are, one page: App.svelte
 * draws everything from it, nothing's made again to move. `view`: "home" (the waiting pericope, the search and the
 * list below it), "pericope" (one of the store's, open), "keys" (the keys page) or "kinds" (the kinds view); `opening`: what the one
 * pericope on the page shows ({id, at, first, flash, home}, a new object each time something's opened; null on the keys
 * page; Pericope.svelte); `written`: home's waiting pericope typed in (the rest of home gone, the page just it). main.js
 * sets it from the address (the routing), after the pericope open before has saved. Raw: `opening` carries a whole
 * pericope as the core sent it, not made deeply reactive. */
class Here {
  view = $state(null);
  opening = $state.raw(null);
  written = $state(false);
}
export const here = new Here();
