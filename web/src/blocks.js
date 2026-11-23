// blocks.js — blocks selected whole (the terminal's fw_blocks): Esc selects the block you're in (again: the
// block around it), Shift+↑/↓ grows the selection a block at a time, a click on a block's number in the gutter
// selects it; selected, they're drawn bright, and Backspace or Delete removes them, typing replaces them with a
// new block holding what's typed, Enter puts a new block below. An empty block of text goes with one Backspace
// (or Delete) instead of the cursor moving onto what's beside it.
import { Selection, SelectionRange, TextSelection, NodeSelection, Plugin, PluginKey } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";
import { schema } from "./schema.js";
import { Fragment } from "prosemirror-model";

// Block level (the user, 2026-11-19, later: "if we have a block selected, up and down arrow should navigate at block
// selection level"): blocks selected deliberately (Esc, a click on a tab or a number, Shift+↑/↓, and moving at block
// level) are at block level, where ↑/↓ go from block to block (editor.js). A quote only arrowed onto from text isn't:
// the same arrow goes on into it. Any other change of the selection leaves block level.
export const levelKey = new PluginKey("fw-level");
/** Blocks selected whole at block level. */
export const atLevel = (state) => !!levelKey.getState(state) && (state.selection instanceof BlockSelection || state.selection instanceof NodeSelection);

/** A run of whole blocks, siblings in one parent: from the start of the first to the end of the last. */
export class BlockSelection extends Selection {
  constructor($anchor, $head = $anchor) {
    const [$from, $to] = $anchor.pos <= $head.pos ? [$anchor, $head] : [$head, $anchor];
    super($anchor, $head, [new SelectionRange($from, $to)]);
  }
  get visible() { return false; }   // (drawn as the blocks' boxes, not as text selected)
  map(doc, mapping) {
    const a = mapping.map(this.anchor), h = mapping.map(this.head);
    if (a === h) return Selection.near(doc.resolve(a));
    return new BlockSelection(doc.resolve(a), doc.resolve(h));
  }
  eq(other) { return other instanceof BlockSelection && other.anchor === this.anchor && other.head === this.head; }
  toJSON() { return { type: "blocks", anchor: this.anchor, head: this.head }; }
  static fromJSON(doc, json) { return new BlockSelection(doc.resolve(json.anchor), doc.resolve(json.head)); }
  /** The blocks it covers: [{node, pos}]. */
  blocks() {
    const out = [], parent = this.$from.parent, start = this.$from.start();
    parent.forEach((node, offset) => {
      const pos = start + offset;
      if (pos >= this.from && pos + node.nodeSize <= this.to) out.push({ node, pos });
    });
    return out;
  }
}
Selection.jsonID("blocks", BlockSelection);

/** Block `pos` (a block's start) selected whole: an atom (a quote, a picture) as ProseMirror selects one, any
 * other as a BlockSelection. */
export function selectBlock(doc, pos) {
  const node = doc.nodeAt(pos);
  if (node.isAtom) return NodeSelection.create(doc, pos);
  return new BlockSelection(doc.resolve(pos), doc.resolve(pos + node.nodeSize));
}

/** The block the cursor's in, as [pos, node] at depth `d` (the innermost by default). */
function blockAround($pos, outer = 0) {
  for (let d = $pos.depth; d > 0; d--) {
    if ($pos.node(d).isBlock && (outer-- === 0)) return { pos: $pos.before(d), node: $pos.node(d) };
  }
  return null;
}

/** Esc: the block you're in selected whole; with blocks selected, the block around them (a container). */
export function selectAround(state, dispatch) {
  const sel = state.selection;
  let target = null;
  if (sel instanceof BlockSelection || sel instanceof NodeSelection) {
    const $from = sel.$from;
    if ($from.depth > 0) target = $from.before($from.depth);   // (the container holding them)
    else if (!levelKey.getState(state)) {   // (at the top, selected but not at block level, a page opened on a quote say: now it is)
      if (dispatch) dispatch(state.tr.setMeta(levelKey, true));
      return true;
    }
  } else {
    const b = blockAround(sel.$from);
    if (b) target = b.pos;
  }
  if (target === null) return false;
  if (dispatch) dispatch(state.tr.setSelection(selectBlock(state.doc, target)).setMeta(levelKey, true).scrollIntoView());
  return true;
}

/** Shift+↑/↓ with blocks selected whole: one more (or one fewer), siblings in the same parent. */
export function grow(dir) {
  return (state, dispatch) => {
    const sel = state.selection;
    if (!(sel instanceof BlockSelection || (sel instanceof NodeSelection && sel.node.isBlock))) return false;
    const $anchor = sel instanceof BlockSelection ? sel.$anchor : (dir > 0 ? state.doc.resolve(sel.from) : state.doc.resolve(sel.to));
    let head = sel instanceof BlockSelection ? sel.head : (dir > 0 ? sel.to : sel.from);
    const $head = state.doc.resolve(head);
    if (dir > 0) {
      const next = $head.nodeAfter;
      if (!next || $head.depth !== $anchor.depth) return true;
      head += next.nodeSize;
    } else {
      const prev = $head.nodeBefore;
      if (!prev || $head.depth !== $anchor.depth) return true;
      head -= prev.nodeSize;
    }
    if (head === $anchor.pos) return true;
    if (dispatch) dispatch(state.tr.setSelection(new BlockSelection($anchor, state.doc.resolve(head))).setMeta(levelKey, true).scrollIntoView());
    return true;
  };
}

