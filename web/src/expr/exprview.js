// exprview.js — an expression block on the page (the expr branch; the user: "the block shows its result,
// selecting it and hitting a hot key shows the code with the result dim below"; "a computed block can be selected but
// not edited"). At rest: what it evaluates to (hazel.js, views.drawValue): a value of fw's Block type as real blocks,
// any other value printed, a function its type, dim. ⌘⇧X on it selected (`toggle`): its code, written in a box of its
// own, the result dim below it and Hazel's errors under that, following every key; ⌘⇧X or Esc again: back to the
// result, the block selected. Each change to the code is a change to the document (its `source`), saved as any is. The
// result follows the snapshot of the store (snapshot.svelte.js), so it follows every key anywhere on the page.
import { NodeSelection, Plugin, Selection } from "prosemirror-state";
import { enterCode } from "../editor/inlinecode.js";
import { levelKey } from "../editor/blocks.js";
import * as hazel from "./hazel.js";
import { drawValue, quoteOf, insideOf, namesOf, hereOf, toneOf } from "./views.js";
import { onSnapshot } from "../state/snapshot.svelte.js";
import { codeBox, setText, labelOf, refsIn } from "../editor/codebox.js";
import { pressed } from "../lib/keys.js";
import { float } from "../state/float.svelte.js";
import SlashList from "../ui/SlashList.svelte";

/** Hazel's errors, a line each (under a result, its code shown). */
export function errorsEl(r) {
  const d = document.createElement("div");
  d.className = "fw-expr-errors";
  for (const c of r?.casts || []) {   // (each cast put in, said while the code's open: TYPE.md "Casting", visible)
    const line = document.createElement("div");
    line.className = "fw-expr-cast";
    line.textContent = `${c.cast}: ${c.from} → ${c.to}`;
    d.appendChild(line);
  }
  for (const e of r?.errors || []) {
    const line = document.createElement("div");
    line.textContent = `${e.term}: ${e.message}`;
    d.appendChild(line);
  }
  return d;
}

/** A Block value (the bridge's tree) as the blocks a browsed editor holds (the core's tree's shape, draft.pmNode): a
 * text, a paraphrase's words, a container, a quote (as the core draws a new one: quoteOf), a hole a "?". Blocks at the
 * top are the expression's own blocks, as a quote's are its target's. A promise (quotes are asked for). */
export async function valueTree(block) {
  const conv = async (t) => {
    switch (t.t) {
      case "text": return { t: "text", id: null, text: t.text, links: (t.links || []).map((l) => ({ ...l, title: labelOf(l.to) || "" })) };
      case "paraphrase": return { t: "text", id: null, text: t.text, para: { id: t.target, title: labelOf(t.target) || "", text: "", home: t.target } };
      case "blocks": return { t: "container", id: null, children: await Promise.all(t.children.map(conv)) };
      case "loop": {   // (x met again while showing x, the recursive case: its title and a loop, a window on it all the same)
        const q = await quoteOf(t.target);
        return { ...q, expr: undefined, t: "quote", id: null, target: t.target, fromExpr: true, loop: true, lens: null, masked: false, body: [],
          tree: [{ t: "text", id: null, text: `${labelOf(t.target) ?? "?"} ↻`, links: [] }] };
      }
      case "from": {
        if (t.child.t === "loop" && t.child.target === t.target) return conv(t.child);   // (a window on itself: just the loop)   // (blocks that came from a pericope unchanged: drawn as a quote of it, green, TYPE.md; what it
        // holds Hazel's value, so it follows every key as the rest does; its top line the core's)
        const q = await quoteOf(t.target);
        const kids = t.child.t === "blocks" ? t.child.children : [t.child];
        return { ...q, expr: undefined, t: "quote", id: null, target: t.target, fromExpr: true, lens: null, masked: false, body: [],   // (Hazel's value, worked out: never a call again)
          tree: await Promise.all(kids.map(conv)) };
      }
      default: return { t: "text", id: null, text: "?" };
    }
  };
  return block.t === "blocks" ? Promise.all(block.children.map(conv)) : [await conv(block)];
}

