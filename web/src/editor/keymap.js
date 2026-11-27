// keymap.js — an editor's keys: the arrows through blocks, quotes and levels, Enter, Esc, undo, and the commands' keys
// (lib/keys.js: the user's bindings, else the defaults).
import { NodeSelection, TextSelection, Selection } from "prosemirror-state";
import { keymap } from "prosemirror-keymap";
import { chainCommands, splitBlock, liftEmptyBlock } from "prosemirror-commands";
import { undo, redo } from "prosemirror-history";
import { BlockSelection, selectAround, grow, removeSelected, removeEmpty, joinOut, nestIn, atLevel } from "./blocks.js";
import { schema } from "./schema.js";
import { toggleCode } from "../expr/exprview.js";
import { keyOf } from "../lib/keys.js";
import { views, enterQuote, paraAt } from "./here.js";

const ACTS = ["menu", "popout", "popopen", "detach", "lock", "mask", "showall", "delete", "link", "unlink"];

/** Arrow commands: onto, into and out of quotes, and past an editor's edges. */
function arrows(ed) {
  const quoteAt = (state) => {   // the quote selected whole, and its view
    const n = state.selection instanceof NodeSelection ? state.selection.node : null;
    return n?.type.name === "quote" ? { node: n, qv: views.get(ed.view.nodeDOM(state.selection.from)) } : null;
  };
  return {
    quoteAt,
    into: (where) => (state) => { const q = quoteAt(state); return !!(q?.qv?.inner && q.qv.enter(where)); },   // the same arrow again, on a quote: into it
    onto: (dir) => (state, dispatch, view) => {   // ↑/↓ past a line's edge onto a quote: into it (Esc selects it whole)
      const sel = state.selection;
      if (!(sel instanceof TextSelection) || !sel.empty || !view.endOfTextblock(dir < 0 ? "up" : "down")) return false;
      const $p = state.doc.resolve(dir < 0 ? sel.$from.before(sel.$from.depth) : sel.$to.after(sel.$to.depth));
      return enterQuote(view, Selection.findFrom($p, dir, false), dir);
    },
    edge: (dir) => (state, dispatch, view) => {   // at a quote's editor's top or bottom: out of it; at the page's top, the header
      if (!ed.exit && !(dir < 0 && ed.top) && !(dir > 0 && ed.bottom)) return false;
      const sel = state.selection, whole = sel instanceof NodeSelection;
      const pos = dir < 0 ? (whole ? sel.from : sel.$from.before(sel.$from.depth)) : (whole ? sel.to : sel.$to.after(sel.$to.depth));
      // (anything before or after this block to go to; only past the last of them is the edge)
      const more = Selection.findFrom(state.doc.resolve(pos), dir, false);
      if (more || !(whole || view.endOfTextblock(dir < 0 ? "up" : "down"))) return false;
      if (ed.exit) ed.exit(dir); else if (dir < 0) ed.top(); else ed.bottom();
      return true;
    },
    below: (state) => {   // ↓ on the page's last picture, selected whole: a block below it to write in
      const sel = state.selection;
      return sel instanceof NodeSelection && sel.to === state.doc.content.size && ed.roomBelow();
    },
    out: (dir) => (state, dispatch) => {   // blocks selected whole (not one quote): the cursor into the first or last
      const sel = state.selection;
      if (!(sel instanceof BlockSelection)) return false;
      if (dispatch) dispatch(state.tr.setSelection(dir < 0 ? Selection.near(state.doc.resolve(sel.from + 1), 1) : Selection.near(state.doc.resolve(sel.to - 1), -1)));
      return true;
    },
    side: (dir) => (state, dispatch, view) => {   // ← at the very start, → at the very end: out too
      if (!ed.exit) return false;
      const sel = state.selection, end = dir < 0 ? Selection.atStart(state.doc) : Selection.atEnd(state.doc);
      if (!(sel.empty && sel.from === end.from && view.endOfTextblock(dir < 0 ? "left" : "right"))) return false;
      ed.exit(dir);
      return true;
    },
  };
}

/** Block level (blocks.js atLevel): ↑/↓ the block before or after at the same level, past the first or last a level
 * out; → (or Enter) a level in: a container's or quote's first block, and text, bottomed out, to writing (→ the caret at
 * its start, Enter at its end); ← out a level, and with nothing around it, to writing, the caret at its start. */
