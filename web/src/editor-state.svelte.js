// editor-state.svelte.js — what an editor (editor.js BlockEditor) holds that the page derives from, as Svelte 5 runes
// (the audit of 2026-11-19: the editor's state inside the runes, not a counter bumped by hand): its ProseMirror state, set
// as each transaction is applied; what it says; its words when the store's count was taken (the header counts what's
// gained or lost since); the draft as last saved (dirty() compares); the editors of the quotes in it. A base class of
// its own, since a .svelte.js module can't hold ProseMirror's $-named positions.
import { SvelteSet } from "svelte/reactivity";

export class EditorRunes {
  pm = $state.raw(null);
  message = $state("");
  since = $state(0);
  saved = $state.raw(null);
  kids = new SvelteSet();
}