export class ExprView {
  constructor(node, view, getPos, open = null, parent = null) {
    this.node = node; this.view = view; this.outer = view; this.getPos = getPos; this.open = open; this.parent = parent;
    this.dom = document.createElement("div");
    this.dom.className = "fw-expr";
    this.dom.contentEditable = "false";
    this.dom.fwExpr = this;   // (the ⌘⇧X command finds it from the block selected)
    this.code = null;
    // its ƒ tab, in the right margin (where a paraphrase's ↗ is): it's code, ⌘⇧X or a click shows it
    // ("we need something which indicates to the user they can edit it")
    this.fn = document.createElement("button");
    this.fn.className = "fw-fn";
    this.fn.textContent = "ƒ";
    this.fn.title = "its code (⌘⇧X)";
    this.fn.addEventListener("mousedown", (e) => { e.preventDefault(); this.code ? this.close() : this.showCode(); });
    this.dom.append(this.fn);
    // its dependencies, a tab each down the right side under the ƒ: what its code names that you
    // can open, each once; as many as its height has room for, the rest behind a "+n"; hovered, a tab grows out to the
    // right with the name; a click opens it
    this.depsEl = document.createElement("div");
    this.depsEl.className = "fw-deps";
    this.depsEl.contentEditable = "false";
    this.dom.append(this.depsEl);
    this.depsKey = null;
    this.sizes = new ResizeObserver(() => this.layoutDeps());
    this.sizes.observe(this.dom);
    // (shown only while it's active: measured as it becomes so, the room then what's below it)
    this.lit = new MutationObserver(() => { if (this.depsEl.offsetParent) this.layoutDeps(); });
    this.lit.observe(this.dom, { attributes: true, attributeFilter: ["class"] });
    this.inner = null;   // (a Block value: a browsed editor, BlockEditor.valueEditor; entered and left as a quote's)
    this.shown = null;   // (the value it shows, as JSON: a new one redraws it)
    this.draw();
    this.stop = onSnapshot(() => this.draw());   // (drawn now, and again as anything it could read changes)
    hazel.load(() => this.draw());   // (the engine loaded after the page opens: drawn again once it's here)
  }