function levels(ed) {
  const levelIn = (where) => (state, dispatch) => {
    if (!atLevel(state)) return false;
    const pos = state.selection.from, n = state.doc.nodeAt(pos);
    if (n?.type.name === "quote") {
      const qv = views.get(ed.view.nodeDOM(pos)), inner = qv?.inner;
      if (!inner) return false;
      const d = inner.view.state.doc;
      if (qv.node.attrs.data?.expr || ed.browse) return qv.enter("start");
      if (d.childCount === 1 && d.firstChild.isTextblock) return qv.enter(where);
      inner.selectLevel(0);
      return true;
    }
    if (n?.type.name === "expr") { const ev = views.get(ed.view.nodeDOM(pos)); return !!ev?.inner && ev.enter("start"); }
    if (n?.isTextblock && ed.browse) return true;   // (a value's text: never written in)
    if (n?.isTextblock) { dispatch?.(state.tr.setSelection(TextSelection.create(state.doc, where === "start" ? pos + 1 : pos + n.nodeSize - 1)).scrollIntoView()); return true; }
    if (n && !n.isAtom && n.childCount) { ed.selectLevel(pos + 1); return true; }
    return false;
  };
  return {
    levelIn,
    levelMove: (dir) => (state) => atLevel(state) && ed.levelStep(state.selection.from, state.selection.to, dir),
    levelOut: (state) => atLevel(state) && ed.levelOut(),
    levelStart: (state, dispatch) => {   // (at the top level, nothing around it: the caret at its start)
      if (!atLevel(state)) return false;
      const doc = state.doc, pos = state.selection.from, n = doc.nodeAt(pos);
      if (n.type.name === "quote") { const qv = views.get(ed.view.nodeDOM(pos)); return !!(qv?.inner && qv.enter("start")); }
      if (n.isAtom || ed.browse) return ed.browse;   // (a picture: the caret beside it; a value: no caret)
      dispatch?.(state.tr.setSelection(Selection.near(doc.resolve(pos + 1), 1)).scrollIntoView());
      return true;
    },
  };
}

/** Enter on blocks selected whole (a quote, a picture): a new block below them. */
function newBelow(state, dispatch) {
  if (!(state.selection instanceof NodeSelection || state.selection instanceof BlockSelection)) return false;
  if (dispatch) {
    const after = state.selection.to;
    const tr = state.tr.insert(after, schema.nodes.text_block.create());
    dispatch(tr.setSelection(TextSelection.create(tr.doc, after + 1)).scrollIntoView());
  }
  return true;
}

/** Esc: the block you're in selected whole; again, the one around it; in a quote's editor, at its top, the quote (a
 * quote showing one block: that block's box is the quote's, so the quote itself). */
const escape = (ed) => (state, dispatch) => {
  const whole = state.selection instanceof NodeSelection || state.selection instanceof BlockSelection;
  if (ed.exit && whole && state.selection.$from.depth === 0) { ed.exit(0); return true; }
  const doc = state.doc;
  if (ed.exit && !whole && doc.childCount === 1 && doc.firstChild.type.name === "text_block") { ed.exit(0); return true; }
  return selectAround(state, dispatch);
};

/** Open it: a quote selected whole; an expression's references; a link; a paraphrase's source; in a quote's editor,
 * its source at the cursor. */
const openIt = (ed, quoteAt) => (state) => {
  const q = quoteAt(state);
  if (q) { ed.open({ ...(q.node.attrs.data || { target: q.node.attrs.target }), whole: true }); return true; }   // (selected whole: arrives quiet)
  const sel = state.selection;
  if (sel instanceof NodeSelection && sel.node.type.name === "expr") return ed.openRefs(ed.view.nodeDOM(sel.from)?.fwExpr);
  const link = ed.context().link;
  if (link) { ed.open({ target: link.to }); return true; }
  const para = paraAt(state);
  if (para) { ed.open({ target: para.id, home: para.home }); return true; }
  return ed.openHere();
};

/** Editor `ed`'s keymap. */
export function editorKeys(ed) {
  const { quoteAt, into, onto, edge, below, out, side } = arrows(ed);
  const { levelIn, levelMove, levelOut, levelStart } = levels(ed);
  const act = (id) => () => ed.act(ed, id);
  return keymap({
    "Enter": chainCommands(levelIn("end"), newBelow, liftEmptyBlock, splitBlock),   // (an empty block inside a container: out a level)
    "Shift-Enter": (state, dispatch) => {
      if (dispatch) dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create()).scrollIntoView());
      return true;
    },
    // undo: what's typed first, then the store actions taken before it (actions.js); redo the same way back
    "Mod-z": chainCommands(undo, act("undo")),
    "Mod-y": chainCommands(redo, act("redo")),
    "Mod-Shift-z": chainCommands(redo, act("redo")),
    "ArrowDown": chainCommands(levelMove(1), into("start"), onto(1), out(1), edge(1), below),
    "ArrowUp": chainCommands(levelMove(-1), into("end"), onto(-1), out(-1), edge(-1)),
    "ArrowLeft": chainCommands(levelOut, levelStart, side(-1)),
    "ArrowRight": chainCommands(levelIn("start"), side(1)),
    "Escape": escape(ed),
    "Shift-ArrowUp": grow(-1),
    "Shift-ArrowDown": grow(1),
    "Backspace": chainCommands(removeSelected, joinOut(-1), removeEmpty(-1)),
    "Delete": chainCommands(removeSelected, joinOut(1), removeEmpty(1)),
    // (with ⌘ or ⌥ still held from ⌘↵, the same at a block's edge; elsewhere the browser's word and line deletes)
    "Mod-Backspace": joinOut(-1), "Alt-Backspace": joinOut(-1), "Mod-Delete": joinOut(1), "Alt-Delete": joinOut(1),
    "Mod-Shift-v": () => {   // paste and match style: a plain copy of what was clipped, not live quotes
      ed.staticPaste = true;
      setTimeout(() => { ed.staticPaste = false; }, 1000);
      return false;   // (the browser pastes)
    },
    ...Object.fromEntries(ACTS.map((id) => [keyOf(id), act(id)])),
    [keyOf("nest")]: nestIn,
    [keyOf("code")]: (state, dispatch, view) => toggleCode(view),
    [keyOf("open")]: openIt(ed, quoteAt),
  });
}
