// editor.js — one block open for writing: a pericope on the page, or what a quote shows when it's written
// through (edit-through, as the terminal's). Each has its own document, undo, autosave and base, and saves
// into its own block through the core (PUT /api/pericope/<id>: the terminal's commit). A quote that can be
// written through holds an editor of its own (QuoteView); one that can't (masked, locked, a picture, too
// deep) is drawn read only from what the core says it shows.
import * as visits from "./visits.js";
import { EditorState, Plugin, PluginKey, NodeSelection, TextSelection, Selection } from "prosemirror-state";
import { EditorView, Decoration, DecorationSet } from "prosemirror-view";
import { keymap } from "prosemirror-keymap";
import { baseKeymap, chainCommands, splitBlock, liftEmptyBlock } from "prosemirror-commands";
import { BlockSelection, blocksPlugin, selectAround, grow, removeSelected, removeEmpty, joinOut, nestIn, selectBlock, levelKey, atLevel } from "./blocks.js";
import { history, undo, redo } from "prosemirror-history";
import { schema } from "./schema.js";
import { pmDoc, draftOf, freshIds, pmLens, lensOf } from "./draft.js";
import { quoteEl, drawBody, drawValue, insideOf, namesOf, hereOf } from "./views.js";
import { ui } from "./state.svelte.js";
import { EditorRunes } from "./editor-state.svelte.js";
import { stopMasking } from "./masking.js";

// every change saved as it's made (the user, 2026-11-23: "all updates should be instant, so the idea of a write or a save
// is after every single change"): no waiting for the keys to stop; saves go one at a time, each with all that's changed
// by then (save(): one in flight, the next after it), so fast typing is a save about every 90 ms, never a queue
const SAVE_AFTER = 0;
const RETRY = TEST ? 150 : 1000;       // ms: a save the store refused, tried again
export const waiting = new Set();     // the editors with a save scheduled, not yet begun (the tests' "settled")

import { api, TEST } from "./api.js";
import { slashMenu } from "./menu.js";
import { ExprView, toggleCode, exprGuard, valueTree } from "./exprview.js";
import { inlineCode } from "./inlinecode.js";
import { codeBox, setText } from "./codebox.js";
import * as hazel from "./hazel.js";
import { onSnapshot } from "./snapshot.svelte.js";
import { setLive } from "./snapshot.svelte.js";
import { clipboardPlugin } from "./clipboard.js";
import { keyOf, pressed } from "./keys.js";
const TRAVEL = ["back", "forward", "home", "done", "keys"];   // (the keys that only move you elsewhere)
export { api };

/** A transaction giving ids where the document needs them (draft.freshIds), or null. A block split off one
 * that was its own block's text (`own`) is a block of its own. */
function idsTr(state) {
  const found = [];
  state.doc.descendants((n, pos) => { found.push({ type: n.type.name, id: n.attrs.id, pos, node: n }); });
  const fresh = freshIds(found);
  if (!fresh.size) return null;
  const tr = state.tr;
  for (const [n, id] of fresh) {   // (a block split off another isn't its own text, nor marked as a paraphrase: the store's mark stays on the first)
    const keep = found[n].type === "text_block" ? { own: false, para: null } : found[n].type === "container" ? { para: null } : {};
    tr.setNodeMarkup(found[n].pos, null, { ...found[n].node.attrs, id, ...keep });
  }
  return tr.setMeta("addToHistory", false);
}

const markKey = new PluginKey("fw-mark");
// where you are, as each editor's own state (the audit of 2026-11-19: not module variables a plugin reads): `current`,
// it's the editor you're in; `quiet`, nothing drawn as where you are yet. Set by a transaction's meta (hereKey), so
// what's drawn changes with the state, never by an empty transaction dispatched to redraw.
const hereKey = new PluginKey("fw-here");
/** The paraphrase the selection is in, innermost first, or selected whole (one block): its `para`, or null. */
function paraAt(state) {
  const sel = state.selection;
  if (sel instanceof BlockSelection) { const b = sel.blocks(); return b.length === 1 ? b[0].node.attrs.para || null : null; }
  if (sel instanceof NodeSelection) return sel.node.attrs.para || null;
  for (let d = sel.$from.depth; d > 0; d--) if (sel.$from.node(d).attrs.para) return sel.$from.node(d).attrs.para;
  return null;
}

const views = new WeakMap();
/** `sel` (where an arrow would go, Selection.findFrom's) a quote that can be gone into: into it, at its start going
 * down (`dir` 1), its end going up, and true; else false (a picture, a stand-in: selected whole as before). */
function enterQuote(view, sel, dir) {
  if (!(sel instanceof NodeSelection) || !["quote", "expr"].includes(sel.node.type.name)) return false;   // (an expression's value: into it too)
  const qv = views.get(view.nodeDOM(sel.from));
  return !!(qv && qv.inner && qv.enter(dir < 0 ? "end" : "start"));
}   // a quote's DOM -> its QuoteView (to go into it from the keys)

// Where you are (the user, 2026-11-18): one editor at a time is the one you're in, and only its selection is drawn,
// the block its cursor is in (fw-here) or what it has selected whole (fw-chosen); its DOM is marked fw-current (so the
// quotes you're writing through, around it, show: app.css), unless it's quiet (nothing drawn as where you are). Every
// other editor is at rest, whatever selection it last had. You stay in it while a menu or a question of the page has
// the focus, or the window loses it; you leave it for another editor, or for anything else on the page (the title,
// home's search). Each editor's state says whether it's the one (hereKey); `current` only remembers which to tell
// it isn't, when another is.
let current = null;
/** Editor `ed` (or none) the one you're in: its state says so, and the one you were in's says it isn't. */
function setCurrent(ed) {
  if (current === ed) return;
  const was = current;
  current = ed;
  if (was && !was.gone) was.view.dispatch(was.view.state.tr.setMeta(hereKey, { current: false }).setMeta("addToHistory", false));
  if (ed && !ed.gone) ed.view.dispatch(ed.view.state.tr.setMeta(hereKey, { current: true }).setMeta("addToHistory", false));
}
/** How many words a document holds (the header's count). */
/** A word: a run without spaces with something in it besides punctuation (fw_block.is_word: one rule wherever fw counts). */
const PUNCT = new Set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~–—…“”‘’«»•·");
export const isWord = (w) => [...w].some((c) => !PUNCT.has(c));
export const wordsIn = (doc) => doc.textBetween(0, doc.content.size, " ", " ").split(/\s+/).filter((w) => w && isWord(w)).length;

/** Where you are in `root`'s editors, from their states (the tabs' path, Tabs.svelte; nothing read from the page):
 * {editor, chosen, from, to}, the editor you're in and what's drawn there: blocks selected whole (`chosen`, the first
 * and last at positions `from`, `to`), or the block of text the cursor's in (`from`); `from` null: in it, nothing of
 * it drawn (a quote showing one block: the quote). Null: you're nowhere in it, or it's quiet. Reactive: it reads each
 * editor's $state. */
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
/** Editor `e` and the editors of the quotes in it, at any depth, outermost first. */
const editorsIn = (e) => [e, ...[...e.kids].flatMap(editorsIn)];

// --- where you are on a page, kept as you leave it and put back as you come back to it along the trail (⌘[ and ⌘], the
// user, 2026-11-19, later: "exactly the place and cursor status you came from"; main.js)
/** Where you are in `root`'s editors (the one you're in): the caret or text selected ({anchor, head}: each the block
 * of text it's in, how far in, and what that block holds), or blocks selected whole ({blocks: [first id, last id]});
 * `path`: the quotes (their ids) the editor it's in is inside, outermost first; `quiet`: nothing drawn yet. Null: none. */