  /** What it depends on that you can open: the pericopes and blocks its code names, each once, that exist and aren't
   * the page you're on. */
  deps() {
    const here = hereOf(this.parent);
    return refsIn(this.node.attrs.source || "").filter((id) => id !== here && labelOf(id) !== null);
  }
  /** Its dependency tabs drawn, under its ƒ (TYPE.md's tab rule): as many as fit from there down
   * to where the next block's own tab sits (at the page's end, as many as there are), the last slot a "+n" for the rest
   * (a click lists them, titles only). */
  layoutDeps() {
    const deps = this.deps();
    const step = 25;   // (px: a tab, its line and the gap: 1.2rem + 2px + .35rem)
    const stackTop = this.dom.getBoundingClientRect().top + (this.fn.offsetTop || 2) + (this.fn.offsetHeight || 19) + 7;
    let next = this.dom.nextElementSibling;
    while (next && !next.matches?.(".fw-text, .fw-container, .fw-quote, .fw-image, .fw-expr")) next = next.nextElementSibling;
    const limit = next ? next.getBoundingClientRect().top + (this.fn.offsetTop || 2) - 6 : Infinity;
    const room = Math.max(1, Math.floor((limit - stackTop + 6) / step));
    const key = `${deps.join(",")}|${Number.isFinite(room) ? room : "all"}|${deps.map((id) => labelOf(id)).join(",")}`;
    if (key === this.depsKey) return;
    this.depsKey = key;
    const shown = deps.length > room ? deps.slice(0, room - 1) : deps, rest = deps.slice(shown.length);
    const tab = (cls, mark, name, onPick) => {
      const b = document.createElement("button");
      b.className = `fw-dep ${cls}`;
      b.tabIndex = -1;
      const m = document.createElement("span"); m.className = "fw-dep-mark"; if (mark) m.textContent = mark;
      const n = document.createElement("span"); n.className = "fw-dep-name"; n.textContent = name;
      b.append(m, n);
      b.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); onPick(b); });
      return b;
    };
    const kids = shown.map((id) => tab("fw-dep-ref", "", labelOf(id), () => this.open?.({ target: id })));
    if (rest.length) kids.push(tab("fw-dep-more", `+${rest.length}`, rest.map((id) => labelOf(id)).join(", "), (b) => {
      const box = float(SlashList, b.getBoundingClientRect(), {
        cmds: rest.map((id) => ({ id, label: labelOf(id), note: "" })), sel: 0,
        run: (c) => { box.dismiss(false); this.open?.({ target: c.id }); },
      });
      const off = (e) => { if (!e.target.closest?.(".fw-menu")) { box.dismiss(false); document.removeEventListener("mousedown", off, true); } };
      document.addEventListener("mousedown", off, true);
    }));
    this.depsEl.replaceChildren(...kids);
  }

  /** What it shows: its value (a Block value as blocks you can move through, not change), or why it can't yet; its
   * code shown, Hazel's errors under it. */
  draw() {
    const r = hazel.run(this.node.attrs.source || "", this.node.attrs.id, hereOf(this.parent));
    this.dom.dataset.tone = toneOf(r);   // (its colour its value's: app.css)
    this.top = r?.kind === "block" && r.block.t === "from" ? r.block.target : null;   // (its value one From: ⌘O opens that)
    if (r?.kind === "block" && this.parent) this.showBlocks(r);
    else {
      this.dropInner();
      this.out = drawValue(this.dom, r, this.open, insideOf(this.parent, this.node.attrs.id), namesOf(this.parent, this.node.attrs.id));
      if (this.item != null) this.items()[this.item]?.classList.add("fw-item-sel");   // (drawn again: the item you're on still lit)
    }
    this.layoutDeps();
    this.dom.querySelector(":scope > .fw-expr-errors")?.remove();
    if (this.code && (r?.errors?.length || r?.casts?.length)) this.dom.appendChild(errorsEl(r));
    this.dom.classList.toggle("fw-expr-coding", !!this.code);
  }

  async showBlocks(r) {
    const key = JSON.stringify(r.block);
    if (key === this.shown) return;
    this.shown = key;
    const children = await valueTree(r.block);
    if (this.shown !== key || this.gone) return;   // (a newer value meanwhile)
    if (!this.inner) {
      const out = document.createElement("div");
      out.className = "fw-expr-out fw-expr-block";
      const host = document.createElement("div");
      host.className = "fw-body";
      out.appendChild(host);
      const was = this.dom.querySelector(":scope > .fw-expr-out");
      if (was) was.replaceWith(out); else this.dom.appendChild(out);
      this.out = out;
      this.inner = this.parent.valueEditor(host, children, this);
    } else this.parent.revalue(this.inner, children);
    this.out.title = r.type || "";
  }

  dropInner() {
    if (!this.inner) return;
    this.parent.dropValue(this.inner);
    this.inner = null;
    this.shown = null;
  }

  /** Into its value, at its start or end (from the arrows, as into a quote): a value of blocks, its first or last block;
   * a list, its first or last item. */
  enter(where) {
    if (this.inner) return this.parent.enterValue(this, where);   // (no caret in a value; one block: unwrapped)
    const n = this.items().length;
    if (!n) return false;
    this.selectItem(where === "end" ? n - 1 : 0);
    return true;
  }
  /** A list value's items as drawn. */
  items() { return [...(this.out?.querySelectorAll(":scope > .fw-item") || [])]; }
  /** Item `n` selected (null: none, the expression itself selected whole again). The expression then drawn as a block
   * you're inside is (the path: faint, its tab too), the item lit ("the same style rules as nested
   * blocks"); `tell`: the editor told, so the tabs follow (not while it's already updating: a selection moving on). */
  selectItem(n, tell = true) {
    if ((n ?? null) === (this.item ?? null)) return;
    this.items().forEach((x, i) => x.classList.toggle("fw-item-sel", i === n));
    this.item = n;
    this.dom.classList.toggle("fw-in-item", n != null);
    if (tell && !this.view.isDestroyed) this.view.dispatch(this.view.state.tr.setMeta("fw-item", n).setMeta("addToHistory", false));
  }
  /** What the item selected refers to (a reference in it), or null. */
  itemRef() {
    const chip = this.item == null ? null : this.items()[this.item]?.querySelector(".fw-ref");
    return chip?.title.match(/^@([0-9]{8}T[0-9]{6}-[0-9a-f]{4})/)?.[1] ?? null;
  }

  /** What ⌘O opens on it, selected whole: what its value is, never what its code reads: its
   * value's source if that's one From, or the one reference it works out to; else nothing (step into it: each item
   * opens on its own). What its code names is in the ⌘/ menu, "Open what it refers to…". */
  refs() {
    if (this.top) return [this.top];
    const chips = this.out?.classList.contains("fw-expr-block") ? [] : [...(this.out?.querySelectorAll(":scope > .fw-ref") || [])];
    const id = chips.length === 1 && !this.items().length ? chips[0].title.match(/^@([0-9]{8}T[0-9]{6}-[0-9a-f]{4})/)?.[1] : null;
    return id ? [id] : [];
  }

  /** Out of its value: to the block before (-1), after (1), or it selected whole (0), as out of a quote. */
  exit(dir) { this.inner?.exit(dir); }

  /** Its code shown, from inside its value (the `code` key there): out of the value, the block selected, the code open. */
  showCode() {
    const pos = this.getPos();
    if (pos == null) return;
    this.view.focus();
    this.view.dispatch(this.view.state.tr.setSelection(NodeSelection.create(this.view.state.doc, pos)));
    this.toggle();
  }

  /** Its code shown (or hidden again): written in a box (codebox.js, CodeMirror), the result dim below. */
  toggle() {
    if (this.code) { this.close(); return; }
    const holder = document.createElement("div");
    holder.className = "fw-expr-codebox fw-expr-code";
    this.dom.prepend(holder);
    this.code = codeBox(holder, this.node.attrs.source || "", {
      names: namesOf(this.parent, this.node.attrs.id),
      changed: (text) => {
        const pos = this.getPos();
        if (pos == null || text === this.node.attrs.source) return;
        this.view.dispatch(this.view.state.tr.setNodeMarkup(pos, null, { ...this.node.attrs, source: text }));
      },
      close: () => this.close(),
      isClose: (e) => pressed(e, "code"),
      leave: (dir) => this.leave(dir),
      away: () => this.away(),
    });
    this.holder = holder;
    this.draw();
    this.code.focus();
    this.code.dispatch({ selection: { anchor: this.code.state.doc.length } });
  }

  /** Its code box taken away, nothing else touched (the focus gone elsewhere on the page). */
  away(force = false) {
    if (!this.code || this.closing) return;
    const pos = this.getPos(), sel = this.view.state.selection;
    if (!force && pos != null && sel instanceof NodeSelection && sel.from === pos) return;   // (still on it: not left)
    const c = this.code;
    this.code = null;
    c.destroy();
    this.holder?.remove();
    this.holder = null;
    this.draw();
  }
  /** Out of its code by ↑/↓ at its edge: closed, the caret in the block before (-1) or after (1) it. */
  leave(dir) {
    const pos = this.getPos();
    this.closing = true;
    this.view.focus();
    this.closing = false;
    this.away(true);
    if (pos == null || this.view.isDestroyed) return;
    const at = dir > 0 ? pos + this.node.nodeSize : pos;
    this.view.dispatch(this.view.state.tr.setSelection(Selection.near(this.view.state.doc.resolve(at), dir)).scrollIntoView());
  }

  /** Back to its result, the block selected. */
  close() {
    this.closing = true;
    // (the editor focused first, the block selected whole, and only then the code box taken away: a focused box
    // removed leaves the browser a selection at the page's top, which the editor would read back as where you are;
    // put back once more after the browser's settled)
    const select = () => {
      const pos = this.getPos();
      if (pos == null || this.view.isDestroyed) return;
      const sel = this.view.state.selection;
      if (!(sel instanceof NodeSelection && sel.from === pos && levelKey.getState(this.view.state)))   // (at block level, as Esc leaves a block)
        this.view.dispatch(this.view.state.tr.setSelection(NodeSelection.create(this.view.state.doc, pos)).setMeta(levelKey, true));
    };
    select();
    this.view.fwExprClosed = Date.now();   // (exprGuard: the browser's stray selection, just after, not read back)
    // (a key pressed before the frame (↓ at once): where it went is yours, not put back)
    let moved = false;
    const mark = () => { moved = true; };
    this.view.dom.addEventListener("keydown", mark, { once: true, capture: true });
    this.view.focus();
    this.code?.destroy();
    this.holder?.remove();
    this.code = null; this.holder = null;
    this.closing = false;
    this.draw();
    requestAnimationFrame(() => { this.view.dom.removeEventListener("keydown", mark, { capture: true }); if (!moved) select(); });
  }

  update(node) {
    if (node.type !== this.node.type) return false;
    this.node = node;
    if (this.code) setText(this.code, node.attrs.source || "");   // (an undo, say)
    this.draw();
    return true;
  }
  stopEvent(e) { return !!((this.holder && this.holder.contains(e.target)) || (this.inner && this.inner.view.dom.contains(e.target))); }   // (the code box's keys and clicks are its own)
  ignoreMutation() { return true; }
  selectNode() { this.dom.classList.add("ProseMirror-selectednode"); }
  deselectNode() { this.dom.classList.remove("ProseMirror-selectednode"); this.selectItem(null, false); }
  destroy() { this.sizes?.disconnect(); this.lit?.disconnect(); this.gone = true; this.stop?.(); this.code?.destroy(); this.dropInner(); }
}

