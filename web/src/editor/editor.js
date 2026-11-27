// editor.js — one block open for writing: a pericope on the page, or what a quote shows when it's written through.
// Each has its own document, undo, saves and base, and saves into its own block through the core. Its parts: plugins.js
// (its state), keymap.js (its keys), saving.js, moving.js, context.js (its methods), quote.js (the quotes in it).
import { EditorView } from "prosemirror-view";
import { NodeSelection } from "prosemirror-state";
import { BlockSelection } from "./blocks.js";
import { EditorRunes } from "./runes.svelte.js";
import { stateFor, idsTr, markKey, keptView, keepInView } from "./plugins.js";
import { hereKey, setCurrent, currentEditor, forget, wordsIn } from "./here.js";
import { saving, waiting } from "./saving.js";
import { moving } from "./moving.js";
import { context } from "./context.js";
import { QuoteView } from "./quote.js";
import { ExprView } from "../expr/exprview.js";
import { setLive } from "../state/snapshot.svelte.js";
import * as visits from "../lib/visits.js";
import { TEST } from "../lib/api.js";
import { pressed } from "../lib/keys.js";

export { waiting, QuoteView };
export { wordsIn, isWord, focusOf } from "./here.js";
export { spotOf, restoreSpot, keepSpot, selectBox } from "./spot.js";

const TRAVEL = ["back", "forward", "home", "done", "keys"];   // (the keys that only move you elsewhere)
const MODS = ["Meta", "Control", "Alt", "Shift", "CapsLock"];

export class BlockEditor extends EditorRunes {
  /** `host`: where it's drawn; `id`: the block it writes into; `children`: what it holds (the core's tree); `base`: the
   * content it was built on; `version`: the store's version it was read at (written elsewhere since, they merge);
   * `around`: the editors this one's inside (outermost last), whose shown text a save here changes; `exit(dir)`: leave
   * it (a quote's editor: -1 up, 1 down, 0 select it); `open(target, at)`: Open it; `status()`: something changed worth
   * saying; `act`: the actions menu's; `holder`: the QuoteView it's in; `top()`/`bottom()`: ↑ from the first line, ↓
   * past the last; `lens`: {qid, segments, hole}, written through a masked quote; `fields()`: what else goes with its
   * next save; `saved(sent)`: a save done; `begin()`: no id yet, its pericope made on the first change (a promise of
   * {id, base}); `browse`: an expression's value, moved through and copied, never changed but by its value. */
  constructor(host, { id, children, base, version = null, readOnly = false, browse = false, around = [], exit = null, open, status = () => {}, act = () => false, holder = null, top = null, lens = null,
    fields = () => ({}), saved = () => {}, bottom = null, begin = null }) {
    super();
    readOnly = readOnly || browse;
    Object.assign(this, { id, base, version, readOnly, browse, around, exit, open, status, act, holder, top, lens, fields, onSaved: saved, bottom, begin });
    this.making = null;   // (the pericope being made, begin()'s promise: until then nothing's written)
    this.peeking = new Set();    // the paraphrases whose source shows inside them (Show its source), this session
    this.saving = null;   // (a save in flight: a promise, settled when it's done)
    this.timer = null;
    this.view = new EditorView(host, {
      state: this.make(children),
      editable: () => !readOnly || browse,
      attributes: browse ? { class: "fw-value" } : {},
      handleScrollToSelection: (view) => keepInView(view),
      nodeViews: { quote: (node, view, getPos) => new QuoteView(node, view, getPos, this), expr: (node, view, getPos) => new ExprView(node, view, getPos, this.open, this), rawline: (node) => keptView(node, this.open) },
      handleClick: (view, pos, e) => this.clickLink(view, pos, e),
      dispatchTransaction: (tr) => this.apply(tr),
    });
    this.giveIds();
    this.pm = this.view.state;
    this.tellLive();
    this.since = wordsIn(this.pm.doc);
    this.saved = this.draft();
    this.listen();
  }