export function spotOf(root) {
  const e = root && current && !current.gone && editorsIn(root).includes(current) ? current : null;
  if (!e) return null;
  const path = [];
  for (let x = e; x.holder; x = x.holder.parent) path.unshift(x.holder.node.attrs.id);
  const sel = e.view.state.selection, base = { path, quiet: !!e.quiet, level: !!levelKey.getState(e.view.state) };
  if (sel instanceof NodeSelection) return { ...base, blocks: [sel.node.attrs.id, sel.node.attrs.id] };
  if (sel instanceof BlockSelection) { const b = sel.blocks(); return b.length ? { ...base, blocks: [b[0].node.attrs.id, b.at(-1).node.attrs.id] } : null; }
  const at = ($p) => {
    for (let d = $p.depth; d > 0; d--) { const n = $p.node(d); if (n.isTextblock && n.attrs.id) return { id: n.attrs.id, off: $p.pos - $p.start(d), holds: holds(n) }; }
    return null;
  };
  const anchor = at(sel.$anchor), head = at(sel.$head);
  return anchor && head ? { ...base, anchor, head } : null;
}
/** What a block of text holds, its line breaks and holes too: alike, a place in one is the same place in the other. */
const holds = (n) => n.textBetween(0, n.content.size, "", (leaf) => `\u0000${leaf.type.name}`);
/** Spot `spot` as a selection of `doc`, or null: not there as it was (a block not shown, or shown otherwise: masked). */
function spotIn(doc, spot) {
  const find = (id) => { let at = null; doc.descendants((n, pos) => { if (at === null && n.attrs.id === id) at = pos; return at === null; }); return at; };
  if (spot.blocks) {
    const [a, b] = spot.blocks.map(find);
    if (a === null || b === null) return null;
    if (a === b) return selectBlock(doc, a);
    const $a = doc.resolve(a), $b = doc.resolve(b);
    return $a.parent === $b.parent ? new BlockSelection($a, doc.resolve(b + doc.nodeAt(b).nodeSize)) : null;
  }
  const place = ({ id, off, holds: was }) => {
    const at = find(id), n = at === null ? null : doc.nodeAt(at);
    return n?.isTextblock && holds(n) === was ? at + 1 + off : null;
  };
  const a = place(spot.anchor), h = place(spot.head);
  return a === null || h === null ? null : TextSelection.create(doc, a, h);
}
/** Spot `spot` (spotOf, kept as the page was left) put back in `root`'s editors, the one it was in (by the quotes it's
 * inside), as it was: quiet stays quiet. Not there as it was (changed since): left as the page opened. The editor it
 * was put back in, or false. With `focus` off (a menu open over it), the focus is left where it is: it's only the
 * editor you're in. */
export function restoreSpot(root, spot, { focus = true } = {}) {
  if (!root || root.gone || !spot) return false;
  let e = root;
  for (const qid of spot.path || []) { e = [...e.kids].find((k) => k.holder?.node.attrs.id === qid); if (!e) return false; }
  const sel = spotIn(e.view.state.doc, spot);
  if (!sel) return false;
  if (focus) e.view.focus(); else setCurrent(e);
  e.view.dispatch(e.view.state.tr.setSelection(sel).setMeta(levelKey, !!spot.level));
  if (spot.quiet) e.hush();
  return e;
}

/** Spot `spot` (spotOf, taken before an action) put back in `root` after the action redrew it, following its text
 * where the action moved it (2026-11-19: the cursor stays where it was): as it was; or, its block a quote now (Turn
 * into a quote, its redo), in the quote, in the one block of text there that holds what it held; or, the quote it was
 * in text again (undone, Turn into text), in that text. The editor it was put back in, or false. */
export function keepSpot(root, spot, how = {}) {
  if (!spot) return false;
  const as = restoreSpot(root, spot, how);
  if (as) return as;
  if (!spot.anchor || spot.anchor.id !== spot.head.id) return false;   // (text selected across blocks: not followed)
  let e = root;
  for (const qid of spot.path || []) { e = [...(e?.kids || [])].find((k) => k.holder?.node.attrs.id === qid); }
  const id = spot.anchor.id;
  const inside = e && [...e.kids].find((k) => k.holder?.node.attrs.id === id);   // its block a quote now: into it
  if (inside) {
    let text = null;
    inside.view.state.doc.descendants((n) => { if (!text && n.isTextblock && n.attrs.id && holds(n) === spot.anchor.holds) text = n.attrs.id; return !text; });
    if (text) return restoreSpot(root, { ...spot, path: [...spot.path, id], anchor: { ...spot.anchor, id: text }, head: { ...spot.head, id: text } }, how);
  }
  if (spot.path?.length) {   // the quote it was in is text again: out of it
    const out = spot.path.at(-1);
    return restoreSpot(root, { ...spot, path: spot.path.slice(0, -1), anchor: { ...spot.anchor, id: out }, head: { ...spot.head, id: out } }, how);
  }
  return false;
}

/** A line a masked quote keeps as it is (the lens's rawline): a quote inside it drawn as any quote, with what it shows
 * (read only: written in where it lives), or the picture. */
function keptView(node, open) {
  const d = node.attrs.data;
  let dom;
  if (d?.t === "quote") dom = quoteEl(d, open);
  else if (d?.t === "image" && d.file) { dom = document.createElement("div"); dom.className = "fw-image"; const img = document.createElement("img"); img.src = `/images/${d.file}`; dom.append(img); }
  else { dom = document.createElement("div"); dom.className = "fw-rawline"; dom.textContent = `❝ ${node.attrs.title}`; }
  dom.contentEditable = "false";
  return { dom, ignoreMutation: () => true, stopEvent: () => false };
}

const MARGIN = 60;   // px kept between the cursor and the screen's top and bottom (the status bar's there)
/** The cursor kept on screen (the user, 2026-11-18: a big block mustn't be scrolled to as a whole): the text cursor
 * scrolled just into view; a block selected whole, left where it is if any of it shows, else its nearest edge in.
 * Returns true: ProseMirror's own scrolling (to the whole block) isn't wanted. */
function keepInView(view) {
  const sel = view.state.selection, bottom = innerHeight - MARGIN;
  let top, end;
  if (sel.empty || sel instanceof TextSelection) {
    try { ({ top, bottom: end } = view.coordsAtPos(sel.head)); } catch { return false; }
  } else {
    const dom = view.nodeDOM(sel.from);
    if (!dom?.getBoundingClientRect) return false;
    ({ top, bottom: end } = dom.getBoundingClientRect());
    if (end > MARGIN && top < bottom) return true;   // (some of it shows: stay)
    if (end <= MARGIN) top = end - 24; else end = top + 24;   // (its nearest edge, in)
  }
  if (top < MARGIN) scrollBy(0, top - MARGIN);
  else if (end > bottom) scrollBy(0, end - bottom);
  return true;
}

/** An expression's value, browsed (BlockEditor's `browse`): nothing changes its document but a new value (meta
 * "fw-value"); typing, deleting, Enter, pasting, cutting, undo, Turn into a quote refused. The arrows, selecting,
 * copying, Esc (out, the expression selected) and Open it work; the `code` key shows the expression's code. */
const EDITS = new Set(["Backspace", "Delete", "Tab"]);   // (Enter: a level in, as anywhere at block level; nothing else)
function browsing(ed) {
  return new Plugin({
    filterTransaction: (tr) => !tr.docChanged || !!tr.getMeta("fw-value"),
    // (no caret in it, the user, 2026-11-24: "dont let the user put the caret in the text but they can select the
    // blocks, it should WORK THE EXACT SAME AS OTHER NESTING": a caret or a span of text, from a click or the arrows,
    // becomes the block it's in, selected whole, at block level)
    appendTransaction: (trs, _, state) => {
      const sel = state.selection;
      if (!(sel instanceof TextSelection)) return null;
      const $p = sel.$from;
      for (let d = $p.depth; d > 0; d--) {
        if ($p.node(d).isTextblock) return state.tr.setSelection(selectBlock(state.doc, $p.before(d))).setMeta(levelKey, true);
      }
      return null;
    },
    props: {
      handleTextInput: () => true,
      handleClick: (v, pos) => {   // (a click: the block under it, selected whole)
        const $p = v.state.doc.resolve(pos);
        for (let d = $p.depth; d > 0; d--) {
          if (!$p.node(d).isTextblock) continue;
          if (!v.hasFocus()) v.focus();
          v.dispatch(v.state.tr.setSelection(selectBlock(v.state.doc, $p.before(d))).setMeta(levelKey, true));
          if (d === 1 && v.state.doc.childCount === 1) ed.levelOut();   // (a value's one block is its holder's box: the holder, selected whole)
          return true;
        }
        return false;
      },
      handlePaste: () => true,
      handleDrop: () => true,
      handleDOMEvents: { beforeinput: (v, e) => { e.preventDefault(); return true; } },
      handleKeyDown: (v, e) => {
        if (pressed(e, "code")) { ed.holder?.showCode?.(); return true; }
        const mod = e.metaKey || e.ctrlKey;
        if (EDITS.has(e.key)) return true;
        if (mod && ["x", "v", "z", "y", "e", "k", "d"].includes(e.key.toLowerCase())) return true;
        return false;
      },
    },
  });
}

