// spot.js — where you are on a page, kept as you leave it and put back as you come back along the trail (⌘[, ⌘]), or
// after an action redraws it; and a block's box selected from a click on its tab.
import { NodeSelection, TextSelection } from "prosemirror-state";
import { BlockSelection, selectBlock, levelKey } from "./blocks.js";
import { currentEditor, setCurrent, editorsIn, views } from "./here.js";

/** What a block of text holds, its line breaks and holes too: alike, a place in one is the same place in the other. */
const holds = (n) => n.textBetween(0, n.content.size, "", (leaf) => `\u0000${leaf.type.name}`);

/** Where you are in `root`'s editors (the one you're in): the caret or text selected ({anchor, head}: each the block
 * of text it's in, how far in, and what that block holds), or blocks selected whole ({blocks: [first id, last id]});
 * `path`: the quotes (their ids) the editor it's in is inside, outermost first; `quiet`: nothing drawn yet. Null: none. */
export function spotOf(root) {
  const cur = currentEditor();
  const e = root && cur && !cur.gone && editorsIn(root).includes(cur) ? cur : null;
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

/** Spot `spot` (spotOf) put back in `root`'s editors, the one it was in (by the quotes it's inside), as it was: quiet
 * stays quiet. Not there as it was: left as the page opened. The editor it was put back in, or false. With `focus` off
 * (a menu open over it), the focus is left where it is: it's only the editor you're in. */
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

/** Spot `spot` (taken before an action) put back in `root` after the action redrew it, following its text where the
 * action moved it: as it was; or, its block a quote now (Turn into a quote), in the quote, in the block of text there
 * that holds what it held; or, the quote it was in text again (Turn into text), in that text. The editor, or false. */
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
