// plugins.js — an editor's ProseMirror state and the plugins it's made of: ids given, where you are drawn, a
// paraphrase's ↗ and guide, a block marked (motion.js), a masked quote's lens, an expression's value browsed.
import { EditorState, Plugin, PluginKey, NodeSelection, TextSelection } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";
import { keymap } from "prosemirror-keymap";
import { baseKeymap } from "prosemirror-commands";
import { history } from "prosemirror-history";
import { BlockSelection, blocksPlugin, selectBlock, levelKey } from "./blocks.js";
import { schema } from "./schema.js";
import { pmDoc, freshIds, pmLens } from "./draft.js";
import { slashMenu } from "./menu.js";
import { inlineCode } from "./inlinecode.js";
import { labelOf } from "./codebox.js";
import { clipboardPlugin } from "./clipboard.js";
import { editorKeys } from "./keymap.js";
import { exprGuard, exprItems } from "../expr/exprview.js";
import { quoteEl } from "../expr/views.js";
import { pressed } from "../lib/keys.js";
import { hereKey, currentEditor } from "./here.js";

export const markKey = new PluginKey("fw-mark");

/** A transaction giving ids where the document needs them (draft.freshIds), or null. A block split off one that was
 * its own block's text (`own`) is a block of its own. */
export function idsTr(state) {
  const found = [];
  state.doc.descendants((n, pos) => { found.push({ type: n.type.name, id: n.attrs.id, pos, node: n }); });
  const fresh = freshIds(found);
  if (!fresh.size) return null;
  const tr = state.tr;
  for (const [n, id] of fresh) {   // (a block split off another isn't its own text, nor a paraphrase: the store's mark stays on the first)
    const keep = found[n].type === "text_block" ? { own: false, para: null } : found[n].type === "container" ? { para: null } : {};
    tr.setNodeMarkup(found[n].pos, null, { ...found[n].node.attrs, id, ...keep });
  }
  return tr.setMeta("addToHistory", false);
}

/** A line a masked quote keeps as it is (the lens's rawline): a quote inside it drawn as any quote, read only, or the picture. */
export function keptView(node, open) {
  const d = node.attrs.data;
  let dom;
  if (d?.t === "quote") dom = quoteEl(d, open);
  else if (d?.t === "image" && d.file) { dom = document.createElement("div"); dom.className = "fw-image"; const img = document.createElement("img"); img.src = `/images/${d.file}`; dom.append(img); }
  else { dom = document.createElement("div"); dom.className = "fw-rawline"; dom.textContent = `❝ ${node.attrs.title}`; }
  dom.contentEditable = "false";
  return { dom, ignoreMutation: () => true, stopEvent: () => false };
}

const MARGIN = 60;   // px kept between the cursor and the screen's top and bottom (the status bar's there)
/** The cursor kept on screen (a big block isn't scrolled to as a whole): the text cursor scrolled just into view; a
 * block selected whole, left where it is if any of it shows, else its nearest edge in. True: ProseMirror's own
 * scrolling isn't wanted. */