export class BlockEditor extends EditorRunes {   // (what the page derives from, as runes: editor-state.svelte.js)
  /** `host`: where it's drawn; `id`: the block it writes into; `children`: what it holds (the core's tree);
   * `base`: the content it was built on; `around`: the editors this one's inside (outermost last), whose
   * shown text a save here changes; `exit(dir)`: leave it (a quote's editor: -1 up, 1 down, 0 select it);
   * `open(target, at)`: Open it; `status()`: something changed worth saying; `version`: the store's version it was read
   * at, sent with its saves: written elsewhere since, they merge (fw_store.transact). */
  constructor(host, { id, children, base, version = null, readOnly = false, browse = false, around = [], exit = null, open, status = () => {}, act = () => false, holder = null, top = null, lens = null,
    fields = () => ({}), saved = () => {}, bottom = null, begin = null }) {
    super();
    // (bottom(): ↓ past the last line, home's search; begin(): no id yet (home's waiting pericope, 2026-11-19): its
    // pericope made in the background on the first change, a promise of the core's {id, base}; saves wait for it)
    // (top(): ↑ from the first line, the page's header; lens: {qid, segments, hole}, written through a masked quote;
    // fields(): what else goes with its next save, the header's (its title, when changed); saved(sent): a save done, what went with it)
    // (browse: an expression's value, the user, 2026-11-24: "we should be able to use the cursor to step through the blocks
    // of an evaluation just not delete or edit": the cursor, selecting and copying work, nothing changes it but its value)
    readOnly = readOnly || browse;
    Object.assign(this, { id, base, version, readOnly, browse, around, exit, open, status, act, holder, top, lens, fields, onSaved: saved, bottom, begin });
    this.making = null;   // (the pericope being made, begin()'s promise: until then nothing's written)   // (act: the Ctrl+/ menu's; holder: the QuoteView it's in)
    this.peeking = new Set();    // the paraphrases whose source shows inside them (Show its source), this session
    this.saving = null;   // (a save in flight: a promise, settled when it's done)
    this.timer = null;
    this.view = new EditorView(host, {
      state: this.make(children),
      editable: () => !readOnly || browse,
      attributes: browse ? { class: "fw-value" } : {},   // (a value: its one block, if it has only one, unwrapped: app.css)
      handleScrollToSelection: (view) => keepInView(view),   // (the cursor kept on screen, never the whole block)
      nodeViews: { quote: (node, view, getPos) => new QuoteView(node, view, getPos, this), expr: (node, view, getPos) => new ExprView(node, view, getPos, this.open, this), rawline: (node) => keptView(node, this.open) },
      handleClick: (view, pos, e) => {   // ⌘- or ^-click on a link: Open it
        if (!(e.metaKey || e.ctrlKey)) return false;
        const m = view.state.doc.resolve(pos).marks().find((x) => x.type.name === "link")
          || (view.state.doc.nodeAt(pos)?.marks || []).find((x) => x.type.name === "link");
        if (!m) return false;
        this.open({ target: m.attrs.to });
        return true;
      },
      dispatchTransaction: (tr) => {
        if (TEST) {   // (the tests' record of what changed the document and the selection, the last 20: their reports)
          const log = (window.fwLog ||= []);
          log.push({ ed: this.exit ? "quote" : "page", steps: tr.steps.map((st) => JSON.stringify(st.toJSON()).slice(0, 90)), sel: tr.selection.toJSON(), meta: Object.keys(tr.meta || {}) });
          if (log.length > 20) log.shift();
        }
        this.view.updateState(this.view.state.apply(tr));
        this.pm = this.view.state;
        if (tr.docChanged && tr.getMeta("fw-follow")) this.tellLive();   // (the store's change, followed: nothing to save, no visit)
        else if (tr.docChanged) {
          this.tellLive();
          visits.changed(this);
          this.schedule();
          if (tr.getMeta("addToHistory") !== false) this.act(this, "changed");   // (what was undone can't be redone now)
        }
        this.status();
      },
    });
    this.giveIds();
    this.pm = this.view.state;
    this.tellLive();
    this.since = wordsIn(this.pm.doc);
    this.saved = this.draft();
    // (the one you're in: as the focus comes to it; left for anything but a menu or a question, or another window)
    this.view.dom.addEventListener("focus", () => setCurrent(this));
    // (quiet, arrived from a block selected whole: until a key or a click, nothing drawn as where you are)
    // (a key that only moves you elsewhere, or a modifier pressed on its own, isn't a touch: stepping back out of it, it
    // stays as it was, 2026-11-19, later). Anything that would change what's selected whole, unseen (typing, dictation,
    // ⌫, ⌦, ↵, a paste or a cut), only shows it: nothing you can't see is replaced.
    const unquiet = (e) => {
      if (!this.quiet || (e.type === "keydown" && (["Meta", "Control", "Alt", "Shift", "CapsLock"].includes(e.key) || TRAVEL.some((id) => pressed(e, id))))) return;
      this.view.dispatch(this.view.state.tr.setMeta(hereKey, { quiet: false }).setMeta("addToHistory", false));
      const sel = this.view.state.selection, mod = e.metaKey || e.ctrlKey;
      const edits = ["beforeinput", "paste", "cut"].includes(e.type)
        || (e.type === "keydown" && ((e.key.length === 1 && !mod) || ["Backspace", "Delete", "Enter"].includes(e.key) || (mod && ["v", "x"].includes(e.key.toLowerCase()))));
      if (edits && (sel instanceof NodeSelection || sel instanceof BlockSelection)) { e.preventDefault(); e.stopImmediatePropagation(); }
    };
    for (const type of ["keydown", "mousedown", "beforeinput", "paste", "cut"]) this.view.dom.addEventListener(type, unquiet, true);
    for (const type of ["keydown", "mousedown", "beforeinput"]) this.view.dom.addEventListener(type, () => visits.input(this));   // (attention: visits.js)
    this.view.dom.addEventListener("blur", (e) => {
      const to = e.relatedTarget;
      if (!to || to.closest?.(".fw-menu, .fw-ask, .ProseMirror")) return;
      if (current === this) setCurrent(null);
    });
  }

  /** The pericope open on the page (not a quote's editor, nor a masked one's): its document handed to the expression
   * engine's snapshot as it is now (snapshot.svelte.js), so every expression on the page follows each key. */
  /** An expression's value (`children`, the core's tree's shape) as a browsed editor in `host`, inside this one,
   * held by `holder` (an ExprView, entered and left as a quote's editor is). */
  valueEditor(host, children, holder) {
    const ed = new BlockEditor(host, { id: null, children, base: null, browse: true, around: [this, ...this.around],
      exit: (dir) => QuoteView.prototype.exit.call(holder, dir), open: this.open, status: this.status, act: this.act, holder });
    this.kids.add(ed);
    views.set(holder.dom, holder);
    ed.view.dom.addEventListener("focus", () => holder.dom.classList.add("fw-in"));
    ed.view.dom.addEventListener("blur", () => holder.dom.classList.remove("fw-in"));
    return ed;
  }
  /** Into the value `holder` (an ExprView, a call, a window in a value) holds, at its first block or its last, selected
   * whole. A value of one block is unwrapped (the user, 2026-11-24: "we should always unwrap wrappings with just one
   * block"): one block of text (or a picture) is the holder's own box, nothing to go into (false: the holder stays
   * selected whole); one container or window, its blocks, as if they were the value's. */
  enterValue(holder, where) {
    const ed = holder.inner;
    if (!ed) return false;
    const d = ed.view.state.doc;
    if (d.childCount !== 1) { ed.selectLevel(where === "start" ? 0 : d.content.size - d.lastChild.nodeSize); return true; }
    const c = d.firstChild;
    if (c.type.name === "quote") { const qv = views.get(ed.view.nodeDOM(0)); return !!qv && this.enterValue(qv, where); }
    if (c.isTextblock || c.isAtom || !c.childCount) return false;
    ed.selectLevel(where === "start" ? 1 : 1 + c.content.size - c.lastChild.nodeSize);
    return true;
  }

  /** Value editor `ed` showing `children` now (a new value: the cursor kept where it was, as near as it can be). */
  revalue(ed, children) {
    const v = ed.view, doc = schema.nodeFromJSON(pmDoc(children));
    const at = Math.min(v.state.selection.from, doc.content.size);
    const tr = v.state.tr.replaceWith(0, v.state.doc.content.size, doc.content).setMeta("fw-value", true).setMeta("addToHistory", false);
    try { tr.setSelection(Selection.near(tr.doc.resolve(Math.min(at, tr.doc.content.size)))); } catch {}
    v.dispatch(tr);
  }
  dropValue(ed) { this.kids.delete(ed); ed.destroy(); }

  tellLive() {
    if (!this.holder && !this.lens && this.id) setLive(this.id, this.view.state.doc.toJSON());
  }

