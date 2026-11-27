// quote.js — a quote in a document. One that can be written through holds an editor over what it quotes (its target's
// blocks, saved into the target); one that can't is drawn read only. A quote of one expression is a call: evaluated
// where it sits, its result its blocks, moved through, not written in.
import { NodeSelection, Selection } from "prosemirror-state";
import { codeBox, setText } from "./codebox.js";
import { stopMasking } from "./masking.js";
import { levelKey } from "./blocks.js";
import { views, enterQuote } from "./here.js";
import { quoteEl, drawValue, insideOf, namesOf, hereOf } from "../expr/views.js";
import { valueTree } from "../expr/exprview.js";
import * as hazel from "../expr/hazel.js";
import { onSnapshot } from "../state/snapshot.svelte.js";
import { pressed } from "../lib/keys.js";

export class QuoteView {
  constructor(node, view, getPos, parent) {
    Object.assign(this, { node, outer: view, getPos, parent, inner: null });
    const data = node.attrs.data || { target: node.attrs.target, body: [] };
    this.dom = quoteEl({ ...data, body: data.tree || data.lens ? [] : data.body }, parent.open);
    this.dom.contentEditable = "false";
    if (data.fromExpr) this.dom.classList.add("fw-from");   // (an expression's From: green)
    if (data.loop) this.dom.classList.add("fw-loop");   // (Loop: x met again while showing x)
    if (data.expr) {
      this.host = this.dom.querySelector(".fw-body");
      this.host.replaceChildren();
      this.dom.fwCall = this;   // (⌘⇧X finds it from the quote selected)
      this.source = data.expr.source;   // (its code: as the store has it, or as written here through it)
      this.stop = onSnapshot(() => this.call());
      hazel.load(() => this.call());
      return;
    }
    views.set(this.dom, this);
    if (data.tree || data.lens) this.writeThrough(data);
  }

  /** Its editor, over what it holds (or through its mask, the lens). */
  writeThrough(data) {
    const parent = this.parent;
    this.inner = new parent.constructor(this.dom.querySelector(".fw-body"), {
      id: data.target, children: data.tree, base: data.base, version: data.version ?? parent.version, around: [parent, ...parent.around], browse: !!parent.browse,
      exit: (dir) => this.exit(dir), open: parent.open, status: parent.status, act: parent.act, holder: this,
      lens: data.lens ? { qid: data.id, segments: data.lens, hole: data.hole } : null,
    });
    parent.kids.add(this.inner);
    this.inner.view.dom.addEventListener("focus", () => this.dom.classList.add("fw-in"));
    this.inner.view.dom.addEventListener("blur", () => this.dom.classList.remove("fw-in"));
  }

  /** A call's code shown (or hidden again), from the quote selected (⌘⇧X): written in a code box, through to the
   * expression itself (its pericope's editor, unseen, saving as any written-through quote does); the result follows. */
  toggle() {
    if (this.code) { this.close(); return; }
    const data = this.node.attrs.data, p = this.parent;
    if (!this.through) {
      this.through = new p.constructor(document.createElement("div"), { id: data.target, children: data.tree, base: data.base,
        version: data.version ?? p.version, around: [p, ...p.around], open: p.open, status: p.status, act: p.act, holder: null });
      p.kids.add(this.through);
    }
    const holder = document.createElement("div");
    holder.className = "fw-expr-codebox fw-expr-code";
    this.dom.querySelector(".fw-body").before(holder);
    this.code = codeBox(holder, this.source, {
      names: namesOf(p, this.node.attrs.id),
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
  /** The quote selected whole in the editor it's in. */
  selectIt() {
    const pos = this.getPos();
    if (pos != null && !this.outer.isDestroyed) this.outer.dispatch(this.outer.state.tr.setSelection(NodeSelection.create(this.outer.state.doc, pos)));
    return pos;
  }
  /** From inside its result (the `code` key there): the quote selected, its code open. */
  showCode() {
    if (this.getPos() == null) return;
    this.outer.focus();
    this.selectIt();
    this.toggle();
  }
  /** Back to its result, the quote selected. */
  close() {
    this.closing = true;
    this.selectIt();
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

  /** A call: its result, worked out where this quote sits, drawn in its body. */
  async call() {
    const p = this.parent, id = this.node.attrs.id;
    const r = hazel.run(this.source, id, hereOf(p));
    if (r?.kind !== "block") {   // (not blocks: its value, as an expression shows one)
      if (this.inner) { p.dropValue(this.inner); this.inner = null; this.host.replaceChildren(); }
      this.shown = null;
      drawValue(this.host, r, p.open, insideOf(p, id), namesOf(p, id));
      return;
    }
    const key = JSON.stringify(r.block);
    if (key === this.shown) return;
    this.shown = key;
    const children = await valueTree(r.block.t === "from" ? r.block.child : r.block);   // (the call's own From: this quote)
    if (this.shown !== key || this.gone) return;
    if (!this.inner) { this.host.replaceChildren(); this.inner = p.valueEditor(this.host, children, this); }
    else p.revalue(this.inner, children);
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

  /** Out of it: to the block before it (-1), after it (1), or it selected whole (0). The next thing that way: text, or
   * a quote or picture selected whole; none in this editor: out of it too, so the arrows flow on through quotes. */
  exit(dir) {
    const v = this.outer, pos = this.getPos(), doc = v.state.doc, p = this.parent;
    const near = dir < 0 ? Selection.findFrom(doc.resolve(pos), -1, false) : dir > 0 ? Selection.findFrom(doc.resolve(pos + this.node.nodeSize), 1, false) : null;
    if (!near && dir !== 0 && p.exit) { p.exit(dir); return; }
    if (!near && dir > 0 && p.roomBelow()) return;   // (down out of the page's last quote: a block below it to write in)
    if (dir !== 0 && enterQuote(v, near, dir)) return;   // (onto another quote: into that one, as from text)
    if (!near && dir < 0 && !p.exit && p.top) { p.top(); return; }   // (up out of the page's first: the header)
    v.focus();
    const tr = v.state.tr.setSelection(near || NodeSelection.create(doc, pos));
    v.dispatch((dir === 0 ? tr.setMeta(levelKey, true) : tr).scrollIntoView());   // (Esc out of it: the quote, at block level)
  }

  // (events inside it are its own: its editor's, its code box's and masking's panel's, never the page's)
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
      // (written through, the same box: what it holds followed in its own editor, the cursor kept; anything else
      // about it changed (its top line, a mask, a lock): drawn again)
      const box = (d) => JSON.stringify({ ...d, tree: null, body: null, base: null, ...(d.show?.length ? {} : { words: null, updated: null }) });
      if (!(this.inner && was?.tree && now?.tree && box(was) === box(now))) return false;
      const moved = now.base && !now.fromExpr ? now.base !== this.inner.base : JSON.stringify(now.tree) !== JSON.stringify(was.tree);   // (a value's: Hazel's, not the store's)
      if (moved && !this.inner.busy()) this.inner.reload(now.tree, now.base, this.parent.version);
    }
    this.node = node;
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