/** Blocks selected whole, removed (and the cursor where they were); `replace`: a new block in their place. */
function removeBlocks(state, dispatch, replace = null) {
  const sel = state.selection;
  const whole = sel instanceof BlockSelection || (sel instanceof NodeSelection && sel.node.isBlock);
  if (!whole) return false;
  if (!dispatch) return true;
  const tr = state.tr;
  const parent = sel.$from.parent;
  const from = sel.from;
  tr.delete(sel.from, sel.to);
  const left = tr.doc.resolve(from).parent;
  if (replace || left.childCount === 0 || (parent === state.doc && tr.doc.childCount === 0)) {   // (nothing left in it: a block to write in)
    tr.insert(from, replace || schema.nodes.text_block.create());
    tr.setSelection(TextSelection.create(tr.doc, from + 1 + (replace ? replace.content.size : 0)));
  } else {
    tr.setSelection(Selection.near(tr.doc.resolve(Math.min(from, tr.doc.content.size)), 1));
  }
  dispatch(tr.scrollIntoView());
  return true;
}

export const removeSelected = (state, dispatch) => removeBlocks(state, dispatch);

/** Backspace (dir -1) or Delete (1) in an empty block of text: the block goes, the cursor to the end of the
 * one before (the start of the one after); a quote or picture there is selected whole. */
export function removeEmpty(dir) {
  return (state, dispatch) => {
    const sel = state.selection;
    if (!sel.empty || !(sel instanceof TextSelection)) return false;
    const $from = sel.$from, block = $from.parent;
    if (block.type.name !== "text_block" || block.content.size !== 0) return false;
    const pos = $from.before(), end = pos + block.nodeSize;
    const $pos = state.doc.resolve(pos);
    const beside = dir < 0 ? $pos.nodeBefore : state.doc.resolve(end).nodeAfter;
    if (!beside) return false;   // (nothing beside it in its parent: as ever)
    if (!dispatch) return true;
    const tr = state.tr.delete(pos, end);
    const at = dir < 0 ? pos - beside.nodeSize : pos;   // (where the block beside it starts now)
    tr.setSelection(beside.isAtom ? NodeSelection.create(tr.doc, at)
      : Selection.near(tr.doc.resolve(dir < 0 ? pos - 1 : pos + 1), dir < 0 ? -1 : 1));
    dispatch(tr.scrollIntoView());
    return true;
  };
}

/** Backspace at the start of a container's second block (dir -1), or Delete at the end of its first (1), when it holds
 * just those two blocks of text: ⌘↵ taken back (the user, 2026-11-23: "after deleting the command enter we should
 * return to the same parent structure"). The two joined into one block of text in the container's place, with the
 * container's id (the block ⌘↵ split), the cursor where they meet; so ⌘↵ then ⌫, again and again, never nests deeper.
 * Not a paraphrase's (Enter grows one). */
export function joinOut(dir) {
  return (state, dispatch) => {
    const sel = state.selection;
    if (!sel.empty || !(sel instanceof TextSelection)) return false;
    const $at = sel.$from, block = $at.parent;
    if (block.type.name !== "text_block" || $at.depth < 2) return false;
    const box = $at.node(-1), n = $at.index(-1);
    if (box.type.name !== "container" || box.attrs.para || box.childCount !== 2) return false;
    if (dir < 0 ? n !== 1 || $at.parentOffset !== 0 : n !== 0 || $at.parentOffset !== block.content.size) return false;
    const [a, b] = [box.child(0), box.child(1)];
    if (a.type.name !== "text_block" || b.type.name !== "text_block" || a.attrs.para || b.attrs.para) return false;
    if (!dispatch) return true;
    const pos = $at.before(-1);
    const one = schema.nodes.text_block.create({ id: box.attrs.id }, a.content.append(b.content));
    const tr = state.tr.replaceWith(pos, pos + box.nodeSize, one);
    dispatch(tr.setSelection(TextSelection.create(tr.doc, pos + 1 + a.content.size)).scrollIntoView());
    return true;
  };
}

/** The plugin: blocks selected whole drawn bright; typing over them replaces them with a new block holding it;
 * a click on a block's number in the gutter selects it. */