  make(children) {
    const ids = new Plugin({ appendTransaction: (trs, _, state) => (trs.some((t) => t.docChanged) ? idsTr(state) : null) });
    const guide = new Plugin({   // a paraphrase's ↗, as a quote's; not written yet, its source dim; Show its source, the same
      props: {
        decorations: (state) => {
          const out = [];
          state.doc.descendants((n, pos) => {
            const para = n.attrs?.para;
            if (!para) return;
            const go = () => {
              const g = document.createElement("span");
              g.className = "fw-open";
              g.contentEditable = "false";
              g.textContent = "↗";
              g.title = "Open it";
              g.addEventListener("mousedown", (e) => { e.preventDefault(); this.open({ target: para.id, home: para.home }); });
              return g;
            };
            out.push(Decoration.widget(pos + 1, go, { side: -2, ignoreSelection: true, key: `o${n.attrs.id}${para.id}` }));
            const empty = n.type.name === "text_block" && n.content.size === 0;
            if (empty || this.peeking.has(n.attrs.id)) {
              const make = () => {
                const g = document.createElement(n.type.name === "text_block" ? "span" : "div");
                g.className = empty ? "fw-guide" : "fw-peek";
                g.textContent = para.text.slice(0, 600);
                return g;
              };
              out.push(Decoration.widget(pos + 1, make, { side: -1, ignoreSelection: true, key: `${empty ? "g" : "p"}${n.attrs.id}${para.text.length}` }));
            }
          });
          return DecorationSet.create(state.doc, out);
        },
      },
    });
    const here = new Plugin({   // where you are, drawn: only in the editor you're in (its state says: setCurrent, hush)
      key: hereKey,
      state: { init: () => ({ current: current === this, quiet: this.quiet }),   // (drawn again from the store: as it was)
                 apply: (tr, was) => { const m = tr.getMeta(hereKey); return m ? { ...was, ...m } : was; } },
      props: {
        // (one focus, the user, 2026-11-18: either a caret, editing, or blocks selected whole, never both: selecting,
        // no caret shows)
        attributes: (state) => {
          const { current: mine, quiet } = hereKey.getState(state);
          if (!mine) return {};
          const selecting = quiet || state.selection instanceof NodeSelection || state.selection instanceof BlockSelection;
          return { class: [quiet ? "" : "fw-current", selecting ? "fw-selecting" : ""].filter(Boolean).join(" ") };
        },
        decorations: (state) => {
          const { current: mine, quiet } = hereKey.getState(state);
          if (!mine || quiet) return null;   // (quiet: arrived from a block selected whole, nothing yet where you are)
          const sel = state.selection, { $from } = sel;
          const chosen = (from, to) => Decoration.node(from, to, { class: "fw-chosen" });
          if (sel instanceof NodeSelection) return DecorationSet.create(state.doc, [chosen(sel.from, sel.to)]);   // (selected whole)
          if (sel instanceof BlockSelection) return DecorationSet.create(state.doc, sel.blocks().map(({ node, pos }) => chosen(pos, pos + node.nodeSize)));
          for (let d = $from.depth; d > 0; d--) {
            if ($from.node(d).type.name === "text_block") {
              return DecorationSet.create(state.doc, [Decoration.node($from.before(d), $from.after(d), { class: "fw-here" })]);
            }
          }
          return null;
        },
      },
    });
    if (this.lens) {   // through a masked quote: only the shown text written; every hole, kept line and block stays
      const count = (doc) => { const n = { hole: 0, rawline: 0, text_block: 0 }; doc.descendants((x) => { if (x.type.name in n) n[x.type.name]++; }); return JSON.stringify(n); };
      const guard = new Plugin({ filterTransaction: (tr, state) => !tr.docChanged || count(tr.doc) === count(state.doc) });
      const lensKeys = keymap({ "Enter": (state, dispatch) => { if (dispatch) dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create())); return true; } });
      return EditorState.create({ doc: schema.nodeFromJSON(pmLens(this.lens.segments, this.lens.hole)),
        plugins: [lensKeys, inlineCode(this), this.keys(), keymap(baseKeymap), history(), guard, here] });
    }
    const slash = slashMenu(this, (at) => this.enterQuote(at));
    // a block marked (mark(id, cls): the block a step between pericopes goes through, motion.js): its element given the
    // classes by ProseMirror itself, which keeps them (it redraws an element whose classes are changed from outside)
    const marking = new Plugin({
      state: { init: () => null, apply: (tr, was) => { const m = tr.getMeta(markKey); return m === undefined ? was : m; } },
      key: markKey,
      props: {
        decorations: (state) => {
          const m = markKey.getState(state);
          if (!m) return null;
          let deco = null;
          state.doc.descendants((n, pos) => { if (!deco && n.attrs.id === m.id) deco = Decoration.node(pos, pos + n.nodeSize, { class: m.cls }); return !deco; });
          return deco ? DecorationSet.create(state.doc, [deco]) : null;
        },
      },
    });
    return EditorState.create({ doc: schema.nodeFromJSON(pmDoc(children)),
      plugins: [...(this.browse ? [browsing(this)] : []), slash, inlineCode(this), exprGuard(), blocksPlugin(), clipboardPlugin(this), this.keys(), keymap(baseKeymap), history(), ids, here, guide, marking] });
  }

  keys() {
    const quoteAt = (state) => {   // the quote selected whole, and its view
      const n = state.selection instanceof NodeSelection ? state.selection.node : null;
      if (!n || n.type.name !== "quote") return null;
      return { node: n, qv: views.get(this.view.nodeDOM(state.selection.from)) };
    };
    const into = (where) => (state) => {   // the same arrow again, on a quote selected whole: into it
      const q = quoteAt(state);
      return !!(q && q.qv && q.qv.inner && q.qv.enter(where));
    };
    const onto = (dir) => (state, dispatch, view) => {   // ↑/↓ past a line's edge onto a quote: into it, not selecting it
      // whole first (the user, 2026-11-20: "we should just enter"; Esc is how a block is selected whole)
      const sel = state.selection;
      if (!(sel instanceof TextSelection) || !sel.empty || !view.endOfTextblock(dir < 0 ? "up" : "down")) return false;
      const $p = state.doc.resolve(dir < 0 ? sel.$from.before(sel.$from.depth) : sel.$to.after(sel.$to.depth));
      return enterQuote(view, Selection.findFrom($p, dir, false), dir);
    };
    const edge = (dir) => (state, dispatch, view) => {   // at the top or bottom of a quote's editor: out of it; at the page's top, the header
      if (!this.exit && !(dir < 0 && this.top) && !(dir > 0 && this.bottom)) return false;
      const sel = state.selection, whole = sel instanceof NodeSelection;
      const pos = dir < 0 ? (whole ? sel.from : sel.$from.before(sel.$from.depth)) : (whole ? sel.to : sel.$to.after(sel.$to.depth));
      // (anything before or after this block to go to: text, or a quote or picture to select whole; only past the last
      // of them is the edge: a quote below the last line is reached, the user, 2026-11-18)
      const more = Selection.findFrom(state.doc.resolve(pos), dir, false);
      const textEdge = whole || view.endOfTextblock(dir < 0 ? "up" : "down");
      if (more || !textEdge) return false;
      if (this.exit) this.exit(dir); else if (dir < 0) this.top(); else this.bottom();
      return true;
    };
    const below = (state) => {   // ↓ on the page's last picture, selected whole: a block below it to write in
      const sel = state.selection;
      return sel instanceof NodeSelection && sel.to === state.doc.content.size && this.roomBelow();
    };
    const out = (dir) => (state, dispatch) => {   // blocks selected whole (not one quote): the cursor into the first or last
      const sel = state.selection;
      if (!(sel instanceof BlockSelection)) return false;
      if (dispatch) dispatch(state.tr.setSelection(dir < 0 ? Selection.near(state.doc.resolve(sel.from + 1), 1) : Selection.near(state.doc.resolve(sel.to - 1), -1)));
      return true;
    };
    const side = (dir) => (state, dispatch, view) => {   // ← at the very start, → at the very end: out too
      if (!this.exit) return false;
      const sel = state.selection;
      const end = dir < 0 ? Selection.atStart(state.doc) : Selection.atEnd(state.doc);
      if (!(sel.empty && sel.from === end.from && view.endOfTextblock(dir < 0 ? "left" : "right"))) return false;
      this.exit(dir);
      return true;
    };
    // block level (blocks.js atLevel): ↑/↓ the block before or after at the same level, past the first or last in a
    // container or quote the one before or after it, a level out; → (or Enter) in a level: a container's or a quote's
    // first block, and text, bottomed out, to writing (→ the caret at its start, Enter at its end; a quote showing one
    // block of text, into its text); ← out a level, the block around it (out of a quote: the quote), and with nothing
    // around it (the page's top level) to writing, the caret at its start (the user, 2026-11-19)
    const levelMove = (dir) => (state) => atLevel(state) && this.levelStep(state.selection.from, state.selection.to, dir);
    const levelIn = (where) => (state, dispatch) => {
      if (!atLevel(state)) return false;
      const pos = state.selection.from, n = state.doc.nodeAt(pos);
      if (n?.type.name === "quote") {
        const qv = views.get(this.view.nodeDOM(pos)), inner = qv?.inner;
        if (!inner) return false;
        const d = inner.view.state.doc;
        if (qv.node.attrs.data?.expr || this.browse) return qv.enter("start");   // (a level in: its first block, as any)
        if (d.childCount === 1 && d.firstChild.isTextblock) return qv.enter(where);
        inner.selectLevel(0);
        return true;
      }
      if (n?.type.name === "expr") {   // (an expression's value: its first block, as a container's)
        const ev = views.get(this.view.nodeDOM(pos));
        return !!ev?.inner && ev.enter("start");
      }
      if (n?.isTextblock && this.browse) return true;   // (a value's text: never written in)
      if (n?.isTextblock) { dispatch?.(state.tr.setSelection(TextSelection.create(state.doc, where === "start" ? pos + 1 : pos + n.nodeSize - 1)).scrollIntoView()); return true; }
      if (n && !n.isAtom && n.childCount) { this.selectLevel(pos + 1); return true; }
      return false;
    };
    const levelOut = (state) => atLevel(state) && this.levelOut();
    const levelStart = (state, dispatch) => {   // (at the top level, nothing around it: the caret at its start)
      if (!atLevel(state)) return false;
      const doc = state.doc, pos = state.selection.from, n = doc.nodeAt(pos);
      if (n.type.name === "quote") { const qv = views.get(this.view.nodeDOM(pos)); return !!(qv?.inner && qv.enter("start")); }
      if (n.isAtom || this.browse) return this.browse;   // (a picture: the caret beside it, as ever; a value: no caret)   // (a picture: the caret beside it, as ever)
      dispatch?.(state.tr.setSelection(Selection.near(doc.resolve(pos + 1), 1)).scrollIntoView());
      return true;
    };
    return keymap({
      "Enter": chainCommands(levelIn("end"), (state, dispatch) => {   // on blocks selected whole (a quote, a picture): a new block below them
        if (!(state.selection instanceof NodeSelection || state.selection instanceof BlockSelection)) return false;
        if (dispatch) {
          const after = state.selection.to;
          const tr = state.tr.insert(after, schema.nodes.text_block.create());
          dispatch(tr.setSelection(TextSelection.create(tr.doc, after + 1)).scrollIntoView());
        }
        return true;
      }, liftEmptyBlock, splitBlock),   // (an empty block inside a container: out a level, the terminal's step_out)
      "Shift-Enter": (state, dispatch) => {
        if (dispatch) dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create()).scrollIntoView());
        return true;
      },
      // undo: what's typed first, then the store actions taken before it (actions.js); redo the same way back
      "Mod-z": chainCommands(undo, () => this.act(this, "undo")),
      "Mod-y": chainCommands(redo, () => this.act(this, "redo")),
      "Mod-Shift-z": chainCommands(redo, () => this.act(this, "redo")),
      "ArrowDown": chainCommands(levelMove(1), into("start"), onto(1), out(1), edge(1), below),
      "ArrowUp": chainCommands(levelMove(-1), into("end"), onto(-1), out(-1), edge(-1)),
      "ArrowLeft": chainCommands(levelOut, levelStart, side(-1)),
      "ArrowRight": chainCommands(levelIn("start"), side(1)),
      "Escape": (state, dispatch) => {   // the block you're in selected whole; again, the one around it; in a quote's editor, at its top, the quote
        const whole = state.selection instanceof NodeSelection || state.selection instanceof BlockSelection;
        if (this.exit && whole && state.selection.$from.depth === 0) { this.exit(0); return true; }
        // (a quote showing one block: that block's box is the quote's, so out a level is the quote itself)
        const doc = state.doc;
        if (this.exit && !whole && doc.childCount === 1 && doc.firstChild.type.name === "text_block") { this.exit(0); return true; }
        return selectAround(state, dispatch);
      },
      "Shift-ArrowUp": grow(-1),
      "Shift-ArrowDown": grow(1),
      "Backspace": chainCommands(removeSelected, joinOut(-1), removeEmpty(-1)),
      "Delete": chainCommands(removeSelected, joinOut(1), removeEmpty(1)),
      // (with ⌘ or ⌥ still held from ⌘↵, the same at a block's edge; elsewhere the browser's word and line deletes)
      "Mod-Backspace": joinOut(-1), "Alt-Backspace": joinOut(-1), "Mod-Delete": joinOut(1), "Alt-Delete": joinOut(1),
      "Mod-Shift-v": () => {   // paste and match style: a plain copy of what was clipped, not live quotes
        this.staticPaste = true;
        setTimeout(() => { this.staticPaste = false; }, 1000);
        return false;   // (the browser pastes)
      },
      // the commands' keys: the user's, else the defaults (keys.js; the bindings page, #/keys)
      ...Object.fromEntries(["menu", "popout", "popopen", "detach", "lock", "mask", "showall", "delete", "link", "unlink"]
        .map((id) => [keyOf(id), () => this.act(this, id)])),
      [keyOf("nest")]: nestIn,
      [keyOf("code")]: (state, dispatch, view) => toggleCode(view),   // (the expr branch: an expression's code)
      [keyOf("open")]: (state) => {   // Open it: a quote selected whole; a link; in a quote's editor, its source at the cursor
        const q = quoteAt(state);
        if (q) { this.open({ ...(q.node.attrs.data || { target: q.node.attrs.target }), whole: true }); return true; }   // (selected whole: arrives quiet)
        const sel = state.selection;   // (an expression selected whole: what it refers to)
        if (sel instanceof NodeSelection && sel.node.type.name === "expr") return this.openRefs(this.view.nodeDOM(sel.from)?.fwExpr);
        const link = this.context().link;
        if (link) { this.open({ target: link.to }); return true; }
        const para = paraAt(state);   // (a paraphrase: its source, as a quote's, the innermost first)
        if (para) { this.open({ target: para.id, home: para.home }); return true; }
        return this.openHere();
      },
    });
  }

  /** ⌘O on expression `ev` (an ExprView): with one thing to open (its value's From, or one @reference), that; with
   * several, the ⌘/ menu at the list of them (TYPE.md: two references are never ambiguous, you pick). */
  openRefs(ev) {
    const refs = ev?.refs() || [];
    if (refs.length === 1) this.open({ target: refs[0] });
    else if (refs.length > 1) this.act(this, "menu:openrefs");
    return true;
  }

  /** Open it from inside a quote's editor: its source, as the pericope, at the cursor (the block it's in, how far in).
   * Not a quote's editor: false. */
  openHere() {
    if (this.browse) return this.openRefs(this.holder);   // (in a value: a computed block opens what its expression refers to)
    if (!this.exit) return false;
    const { $from } = this.view.state.selection;
    let at = null, off = null;
    for (let d = $from.depth; d > 0 && !at; d--) { at = $from.node(d).attrs.id; if (at && $from.node(d).isTextblock && !this.lens) off = $from.pos - $from.start(d); }
    this.open({ target: this.id, at, off });
    return true;
  }

  /** Where the cursor is, for the Ctrl+/ menu: the quote selected whole (`quote`: its node's attrs), the
   * quote it's written in through (`within`: that quote's attrs, if this is a quote's editor), and the block
   * of text it's in (`block`: id, whether it has text). */
  context() {
    const sel = this.view.state.selection;
    const quote = sel instanceof NodeSelection && sel.node.type.name === "quote" ? sel.node.attrs : null;
    const expr = sel instanceof NodeSelection && sel.node.type.name === "expr" ? sel.node.attrs : null;   // (the expr branch)
    let block = null, link = null, span = null;
    if (!(sel instanceof NodeSelection)) {
      const $from = sel.$from;
      for (let d = $from.depth; d > 0 && !block; d--) {
        const n = $from.node(d);
        if (n.type.name !== "text_block") continue;
        const start = $from.start(d), text = n.textBetween(0, n.content.size, undefined, "\n");
        block = { id: n.attrs.id, own: n.attrs.own, text: text.trim() !== "", para: n.attrs.para };
        const off = (pos) => pos - start;   // (an offset into its text: a line break is one, as the store's)
        if (!sel.empty && sel.$to.parent === n) span = { id: n.attrs.id, own: n.attrs.own, text, at: [off(sel.from), off(sel.to)], from: sel.from, end: sel.to };
        const isLink = (m) => m.type.name === "link";
        const mark = (sel.empty ? $from.marks() : $from.marksAcross(sel.$to) || []).find(isLink)
          || ($from.nodeAfter?.marks || []).find(isLink) || ($from.nodeBefore?.marks || []).find(isLink);   // (at either end of it too)
        if (mark) {   // the whole span it marks: the run of pieces carrying it, around the cursor
          const runs = [];
          n.forEach((child, offset) => {
            if (!child.marks.some((m) => m.type.name === "link" && m.attrs.to === mark.attrs.to)) return;
            const from = start + offset, to = from + child.nodeSize, last = runs[runs.length - 1];
            if (last && last[1] === from) last[1] = to; else runs.push([from, to]);
          });
          const run = runs.find(([a, b]) => a <= $from.pos && $from.pos <= b);
          if (run) link = { id: n.attrs.id, own: n.attrs.own, to: mark.attrs.to, title: mark.attrs.title, at: [off(run[0]), off(run[1])], from: run[0], end: run[1] };
        }
      }
    }
    return { quote, expr, within: this.holder ? this.holder.node.attrs : null, block, link, span, para: paraAt(this.view.state) };
  }

  /** Where a new quote at the cursor would go, for the core to draw it from there (GET /api/quote's `into`, `depth`:
   * a ⋯ past the depth, a ↻ where it would show itself; never refused): the blocks around the cursor, by the ids the
   * store knows them by, and the quotes around this. */
  quoteHere() {
    const ids = new Set([this.id]), { $from } = this.view.state.selection;
    for (let d = $from.depth; d > 0; d--) { const n = $from.node(d); if (n.attrs.id) ids.add(this.storeId(n.attrs)); }
    return `&into=${encodeURIComponent([...ids].join(","))}&depth=${this.around.length}`;
  }

  /** The block id the store knows a block of text by: its own (`own`: this editor's block itself), else its id. */
  storeId(b) { return b.own ? this.id : b.id; }

  /** Into the quote at document position `at` (a new pericope's, just quoted: written in at once). */
  enterQuote(at) {
    const qv = views.get(this.view.nodeDOM(at));
    if (qv && qv.inner) qv.enter("start");
  }

  /** Quote block `qid` drawn again, from the core's `data` (masked now, say). */
  setQuote(qid, data) {
    let at = null;
    this.view.state.doc.descendants((n, pos) => { if (at === null && n.type.name === "quote" && n.attrs.id === qid) at = pos; });
    if (at === null || !data || !data.t) return;
    const node = this.view.state.doc.nodeAt(at);
    this.view.dispatch(this.view.state.tr.setNodeMarkup(at, null, { ...node.attrs, data }).setMeta("addToHistory", false));
    this.saved = this.draft();
  }

  giveIds() {
    if (this.lens) return;   // (a lens's blocks are the source's, named by their marker lines)
    const tr = idsTr(this.view.state);
    if (tr) this.view.updateState(this.view.state.apply(tr));
    this.pm = this.view.state;
  }

  draft() {
    if (this.readOnly) return null;
    return this.lens ? lensOf(this.view.state.doc.toJSON(), this.lens.hole) : draftOf(this.view.state.doc.toJSON());
  }
  dirty() { return this.draft() !== this.saved; }
  /** Busy: unsaved or saving here or in a quote it holds, or a menu open (positions in use); then what changed
   * elsewhere waits, for a moment (saves are instant). Being in it isn't busy: a view follows the store while you're in
   * it, its cursor carried along (reload). */
  busy() {
    return this.dirty() || this.saving || ui.menus > 0
      || [...this.kids].some((k) => k.busy());
  }

  schedule() {
    if (!this.id && this.begin && !this.making) {   // the first change to a pericope not made yet: made now, typing never waiting
      this.making = this.begin().then((made) => { if (made) Object.assign(this, { id: made.id, base: made.base }); else this.making = null; },
        () => { this.making = null; });
    }
    clearTimeout(this.timer);
    waiting.add(this);
    this.timer = setTimeout(() => { waiting.delete(this); this.save(); }, SAVE_AFTER);
  }

  /** It and every quote's editor in it, saved. */
  async saveAll() {
    for (const k of this.kids) await k.saveAll();
    await this.save();
  }

  /** Saved into its block: the draft, with what the page's header has changed (fields()) and whatever `extra`
   * (final). One save at a time: another asked for meanwhile waits for it, then goes (never dropped). */
  async save(extra = {}) {
    if (!this.id) {   // (not made yet: nothing to save into until it is; never made, nothing written)
      if (!this.making) return true;
      await this.making;
      if (!this.id) { if (!this.gone) this.schedule(); return false; }
    }
    while (this.saving) await this.saving;
    extra = { ...this.fields(), ...extra };
    if (this.readOnly && !Object.keys(extra).length) return true;
    if (!this.dirty() && !Object.keys(extra).length) return true;
    let done;
    this.saving = new Promise((r) => { done = r; });
    const sent = this.draft();
    // (nothing changed here: no draft, so the store's blocks stay just as they are; the save is for `extra`, the
    // title or the last save's discarding an empty pericope, as the terminal's finish skips a draft it has)
    const draft = this.dirty() ? sent : null;
    const body = this.lens ? { text: sent, base: this.base, version: this.version }
      : { draft, base: this.base, version: this.version, also: this.around.map((e) => e.id), ...extra };
    let r;
    try {
      r = await api(this.lens ? `/api/lens/${this.lens.qid}` : `/api/pericope/${this.id}`, { method: "PUT", body: JSON.stringify(body) });
    } finally {
      this.saving = null;
      done();
    }
    if (r.ok) {
      this.base = this.lens ? (r.body.bases || {})[this.id] || this.base : r.body.base;
      this.version = r.body.version ?? this.version;   // (what it wrote, on what it saw: after a merge, it follows the rest)
      this.saved = sent;
      for (const e of this.around) if (r.body.bases && r.body.bases[e.id]) e.base = r.body.bases[e.id];   // (their shown text changed)
      this.message = (r.body.notes || []).slice(-1)[0] || "";
      this.onSaved(extra);
      this.status();
      return r.body;
    }
    this.message = r.body.error || "not saved";
    this.status();
    if (!this.gone) setTimeout(() => this.save(), RETRY);   // (the terminal retries a refused save)
    return false;
  }

  /** Its quotes kept live (its own blocks unchanged): `children` as the core has them now; a quote whose source changed
   * elsewhere redrawn, just it (its editor, when written through; else the whole, as it holds no editor); one being
   * written in left till it isn't (asked again on the next change). Never anything it wrote itself: its saves keep its
   * quotes' bases up (save). */
  followQuotes(children, version) {
    const now = new Map();
    const walk = (n) => { if (!n) return; if (n.t === "quote") { now.set(n.id, n); (n.tree || []).forEach(walk); } else (n.children || []).forEach(walk); };
    (children || []).forEach(walk);
    let whole = false;
    const visit = (e) => {
      for (const k of e.kids) {
        if (k.holder?.node.attrs.data?.expr) continue;   // (a call's result: it follows the snapshot)
        const q = now.get(k.holder?.node.attrs.id);
        if (q && q.base && q.base !== k.base && !k.busy()) { if (k.lens || !q.tree) whole = true; else k.reload(q.tree, q.base, version); }
        else visit(k);
      }
    };
    visit(this);
    this.view.state.doc.descendants((n, pos) => {   // (a quote drawn from its data, nothing written through it: a locked one, say)
      if (n.type.name !== "quote" || !n.attrs.data) return;
      const q = now.get(n.attrs.id);
      if (n.attrs.data.expr) {   // (a call: its result follows the snapshot, its code the store)
        const here = this.view.nodeDOM(pos)?.fwCall?.source ?? n.attrs.data.expr.source;
        if (q?.expr && q.expr.source !== here) whole = true;
        return;
      }
      if (n.attrs.data.tree || n.attrs.data.lens) return;
      if (q && q.base && n.attrs.data.base && q.base !== n.attrs.data.base) whole = true;
    });
    if (whole && !this.busy()) this.reload(children, this.base, version);
  }

  /** What it holds as the store now has it (nothing unsaved here): just what differs changed, as one step, so the
   * cursor, a selection and undo are carried through it, as a collaborator's edit would be; the quotes whose node is
   * the same keep their views (and their editors), one whose source changed follows it (QuoteView.update). */
  reload(children, base, version) {
    if (this.view.isDestroyed) return;   // (left meanwhile: nothing to draw into)
    if (version !== undefined) this.version = version;   // (first: the quotes drawn new in it take it, QuoteView)
    window.fw && (window.fw.reloads = (window.fw.reloads || 0) + 1);   // (counted, for the tests' reports)
    const now = this.view.state.doc, next = this.make(children).doc;
    const from = now.content.findDiffStart(next.content);
    if (from !== null) {
      let { a, b } = now.content.findDiffEnd(next.content);
      const over = from - Math.min(a, b);   // (a repeated stretch: the ends found past the start)
      if (over > 0) { a += over; b += over; }
      this.view.dispatch(this.view.state.tr.replace(from, a, next.slice(from, b)).setMeta("fw-follow", true).setMeta("fw-value", true).setMeta("addToHistory", false));   // (fw-value: a value, browsed, takes it too)
      this.giveIds();
    }
    this.since = wordsIn(this.view.state.doc);   // (its words as the store has them now)
    this.base = base;
    this.saved = this.draft();
  }

  /** Where the cursor goes, and the view (the user, 2026-11-18): at block `at` (its start, or `off` characters in:
   * where it was in the quote it was opened from, 2026-11-19; or it selected whole), the cursor centered on the screen;
   * else at the very start, the page from its top. */
  place(at = null, off = null) {
    const doc = this.view.state.doc;
    let start = null;
    if (at) doc.descendants((n, pos) => { if (start === null && n.attrs.id === at) start = pos; });
    const node = start !== null ? doc.nodeAt(start) : null;
    const sel = start !== null
      ? (node.isAtom ? NodeSelection.create(doc, start) : TextSelection.create(doc, start + 1 + Math.min(Math.max(0, off || 0), node.isTextblock ? node.content.size : 0)))
      : Selection.atStart(doc);
    this.view.dispatch(this.view.state.tr.setSelection(sel));
    if (start === null) { window.scrollTo(0, 0); return; }
    try {   // the cursor centered on the screen (not the block: a big one would put the cursor off it)
      const { top } = this.view.coordsAtPos(this.view.state.selection.head);
      scrollBy(0, top - innerHeight / 2);
    } catch { this.view.nodeDOM(start)?.scrollIntoView?.({ block: "center" }); }
  }

  /** Block `pos` selected whole, at block level (blocks.js), this the editor you're in. */
  selectLevel(pos) {
    const v = this.view;
    if (!v.hasFocus()) v.focus();
    v.dispatch(v.state.tr.setSelection(selectBlock(v.state.doc, pos)).setMeta(levelKey, true).scrollIntoView());
  }

  /** At block level, out a level: the block around the selected one(s) selected whole; at this editor's top, a quote's,
   * the quote (one showing one block: that block's box is the quote's, so on out past it); the page's top: false. */
  levelOut() {
    const doc = this.view.state.doc, $f = this.view.state.selection.$from;
    const bare = this.browse && doc.childCount === 1;   // (a value of one block: that block has no box of its own, unwrapped)
    if ($f.depth > 0 && !(bare && $f.depth === 1)) { this.selectLevel($f.before()); return true; }
    const q = this.holder;
    if (!q || q.parent.gone) return false;
    const one = doc.childCount === 1 && doc.firstChild.isTextblock && !this.browse;   // (a quote of one block is that block's box: on out past it)
    q.exit(0);
    if (one || (q.parent.browse && q.parent.view.state.doc.childCount === 1)) q.parent.levelOut();   // (an unwrapped box: out past it too)
    return true;
  }

  /** At block level, from blocks `from`–`to` the block after them (`dir` 1) or before (-1) at the same level; none
   * there, the one after (before) the container they're in, a level out, and so on; past this editor's last (first),
   * a quote's, on past the quote in the editor it's in; the page's, nowhere further. */
  levelStep(from, to, dir) {
    const doc = this.view.state.doc;
    for (let $p = doc.resolve(dir > 0 ? to : from); ; $p = doc.resolve(dir > 0 ? $p.after() : $p.before())) {
      const n = dir > 0 ? $p.nodeAfter : $p.nodeBefore;
      if (n) { this.selectLevel(dir > 0 ? $p.pos : $p.pos - n.nodeSize); return true; }
      if ($p.depth === 0) break;
    }
    const q = this.holder;
    if (q && !q.parent.gone) { const pos = q.getPos(); return q.parent.levelStep(pos, pos + q.node.nodeSize, dir); }
    if (dir > 0 && this.bottom) this.bottom();   // (past the page's last block: its foot, the suggestions, as from text; the user, 2026-11-20)
    else if (dir < 0 && this.top) this.top();   // (before its first: the header, as from text; the user, 2026-11-22)
    return true;
  }

  /** Quiet: nothing drawn as where you are (no caret, no block in focus, not the editor you're in) until a key or a click. */
  hush() {
    this.view.dispatch(this.view.state.tr.setMeta(hereKey, { quiet: true }).setMeta("addToHistory", false));
  }

  /** Quiet (hush): its state says. */
  get quiet() { return !!(this.pm && hereKey.getState(this.pm)?.quiet); }

  /** Block `id` marked with classes `cls` (null: none marked), and its element, once drawn. */
  mark(id, cls = "") {
    if (this.gone) return null;
    this.view.dispatch(this.view.state.tr.setMeta(markKey, id ? { id, cls } : null).setMeta("addToHistory", false));
    if (!id) return null;
    let at = null;
    this.view.state.doc.descendants((n, pos) => { if (at === null && n.attrs.id === id) at = pos; return at === null; });
    return at === null ? null : this.view.nodeDOM(at);
  }

  /** The page ends with a quote or picture: going down past it (the user, 2026-11-19: none made on opening, only as you
   * go there), a block to write in below it, the cursor in it (dropped on save if nothing's written). Whether it made one. */
  roomBelow() {
    const state = this.view.state, last = state.doc.lastChild;
    if (this.exit || this.readOnly || !last || !["quote", "image"].includes(last.type.name)) return false;
    const tr = state.tr.insert(state.doc.content.size, schema.nodes.text_block.create()).setMeta("addToHistory", false);
    tr.setSelection(TextSelection.create(tr.doc, tr.doc.content.size - 1));
    this.view.focus();
    this.view.dispatch(tr.scrollIntoView());
    return true;
  }

  /** Saved (and the quotes in it), then gone. */
  async leave(extra = {}) {
    if (this.gone) return;
    this.view.setProps({ editable: () => false });   // (nothing typed now that its last save can't take)
    clearTimeout(this.timer);
    waiting.delete(this);
    for (const k of this.kids) await k.leave();
    await this.save(extra);
    this.destroy();
  }

  destroy() {
    if (this.gone) return;
    if (current === this) current = null;
    this.gone = true;
    clearTimeout(this.timer);
    waiting.delete(this);
    for (const k of this.kids) k.destroy();
    this.kids.clear();
    this.view.destroy();
  }
}