  /** ⌘- or ^-click on a link: Open it. */
  clickLink(view, pos, e) {
    if (!(e.metaKey || e.ctrlKey)) return false;
    const m = view.state.doc.resolve(pos).marks().find((x) => x.type.name === "link")
      || (view.state.doc.nodeAt(pos)?.marks || []).find((x) => x.type.name === "link");
    if (!m) return false;
    this.open({ target: m.attrs.to });
    return true;
  }

  /** Transaction `tr` applied: the store's change followed (nothing to save), or a change of its own saved at once. */
  apply(tr) {
    if (TEST) {   // (the tests' record of what changed the document and the selection, the last 20: their reports)
      const log = (window.fwLog ||= []);
      log.push({ ed: this.exit ? "quote" : "page", steps: tr.steps.map((st) => JSON.stringify(st.toJSON()).slice(0, 90)), sel: tr.selection.toJSON(), meta: Object.keys(tr.meta || {}) });
      if (log.length > 20) log.shift();
    }
    this.view.updateState(this.view.state.apply(tr));
    this.pm = this.view.state;
    if (tr.docChanged) this.tellLive();
    if (tr.docChanged && !tr.getMeta("fw-follow")) {
      visits.changed(this);
      this.schedule();
      if (tr.getMeta("addToHistory") !== false) this.act(this, "changed");   // (what was undone can't be redone now)
    }
    this.status();
  }

  /** The one you're in as the focus comes to it, left for anything but a menu, a question or another window; quiet
   * until a key or a click (a key that only moves you elsewhere, or a modifier alone, isn't one). Anything that would
   * change what's selected whole, unseen (typing, ⌫, ↵, a paste or a cut), only shows it. */
  listen() {
    const dom = this.view.dom;
    dom.addEventListener("focus", () => setCurrent(this));
    const unquiet = (e) => {
      if (!this.quiet || (e.type === "keydown" && (MODS.includes(e.key) || TRAVEL.some((id) => pressed(e, id))))) return;
      this.view.dispatch(this.view.state.tr.setMeta(hereKey, { quiet: false }).setMeta("addToHistory", false));
      const sel = this.view.state.selection, mod = e.metaKey || e.ctrlKey;
      const edits = ["beforeinput", "paste", "cut"].includes(e.type)
        || (e.type === "keydown" && ((e.key.length === 1 && !mod) || ["Backspace", "Delete", "Enter"].includes(e.key) || (mod && ["v", "x"].includes(e.key.toLowerCase()))));
      if (edits && (sel instanceof NodeSelection || sel instanceof BlockSelection)) { e.preventDefault(); e.stopImmediatePropagation(); }
    };
    for (const type of ["keydown", "mousedown", "beforeinput", "paste", "cut"]) dom.addEventListener(type, unquiet, true);
    for (const type of ["keydown", "mousedown", "beforeinput"]) dom.addEventListener(type, () => visits.input(this));
    dom.addEventListener("blur", (e) => {
      const to = e.relatedTarget;
      if (!to || to.closest?.(".fw-menu, .fw-ask, .ProseMirror")) return;
      if (currentEditor() === this) setCurrent(null);
    });
  }

  /** The pericope open on the page (not a quote's editor, nor a masked one's): its document handed to the expression
   * engine's snapshot, so every expression on the page follows each key. */
  tellLive() {
    if (!this.holder && !this.lens && this.id) setLive(this.id, this.view.state.doc.toJSON());
  }

  make(children) { return stateFor(this, children); }

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

  /** Quiet: nothing drawn as where you are (no caret, no block in focus) until a key or a click. */
  hush() { this.view.dispatch(this.view.state.tr.setMeta(hereKey, { quiet: true }).setMeta("addToHistory", false)); }
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
    forget(this);
    this.gone = true;
    clearTimeout(this.timer);
    waiting.delete(this);
    for (const k of this.kids) k.destroy();
    this.kids.clear();
    this.view.destroy();
  }
}
Object.assign(BlockEditor.prototype, saving, moving, context);