export function keepInView(view) {
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

/** An expression's value, browsed: nothing changes its document but a new value (meta "fw-value"); typing, deleting,
 * pasting, cutting, undo, Turn into a quote refused. The arrows, selecting, copying, Esc and Open it work; the `code`
 * key shows the expression's code. No caret in it: a caret or span of text becomes its block, selected whole. */
const EDITS = new Set(["Backspace", "Delete", "Tab"]);   // (Enter: a level in, as anywhere at block level)
function browsing(ed) {
  return new Plugin({
    filterTransaction: (tr) => !tr.docChanged || !!tr.getMeta("fw-value"),
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

/** A paraphrase's ↗, as a quote's; not written yet, its source dim; Show its source, the same. */
function guide(ed) {
  const openEl = (para) => {
    const g = document.createElement("span");
    g.className = "fw-open";
    g.contentEditable = "false";
    g.textContent = "↗";
    g.title = "Open it";
    const name = document.createElement("span");   // (hovered: its name, grown out to the right, as every right-side tab)
    name.className = "fw-open-name";
    name.textContent = para.title || labelOf(para.id) || "";
    g.appendChild(name);
    g.addEventListener("mousedown", (e) => { e.preventDefault(); ed.open({ target: para.id, home: para.home }); });
    return g;
  };
  return new Plugin({ props: { decorations: (state) => {
    const out = [];
    state.doc.descendants((n, pos) => {
      const para = n.attrs?.para;
      if (!para) return;
      out.push(Decoration.widget(pos + 1, () => openEl(para), { side: -2, ignoreSelection: true, key: `o${n.attrs.id}${para.id}` }));
      const empty = n.type.name === "text_block" && n.content.size === 0;
      if (!empty && !ed.peeking.has(n.attrs.id)) return;
      const make = () => {
        const g = document.createElement(n.type.name === "text_block" ? "span" : "div");
        g.className = empty ? "fw-guide" : "fw-peek";
        g.textContent = para.text.slice(0, 600);
        return g;
      };
      out.push(Decoration.widget(pos + 1, make, { side: -1, ignoreSelection: true, key: `${empty ? "g" : "p"}${n.attrs.id}${para.text.length}` }));
    });
    return DecorationSet.create(state.doc, out);
  } } });
}

/** Where you are, drawn: only in the editor you're in (its state says: setCurrent, hush). One focus: either a caret,
 * editing, or blocks selected whole, never both. On one of an expression's items, the expression is drawn as here. */
function here(ed) {
  return new Plugin({
    key: hereKey,
    state: { init: () => ({ current: currentEditor() === ed, quiet: ed.quiet, item: null }),
             apply: (tr, was) => {
               const m = tr.getMeta(hereKey), item = tr.getMeta("fw-item");   // (item: ExprView.selectItem)
               const now = m ? { ...was, ...m } : was;
               if (item !== undefined) return { ...now, item };
               return tr.selectionSet && now.item != null ? { ...now, item: null } : now;
             } },
    props: {
      attributes: (state) => {
        const { current: mine, quiet } = hereKey.getState(state);
        if (!mine) return {};
        const selecting = quiet || state.selection instanceof NodeSelection || state.selection instanceof BlockSelection;
        return { class: [quiet ? "" : "fw-current", selecting ? "fw-selecting" : ""].filter(Boolean).join(" ") };
      },
      decorations: (state) => {
        const { current: mine, quiet, item } = hereKey.getState(state);
        if (!mine || quiet) return null;
        const sel = state.selection, { $from } = sel;
        const node = (from, to, cls) => DecorationSet.create(state.doc, [Decoration.node(from, to, { class: cls })]);
        if (sel instanceof NodeSelection) return node(sel.from, sel.to, item != null ? "fw-here" : "fw-chosen");
        if (sel instanceof BlockSelection) return DecorationSet.create(state.doc, sel.blocks().map(({ node: n, pos }) => Decoration.node(pos, pos + n.nodeSize, { class: "fw-chosen" })));
        for (let d = $from.depth; d > 0; d--) if ($from.node(d).type.name === "text_block") return node($from.before(d), $from.after(d), "fw-here");
        return null;
      },
    },
  });
}

/** A block marked with classes (mark(id, cls): the block a step between pericopes goes through, motion.js), given by
 * ProseMirror itself, which keeps them. */
const marking = () => new Plugin({
  key: markKey,
  state: { init: () => null, apply: (tr, was) => { const m = tr.getMeta(markKey); return m === undefined ? was : m; } },
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

/** Through a masked quote: only the shown text written; every hole, kept line and block stays. */
function lensState(ed) {
  const count = (doc) => { const n = { hole: 0, rawline: 0, text_block: 0 }; doc.descendants((x) => { if (x.type.name in n) n[x.type.name]++; }); return JSON.stringify(n); };
  const guard = new Plugin({ filterTransaction: (tr, state) => !tr.docChanged || count(tr.doc) === count(state.doc) });
  const lensKeys = keymap({ "Enter": (state, dispatch) => { if (dispatch) dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create())); return true; } });
  return EditorState.create({ doc: schema.nodeFromJSON(pmLens(ed.lens.segments, ed.lens.hole)),
    plugins: [lensKeys, inlineCode(ed), editorKeys(ed), keymap(baseKeymap), history(), guard, here(ed)] });
}

/** Editor `ed`'s state, holding `children` (the core's tree). */
export function stateFor(ed, children) {
  if (ed.lens) return lensState(ed);
  const ids = new Plugin({ appendTransaction: (trs, _, state) => (trs.some((t) => t.docChanged) ? idsTr(state) : null) });
  return EditorState.create({ doc: schema.nodeFromJSON(pmDoc(children)),
    plugins: [...(ed.browse ? [browsing(ed)] : []), slashMenu(ed, (at) => ed.enterQuote(at)), inlineCode(ed), exprItems(ed), exprGuard(),
      blocksPlugin(), clipboardPlugin(ed), editorKeys(ed), keymap(baseKeymap), history(), ids, here(ed), guide(ed), marking()] });
}