/** A quote in a document. One that can be written through holds a BlockEditor over what it quotes (its
 * target's blocks, saved into the target); one that can't is drawn read only. */
export class QuoteView {
  constructor(node, view, getPos, parent) {
    Object.assign(this, { node, outer: view, getPos, parent, inner: null });
    const data = node.attrs.data || { target: node.attrs.target, body: [] };
    this.dom = quoteEl({ ...data, body: data.tree || data.lens ? [] : data.body }, parent.open);
    this.dom.contentEditable = "false";
    if (data.fromExpr) this.dom.classList.add("fw-from");   // (an expression's From: green, TYPE.md)
    if (data.loop) this.dom.classList.add("fw-loop");   // (Loop: x met again while showing x, its title and ↻)
    if (data.expr) {   // a quote of one expression is a call (TYPE.md): evaluated where this quote sits, its result its
      // blocks, as a quote's are, red; moved through, not written in (for now)
      this.host = this.dom.querySelector(".fw-body");
      this.host.replaceChildren();
      this.dom.fwCall = this;   // (⌘⇧X finds it from the quote selected)
      this.source = data.expr.source;   // (its code: as the store has it, or as written here through it)
      this.stop = onSnapshot(() => this.call());
      hazel.load(() => this.call());
      return;
    }
    views.set(this.dom, this);
    if (data.tree || data.lens) {   // (written through: what it holds, or through its mask, the lens)
      const host = this.dom.querySelector(".fw-body");
      this.inner = new BlockEditor(host, {
        id: data.target, children: data.tree, base: data.base, version: data.version ?? parent.version, around: [parent, ...parent.around], browse: !!parent.browse,
        exit: (dir) => this.exit(dir), open: parent.open, status: parent.status, act: parent.act, holder: this,
        lens: data.lens ? { qid: data.id, segments: data.lens, hole: data.hole } : null,
      });
      parent.kids.add(this.inner);
      this.inner.view.dom.addEventListener("focus", () => this.dom.classList.add("fw-in"));
      this.inner.view.dom.addEventListener("blur", () => this.dom.classList.remove("fw-in"));
    }
  }