export function blocksPlugin() {
  let view = null;
  return new Plugin({
    key: levelKey,
    view: (v) => { view = v; return {}; },
    // A quote or picture selected whole with nowhere for a caret at either end (after another, or the page's last, say):
    // Chrome moves the browser's selection to the page's first letter on the next key, and ProseMirror read that back,
    // so the next ↓ (or anything typed) went to the page's start (2026-11-19, later). That read is refused, and the
    // browser's selection put back where it is.
    filterTransaction(tr, state) {
      if (tr.docChanged || !tr.selectionSet || tr.getMeta("pointer") || tr.getMeta(levelKey) !== undefined) return true;
      const was = state.selection, now = tr.selection;
      if (!(was instanceof NodeSelection && was.node.isAtom) || !(now instanceof TextSelection) || !now.empty) return true;
      const stranded = (n) => !n || n.isAtom;
      if (now.from !== Selection.atStart(tr.doc).from || !stranded(was.$from.nodeBefore) || !stranded(was.$to.nodeAfter)) return true;
      queueMicrotask(() => { if (view && !view.isDestroyed && view.hasFocus()) view.focus(); });
      return false;
    },
    state: {   // (at block level: set by what selects deliberately; any other change of the selection leaves it)
      init: () => false,
      apply: (tr, was, old) => { const m = tr.getMeta(levelKey); return m !== undefined ? m : tr.selectionSet && !tr.selection.eq(old.selection) ? false : was; },
    },
    props: {

      decorations(state) {
        const sel = state.selection;
        if (!(sel instanceof BlockSelection)) return null;
        return DecorationSet.create(state.doc, sel.blocks().map(({ node, pos }) => Decoration.node(pos, pos + node.nodeSize, { class: "fw-picked" })));
      },
      handleTextInput(view, from, to, text) {
        const sel = view.state.selection;
        if (!(sel instanceof BlockSelection)) return false;
        return removeBlocks(view.state, view.dispatch, schema.nodes.text_block.create(null, schema.text(text)));
      },
      handleDOMEvents: {
        mousedown(view, e) {   // the gutter: left of a block's box, where its number is
          // (the gutter: anywhere left of a block's box, level with it: its number, or the frame's padding beside it)
          const top = e.target.closest?.(".fw-doc > .ProseMirror > *")
            || [...view.dom.children].find((c) => { const r = c.getBoundingClientRect(); return e.clientY >= r.top && e.clientY < r.bottom; });
          if (!top || e.clientX >= top.getBoundingClientRect().left) return false;
          let pos = null;
          view.state.doc.forEach((node, offset) => { if (pos === null && view.nodeDOM(offset) === top) pos = offset; });
          if (pos === null) return false;
          e.preventDefault();
          view.focus();
          view.dispatch(view.state.tr.setSelection(selectBlock(view.state.doc, pos)).setMeta(levelKey, true));
          return true;
        },
      },
    },
  });
}

/** Ctrl+Enter: a block inside the block (the terminal's nest_in): the block of text you're in becomes a
 * container (keeping its id, so its box), holding its text before the cursor, then a new block with the rest,
 * where the cursor goes. Not on a block that's its editor's own text (a quote of a block of text). */
export function nestIn(state, dispatch) {
  const sel = state.selection;
  if (!(sel instanceof TextSelection)) return false;
  const $from = sel.$from, block = $from.parent;
  if (block.type.name !== "text_block" || block.attrs.own) return false;
  if (!dispatch) return true;
  const off = $from.parentOffset;
  const head = schema.nodes.text_block.create(null, block.content.cut(0, off));
  const tail = schema.nodes.text_block.create(null, block.content.cut(off));
  const box = schema.nodes.container.create({ id: block.attrs.id }, [head, tail]);
  const pos = $from.before();
  const tr = state.tr.replaceWith(pos, pos + block.nodeSize, box);
  tr.setSelection(TextSelection.create(tr.doc, pos + 1 + head.nodeSize + 1));
  dispatch(tr.scrollIntoView());
  return true;
}

/** A selection inside one block of text split out to a block of its own (for Turn into a quote on a selection,
 * the terminal's): the block becomes a container (keeping its id, so its box) holding the text before, the
 * selection, and the text after (each only if there is some); a block that's its editor's own text splits into
 * siblings instead. Returns a transaction and the selection's new block's id (given now: it's saved before the
 * store moves it out), or null. */
export function splitSelection(state, newId) {
  const sel = state.selection;
  if (!(sel instanceof TextSelection) || sel.empty || sel.$from.parent !== sel.$to.parent) return null;
  const block = sel.$from.parent;
  if (block.type.name !== "text_block") return null;
  const a = sel.$from.parentOffset, b = sel.$to.parentOffset, id = newId();
  const parts = [block.content.cut(0, a), block.content.cut(a, b), block.content.cut(b)];
  const kids = parts.map((c, n) => (n === 1 ? schema.nodes.text_block.create({ id }, c) : c.size ? schema.nodes.text_block.create(null, c) : null)).filter(Boolean);
  const pos = sel.$from.before();
  const tr = state.tr.replaceWith(pos, pos + block.nodeSize,
    block.attrs.own ? Fragment.fromArray(kids) : schema.nodes.container.create({ id: block.attrs.id }, kids));
  // (the selection kept on what was selected, its block of its own now: it stays selected through the pop out)
  const mid = pos + (block.attrs.own ? 0 : 1) + (parts[0].size ? kids[0].nodeSize : 0) + 1;
  tr.setSelection(TextSelection.create(tr.doc, mid, mid + (b - a)));
  return { tr, id };
}
