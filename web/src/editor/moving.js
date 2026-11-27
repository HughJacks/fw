// moving.js — BlockEditor's moves: where the cursor goes on opening, block level (selected whole, in and out a level,
// on to the next), into quotes and expressions' values (browsed editors inside it), and a block made below the last.
import { NodeSelection, TextSelection, Selection } from "prosemirror-state";
import { selectBlock, levelKey } from "./blocks.js";
import { schema } from "./schema.js";
import { pmDoc } from "./draft.js";
import { views } from "./here.js";
import { QuoteView } from "./quote.js";

export const moving = {
  /** Where the cursor goes: at block `at` (its start, or `off` characters in; or it selected whole), centered on the
   * screen; else at the very start, the page from its top. */
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
  },

  /** Block `pos` selected whole, at block level, this the editor you're in. */
  selectLevel(pos) {
    const v = this.view;
    if (!v.hasFocus()) v.focus();
    v.dispatch(v.state.tr.setSelection(selectBlock(v.state.doc, pos)).setMeta(levelKey, true).scrollIntoView());
  },

  /** Out a level: the block around the selected one(s) selected whole; at a quote's editor's top, the quote (one showing
   * one block: that block's box is the quote's, so on out past it); the page's top: false. */
  levelOut() {
    const doc = this.view.state.doc, $f = this.view.state.selection.$from;
    const bare = this.browse && doc.childCount === 1;   // (a value of one block: that block has no box of its own)
    if ($f.depth > 0 && !(bare && $f.depth === 1)) { this.selectLevel($f.before()); return true; }
    const q = this.holder;
    if (!q || q.parent.gone) return false;
    const one = doc.childCount === 1 && doc.firstChild.isTextblock && !this.browse;
    q.exit(0);
    if (one || (q.parent.browse && q.parent.view.state.doc.childCount === 1)) q.parent.levelOut();   // (an unwrapped box: out past it too)
    return true;
  },

  /** From blocks `from`–`to` the block after them (`dir` 1) or before (-1) at the same level; none there, the one after
   * (before) the container they're in, and so on; past a quote's editor's last (first), on past the quote; past the
   * page's, its foot (or the header). */
  levelStep(from, to, dir) {
    const doc = this.view.state.doc;
    for (let $p = doc.resolve(dir > 0 ? to : from); ; $p = doc.resolve(dir > 0 ? $p.after() : $p.before())) {
      const n = dir > 0 ? $p.nodeAfter : $p.nodeBefore;
      if (n) { this.selectLevel(dir > 0 ? $p.pos : $p.pos - n.nodeSize); return true; }
      if ($p.depth === 0) break;
    }
    const q = this.holder;
    if (q && !q.parent.gone) { const pos = q.getPos(); return q.parent.levelStep(pos, pos + q.node.nodeSize, dir); }
    if (dir > 0 && this.bottom) this.bottom();
    else if (dir < 0 && this.top) this.top();
    return true;
  },

  /** The page ends with a quote or picture: going down past it, a block to write in below it, the cursor in it
   * (dropped on save if nothing's written). Whether it made one. */
  roomBelow() {
    const state = this.view.state, last = state.doc.lastChild;
    if (this.exit || this.readOnly || !last || !["quote", "image"].includes(last.type.name)) return false;
    const tr = state.tr.insert(state.doc.content.size, schema.nodes.text_block.create()).setMeta("addToHistory", false);
    tr.setSelection(TextSelection.create(tr.doc, tr.doc.content.size - 1));
    this.view.focus();
    this.view.dispatch(tr.scrollIntoView());
    return true;
  },

  /** Into the quote at document position `at` (a new pericope's, just quoted: written in at once). */
  enterQuote(at) {
    const qv = views.get(this.view.nodeDOM(at));
    if (qv && qv.inner) qv.enter("start");
  },

  /** An expression's value (`children`, the core's tree's shape) as a browsed editor in `host`, inside this one, held by
   * `holder` (an ExprView or a call, entered and left as a quote's editor is). */
  valueEditor(host, children, holder) {
    const ed = new this.constructor(host, { id: null, children, base: null, browse: true, around: [this, ...this.around],
      exit: (dir) => QuoteView.prototype.exit.call(holder, dir), open: this.open, status: this.status, act: this.act, holder });
    this.kids.add(ed);
    views.set(holder.dom, holder);
    ed.view.dom.addEventListener("focus", () => holder.dom.classList.add("fw-in"));
    ed.view.dom.addEventListener("blur", () => holder.dom.classList.remove("fw-in"));
    return ed;
  },

  /** Into the value `holder` holds, at its first block or its last, selected whole. A value of one block is unwrapped:
   * one block of text (or a picture) is the holder's own box, nothing to go into (false); one container or window,
   * its blocks, as if they were the value's. */
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
  },

  /** Value editor `ed` showing `children` now (the cursor kept where it was, as near as it can be). */
  revalue(ed, children) {
    const v = ed.view, doc = schema.nodeFromJSON(pmDoc(children));
    const at = Math.min(v.state.selection.from, doc.content.size);
    const tr = v.state.tr.replaceWith(0, v.state.doc.content.size, doc.content).setMeta("fw-value", true).setMeta("addToHistory", false);
    try { tr.setSelection(Selection.near(tr.doc.resolve(Math.min(at, tr.doc.content.size)))); } catch {}
    v.dispatch(tr);
  },
  dropValue(ed) { this.kids.delete(ed); ed.destroy(); },
};