  /** A call's code shown (or hidden again), from the quote selected (⌘⇧X): written in the code box an expression
   * has, through to the expression itself (its pericope's editor, unseen, saving as any written-through quote does);
   * the result here follows each key. */
  toggle() {
    if (this.code) { this.close(); return; }
    const data = this.node.attrs.data;
    if (!this.through) {
      this.through = new BlockEditor(document.createElement("div"), { id: data.target, children: data.tree, base: data.base,
        version: data.version ?? this.parent.version, around: [this.parent, ...this.parent.around], open: this.parent.open,
        status: this.parent.status, act: this.parent.act, holder: null });
      this.parent.kids.add(this.through);
    }
    const holder = document.createElement("div");
    holder.className = "fw-expr-codebox fw-expr-code";
    this.dom.querySelector(".fw-body").before(holder);
    this.code = codeBox(holder, this.source, {
      names: namesOf(this.parent, this.node.attrs.id),
      changed: (text) => {
        if (text === this.source) return;
        this.source = text;
        const v = this.through.view;
        v.state.doc.descendants((n, pos) => {
          if (n.type.name === "expr" && n.attrs.id === data.expr.id) v.dispatch(v.state.tr.setNodeMarkup(pos, null, { ...n.attrs, source: text }));
        });
        this.call();
      },
      close: () => this.close(),
      isClose: (e) => pressed(e, "code"),
      leave: (dir) => this.leave(dir),
      away: () => this.away(),
    });
    this.holder = holder;
    this.code.focus();
    this.code.dispatch({ selection: { anchor: this.code.state.doc.length } });
  }
  /** From inside its result (the `code` key there): the quote selected, its code open. */
  showCode() {
    const pos = this.getPos();
    if (pos == null) return;
    this.outer.focus();
    this.outer.dispatch(this.outer.state.tr.setSelection(NodeSelection.create(this.outer.state.doc, pos)));
    this.toggle();
  }
  /** Back to its result, the quote selected. */
  close() {
    const pos = this.getPos();
    this.closing = true;
    if (pos != null && !this.outer.isDestroyed) this.outer.dispatch(this.outer.state.tr.setSelection(NodeSelection.create(this.outer.state.doc, pos)));
    this.outer.fwExprClosed = Date.now();   // (exprGuard: the browser's stray selection, just after, not read back)
    this.outer.focus();
    this.closing = false;
    this.away();
  }
  /** Its code box taken away, nothing else touched (the focus gone elsewhere on the page). */
  away() {
    if (!this.code || this.closing) return;
    const c = this.code;
    this.code = null;
    c.destroy();
    this.holder?.remove();
    this.holder = null;
  }
  /** Out of its code by ↑/↓ at its edge: closed, the caret in the block before (-1) or after (1) it. */
  leave(dir) {
    const pos = this.getPos();
    this.closing = true;
    this.outer.focus();
    this.closing = false;
    this.away();
    if (pos == null || this.outer.isDestroyed) return;
    const at = dir > 0 ? pos + this.node.nodeSize : pos;
    this.outer.dispatch(this.outer.state.tr.setSelection(Selection.near(this.outer.state.doc.resolve(at), dir)).scrollIntoView());
  }