/** The browser's selection read back just after an expression's code box closed (a focused box removed leaves the
 * browser's selection at the page's top) refused: the block stays selected whole. Only that read (ProseMirror's own,
 * "pointer"), only off an expression selected whole, only for a moment. */
export function exprGuard() {
  return new Plugin({
    filterTransaction(tr, state) {
      const view = tr.getMeta("pointer") && !tr.docChanged && tr.selectionSet ? globalThis.__fwViews?.find((v) => v.state === state) : null;
      const sel = state.selection;
      return !(view && Date.now() - (view.fwExprClosed || 0) < 400 && sel instanceof NodeSelection && (sel.node.type.name === "expr" || !!sel.node.attrs.data?.expr));
    },
    view: (v) => { (globalThis.__fwViews ||= []).push(v); return { destroy: () => { globalThis.__fwViews = globalThis.__fwViews.filter((x) => x !== v); } }; },
  });
}

/** A list value's items stepped through (an expression selected whole): → onto its first item, ← onto its last, ←/→
 * between them, ← past the first back to it whole, ↑/↓ and Esc out of them; ⌘O opens the item's reference. */
export function exprItems(editor) {
  return new Plugin({
    props: {
      handleKeyDown(view, e) {
        const sel = view.state.selection;
        if (!(sel instanceof NodeSelection) || sel.node.type.name !== "expr" || e.metaKey && !pressed(e, "open")) return false;
        const ev = view.nodeDOM(sel.from)?.fwExpr;
        if (!ev || ev.inner || ev.code) return false;
        const n = ev.items().length;
        if (ev.item == null) {
          // (→ onto its first item, ← onto its last; Enter is Enter, as on any block selected whole: a new block after
          // it)
          if (n && !e.shiftKey && e.key === "ArrowRight") { ev.selectItem(0); return true; }
          if (n && !e.shiftKey && e.key === "ArrowLeft") { ev.selectItem(n - 1); return true; }
          return false;
        }
        if (pressed(e, "open")) { const id = ev.itemRef(); if (id) editor.open({ target: id }); return true; }
        if (e.key === "ArrowRight") { ev.selectItem(Math.min(n - 1, ev.item + 1)); return true; }
        if (e.key === "ArrowLeft") { ev.selectItem(ev.item > 0 ? ev.item - 1 : null); return true; }
        if (e.key === "Escape") { ev.selectItem(null); return true; }
        if (e.key === "ArrowUp" || e.key === "ArrowDown") ev.selectItem(null);
        return false;
      },
    },
  });
}

/** ⌘⇧X: on an expression block selected, or a quote of one (a call), its code shown or hidden; on an inline
 * expression against the caret, into its code (or out of it). */
export function toggleCode(view) {
  const sel = view.state.selection;
  if (enterCode(view)) return true;   // (an inline expression against the caret: into its code, or out of it)
  if (!(sel instanceof NodeSelection)) return false;
  if (sel.node.type.name === "quote" && sel.node.attrs.data?.expr) { view.nodeDOM(sel.from)?.fwCall?.toggle(); return true; }   // (a call: its expression's code, written through)
  if (sel.node.type.name !== "expr") return false;
  view.nodeDOM(sel.from)?.fwExpr?.toggle();
  return true;
}
