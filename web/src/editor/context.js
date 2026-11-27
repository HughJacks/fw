// context.js — BlockEditor's reading of where the cursor is: for the actions menu (context), for Open it (openHere,
// openRefs) and for a new quote's place (quoteHere).
import { NodeSelection } from "prosemirror-state";
import { paraAt } from "./here.js";

/** The link mark's whole span around the cursor in block `n` (starting at `start`), or null. */
function linkAround(sel, n, start) {
  const { $from } = sel, isLink = (m) => m.type.name === "link";
  const mark = (sel.empty ? $from.marks() : $from.marksAcross(sel.$to) || []).find(isLink)
    || ($from.nodeAfter?.marks || []).find(isLink) || ($from.nodeBefore?.marks || []).find(isLink);   // (at either end of it too)
  if (!mark) return null;
  const runs = [];   // the runs of pieces carrying it
  n.forEach((child, offset) => {
    if (!child.marks.some((m) => isLink(m) && m.attrs.to === mark.attrs.to)) return;
    const from = start + offset, to = from + child.nodeSize, last = runs.at(-1);
    if (last && last[1] === from) last[1] = to; else runs.push([from, to]);
  });
  const run = runs.find(([a, b]) => a <= $from.pos && $from.pos <= b);
  return run ? { mark, run } : null;
}

export const context = {
  /** Where the cursor is, for the actions menu: the quote selected whole (`quote`: its attrs), the quote it's written in
   * through (`within`), the block of text it's in (`block`: id, whether it has text), a link, a span selected. */
  context() {
    const sel = this.view.state.selection;
    const whole = (t) => (sel instanceof NodeSelection && sel.node.type.name === t ? sel.node.attrs : null);
    let block = null, link = null, span = null;
    if (!(sel instanceof NodeSelection)) {
      const $from = sel.$from;
      for (let d = $from.depth; d > 0 && !block; d--) {
        const n = $from.node(d);
        if (n.type.name !== "text_block") continue;
        const start = $from.start(d), text = n.textBetween(0, n.content.size, undefined, "\n");
        const off = (pos) => pos - start;   // (an offset into its text: a line break is one, as the store's)
        const at = (from, end) => ({ id: n.attrs.id, own: n.attrs.own, at: [off(from), off(end)], from, end });
        block = { id: n.attrs.id, own: n.attrs.own, text: text.trim() !== "", para: n.attrs.para };
        if (!sel.empty && sel.$to.parent === n) span = { ...at(sel.from, sel.to), text };
        const l = linkAround(sel, n, start);
        if (l) link = { ...at(l.run[0], l.run[1]), to: l.mark.attrs.to, title: l.mark.attrs.title };
      }
    }
    return { quote: whole("quote"), expr: whole("expr"), within: this.holder ? this.holder.node.attrs : null, block, link, span, para: paraAt(this.view.state) };
  },

  /** ⌘O on expression `ev` (an ExprView): with one thing to open, that; with several, a word on going into it. */
  openRefs(ev) {
    const refs = ev?.refs() || [];
    if (refs.length === 1) this.open({ target: refs[0] });
    else if (ev?.items().length) { this.message = "→ into it: each one opens on its own"; this.status(); }
    return true;
  },

  /** Open it from inside a quote's editor: its source, as the pericope, at the cursor. Not a quote's editor: false. */
  openHere() {
    if (this.browse) return this.openRefs(this.holder);   // (in a value: what its expression refers to)
    if (!this.exit) return false;
    const { $from } = this.view.state.selection;
    let at = null, off = null;
    for (let d = $from.depth; d > 0 && !at; d--) { at = $from.node(d).attrs.id; if (at && $from.node(d).isTextblock && !this.lens) off = $from.pos - $from.start(d); }
    this.open({ target: this.id, at, off });
    return true;
  },

  /** Where a new quote at the cursor would go, for the core to draw it from there (GET /api/quote's `into`, `depth`):
   * the blocks around the cursor, by the ids the store knows them by, and the quotes around this. */
  quoteHere() {
    const ids = new Set([this.id]), { $from } = this.view.state.selection;
    for (let d = $from.depth; d > 0; d--) { const n = $from.node(d); if (n.attrs.id) ids.add(this.storeId(n.attrs)); }
    return `&into=${encodeURIComponent([...ids].join(","))}&depth=${this.around.length}`;
  },

  /** The block id the store knows a block of text by: its own (`own`: this editor's block itself), else its id. */
  storeId(b) { return b.own ? this.id : b.id; },
};