  /** A call (a quote of one expression): its result, worked out where this quote sits, drawn in its body. */
  async call() {
    const r = hazel.run(this.source, this.node.attrs.id, hereOf(this.parent));
    if (r?.kind !== "block") {   // (not blocks: its value, as an expression shows one)
      if (this.inner) { this.parent.dropValue(this.inner); this.inner = null; this.host.replaceChildren(); }
      this.shown = null;
      drawValue(this.host, r, this.parent.open, insideOf(this.parent, this.node.attrs.id), namesOf(this.parent, this.node.attrs.id));
      return;
    }
    const key = JSON.stringify(r.block);
    if (key === this.shown) return;
    this.shown = key;
    const children = await valueTree(r.block.t === "from" ? r.block.child : r.block);   // (the call's own From: this quote)
    if (this.shown !== key || this.gone) return;
    if (!this.inner) { this.host.replaceChildren(); this.inner = this.parent.valueEditor(this.host, children, this); }
    else this.parent.revalue(this.inner, children);
  }

  /** Into it, at its start or its end; one that starts (or ends) with a quote: on into that one, as far as it goes. */
  enter(where) {
    if (this.node.attrs.data?.expr || this.parent.browse) return this.parent.enterValue(this, where);   // (a call, or a window in a value)
    const v = this.inner.view;
    const at = where === "start" ? Selection.atStart(v.state.doc) : Selection.atEnd(v.state.doc);
    if (enterQuote(v, at, where === "start" ? 1 : -1)) return true;
    v.focus();
    v.dispatch(v.state.tr.setSelection(at).scrollIntoView());
    return true;
  }

