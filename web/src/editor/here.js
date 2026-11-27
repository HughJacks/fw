// here.js — where you are among the editors: the one you're in (each editor's own state says so, hereKey), the quote
// views found from their DOM, the words a document holds, and what's focused in a pericope's editors (the tabs' path).
import { PluginKey, NodeSelection } from "prosemirror-state";
import { BlockSelection } from "./blocks.js";

// `current`: it's the editor you're in; `quiet`: nothing drawn as where you are yet. Set by a transaction's meta, so
// what's drawn changes with the state, never by an empty transaction dispatched to redraw.
export const hereKey = new PluginKey("fw-here");

/** A quote's (or an expression's) DOM -> its view, to go into it from the keys. */
export const views = new WeakMap();

// One editor at a time is the one you're in, and only its selection is drawn. You stay in it while a menu or a question
// of the page has the focus, or the window loses it; you leave it for another editor, or anything else on the page.
// `current` only remembers which to tell it isn't, when another is.
let current = null;
export const currentEditor = () => current;
/** Editor `ed` (or none) the one you're in: its state says so, and the one you were in's says it isn't. */
export function setCurrent(ed) {
  if (current === ed) return;
  const was = current;
  current = ed;
  if (was && !was.gone) was.view.dispatch(was.view.state.tr.setMeta(hereKey, { current: false }).setMeta("addToHistory", false));
  if (ed && !ed.gone) ed.view.dispatch(ed.view.state.tr.setMeta(hereKey, { current: true }).setMeta("addToHistory", false));
}
/** Editor `ed` gone: no longer the one you're in. */
export function forget(ed) { if (current === ed) current = null; }

/** `sel` (where an arrow would go, Selection.findFrom's) a quote that can be gone into: into it, at its start going
 * down (`dir` 1), its end going up, and true; else false (a picture, a stand-in: selected whole as before). */
export function enterQuote(view, sel, dir) {
  if (!(sel instanceof NodeSelection) || !["quote", "expr"].includes(sel.node.type.name)) return false;
  const qv = views.get(view.nodeDOM(sel.from));
  return !!(qv && qv.inner && qv.enter(dir < 0 ? "end" : "start"));
}

/** The paraphrase the selection is in, innermost first, or selected whole (one block): its `para`, or null. */
export function paraAt(state) {
  const sel = state.selection;
  if (sel instanceof BlockSelection) { const b = sel.blocks(); return b.length === 1 ? b[0].node.attrs.para || null : null; }
  if (sel instanceof NodeSelection) return sel.node.attrs.para || null;
  for (let d = sel.$from.depth; d > 0; d--) if (sel.$from.node(d).attrs.para) return sel.$from.node(d).attrs.para;
  return null;
}

/** A word: a run without spaces with something in it besides punctuation (fw.block.is_word: one rule wherever fw counts). */
const PUNCT = new Set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~–—…“”‘’«»•·");
export const isWord = (w) => [...w].some((c) => !PUNCT.has(c));
/** How many words a document holds (the header's count). */
export const wordsIn = (doc) => doc.textBetween(0, doc.content.size, " ", " ").split(/\s+/).filter((w) => w && isWord(w)).length;

/** Editor `e` and the editors of the quotes in it, at any depth, outermost first. */
export const editorsIn = (e) => [e, ...[...e.kids].flatMap(editorsIn)];

/** Where you are in `root`'s editors, from their states (the tabs' path): {editor, chosen, from, to}, the editor you're
 * in and what's drawn there: blocks selected whole (`chosen`, the first and last at `from`, `to`), or the block of text
 * the cursor's in (`from`); `from` null: in it, nothing of it drawn. Null: nowhere in it, or quiet. Reactive. */
export function focusOf(root) {
  if (!root || root.gone) return null;
  for (const e of editorsIn(root)) {
    const st = e.pm, h = st && hereKey.getState(st);
    if (!h?.current || h.quiet) continue;
    const sel = st.selection;
    if (sel instanceof NodeSelection) return { editor: e, chosen: true, from: sel.from, to: sel.from };
    if (sel instanceof BlockSelection) { const b = sel.blocks(); if (b.length) return { editor: e, chosen: true, from: b[0].pos, to: b.at(-1).pos }; }
    const { $from } = sel;
    for (let d = $from.depth; d > 0; d--) if ($from.node(d).type.name === "text_block") return { editor: e, chosen: false, from: $from.before(d), to: $from.before(d) };
    return { editor: e, chosen: false, from: null, to: null };
  }
  return null;
}