  /** Out of it: to the block before it (-1), after it (1), or it selected whole (0). */
  exit(dir) {
    const v = this.outer, pos = this.getPos(), doc = v.state.doc;
    // (the next thing that way: text, or a quote or picture selected whole; none in this editor: out of it too, a level
    // further, so the arrows flow on through quotes that end together)
    const near = dir < 0 ? Selection.findFrom(doc.resolve(pos), -1, false) : dir > 0 ? Selection.findFrom(doc.resolve(pos + this.node.nodeSize), 1, false) : null;
    if (!near && dir !== 0 && this.parent.exit) { this.parent.exit(dir); return; }
    if (!near && dir > 0 && this.parent.roomBelow()) return;   // (down out of the page's last quote: a block below it to write in)
    if (dir !== 0 && enterQuote(v, near, dir)) return;   // (out of it onto another quote: into that one, as from text)
    if (!near && dir < 0 && !this.parent.exit && this.parent.top) { this.parent.top(); return; }   // (up out of the page's first: the header, as from text)
    v.focus();
    const tr = v.state.tr.setSelection(near || NodeSelection.create(doc, pos));
    v.dispatch((dir === 0 ? tr.setMeta(levelKey, true) : tr).scrollIntoView());   // (Esc out of it: the quote, at block level)
  }

  // (events inside it are its own, not the page's: its editor's, and masking's panel, whose keys and clicks the page
  // must never take: an arrow moving the page's selection, a click focusing the page and ending masking)
  stopEvent(e) { return !!((this.inner && this.inner.view.dom.contains(e.target)) || this.holder?.contains(e.target) || e.target.closest?.(".fw-masking")); }
  ignoreMutation() { return true; }
  selectNode() { this.dom.classList.add("ProseMirror-selectednode"); }
  deselectNode() { this.dom.classList.remove("ProseMirror-selectednode"); }
  update(node) {
    if (node.attrs.target !== this.node.attrs.target) return false;
    const was = this.node.attrs.data, now = node.attrs.data;
    if (was !== now && now?.expr) {   // (a call: its result follows the snapshot, never what the core says it holds)
      if (this.code && was?.expr?.id === now.expr.id) {   // (its code open here: kept open, following what's stored)
        if (!this.through.busy()) { this.through.reload(now.tree, now.base, this.parent.version); if (now.expr.source !== this.source) { this.source = now.expr.source; setText(this.code, this.source); this.call(); } }
      } else if (!was?.expr || was.expr.source !== now.expr.source) return false;
    } else if (was !== now) {
      // (written through, the same box: what it holds followed in its own editor, the cursor in it kept; anything
      // else about it changed (its top line, a mask, a lock): drawn again)
      const box = (d) => JSON.stringify({ ...d, tree: null, body: null, base: null, ...(d.show?.length ? {} : { words: null, updated: null }) });
      if (!(this.inner && was?.tree && now?.tree && box(was) === box(now))) return false;
      const moved = now.base && !now.fromExpr ? now.base !== this.inner.base : JSON.stringify(now.tree) !== JSON.stringify(was.tree);   // (a value's: what it holds is Hazel's, not the store's)
      if (moved && !this.inner.busy()) this.inner.reload(now.tree, now.base, this.parent.version);
    }
    this.node = node;   // (its id given since, say)
    return true;
  }
  destroy() {
    stopMasking(this.dom);   // (masking it, its box going: the panel too)
    this.gone = true;
    this.stop?.();
    this.code?.destroy();
    if (this.through) { this.parent.kids.delete(this.through); if (this.through.dirty()) this.through.save(); this.through.destroy(); this.through = null; }
    if (this.node.attrs.data?.expr && this.inner) { this.parent.dropValue(this.inner); this.inner = null; return; }
    if (!this.inner) return;
    this.parent.kids.delete(this.inner);
    if (this.inner.dirty()) this.inner.save();   // (what was written through it, kept)
    this.inner.destroy();
  }
}

export { drawBody };

/** Block DOM `box` selected whole, in whichever editor holds it (the page's, or a quote's): a click on its tab. */
export function selectBox(root, box) {
  const pm = box.parentElement?.closest(".ProseMirror");
  const ed = !pm ? null : pm === root.view.dom ? root : views.get(pm.closest(".fw-quote"))?.inner;
  if (!ed) return false;
  let at = null;
  ed.view.state.doc.descendants((n, pos) => { if (at === null && ed.view.nodeDOM(pos) === box) at = pos; });
  if (at === null) return false;
  ed.view.focus();
  ed.view.dispatch(ed.view.state.tr.setSelection(selectBlock(ed.view.state.doc, at)).setMeta(levelKey, true));
  return true;
}
