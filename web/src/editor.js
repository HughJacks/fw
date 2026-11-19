// editor.js — one block open for writing: a pericope on the page, or what a quote shows when it's written
// through (edit-through, as the terminal's). Each has its own document, undo, autosave and base, and saves
// into its own block through the core (PUT /api/pericope/<id>: the terminal's commit). A quote that can be
// written through holds an editor of its own (QuoteView); one that can't (masked, locked, a picture, too
// deep) is drawn read only from what the core says it shows.
import { EditorState, Plugin, NodeSelection, TextSelection, Selection } from "prosemirror-state";
import { EditorView, Decoration, DecorationSet } from "prosemirror-view";
import { keymap } from "prosemirror-keymap";
import { baseKeymap, chainCommands, splitBlock, liftEmptyBlock } from "prosemirror-commands";
import { BlockSelection, blocksPlugin, selectAround, grow, removeSelected, removeEmpty, nestIn, selectBlock } from "./blocks.js";
import { history, undo, redo } from "prosemirror-history";
import { schema } from "./schema.js";
import { pmDoc, draftOf, freshIds, pmLens, lensOf } from "./draft.js";
import { quoteEl, drawBody } from "./views.js";

const SAVE_AFTER = TEST ? 30 : 400;   // ms after the last key: saved (the terminal's autosave; quicker in the tests)
const RETRY = TEST ? 150 : 1000;       // ms: a save the store refused, tried again
export const waiting = new Set();     // the editors with a save scheduled, not yet begun (the tests' "settled")

import { api, TEST } from "./api.js";
import { slashMenu } from "./menu.js";
import { clipboardPlugin } from "./clipboard.js";
import { keyOf } from "./keys.js";
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

const views = new WeakMap();   // a quote's DOM -> its QuoteView (to go into it from the keys)

// Where you are (the user, 2026-11-18): one editor at a time is the one you're in, and only its selection is drawn,
// the block its cursor is in (fw-here) or what it has selected whole (fw-chosen); its DOM is marked fw-current (so the
// quotes you're writing through, around it, show: app.css). Every other editor is at rest, whatever selection it
// last had. You stay in it while a menu or a question of the page has the focus, or the window loses it; you leave
// it for another editor, or for anything else on the page (the title, home's search).
let current = null;
/** Editor `ed` (or none) the one you're in; the one you were in and it drawn again. */
function setCurrent(ed) {
  if (current === ed) return;
  const was = current;
  current = ed;
  for (const e of [was, ed]) {
    if (!e || e.gone) continue;
    e.view.dom.classList.toggle("fw-current", e === current);
    e.view.dispatch(e.view.state.tr.setMeta("addToHistory", false));   // (its marks drawn again)
  }
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

export class BlockEditor {
  /** `host`: where it's drawn; `id`: the block it writes into; `children`: what it holds (the core's tree);
   * `base`: the content it was built on; `around`: the editors this one's inside (outermost last), whose
   * shown text a save here changes; `exit(dir)`: leave it (a quote's editor: -1 up, 1 down, 0 select it);
   * `open(target, at)`: Open it; `status()`: something changed worth saying. */
  constructor(host, { id, children, base, readOnly = false, around = [], exit = null, open, status = () => {}, act = () => false, holder = null, top = null, lens = null,
    fields = () => ({}), saved = () => {}, bottom = null, begin = null }) {
    // (bottom(): ↓ past the last line, home's search; begin(): no id yet (home's waiting pericope, 2026-11-19): its
    // pericope made in the background on the first change, a promise of the core's {id, base}; saves wait for it)
    // (top(): ↑ from the first line, the page's header; lens: {qid, segments, hole}, written through a masked quote;
    // fields(): what else goes with its next save, the header's (its title, when changed); saved(sent): a save done, what went with it)
    Object.assign(this, { id, base, readOnly, around, exit, open, status, act, holder, top, lens, fields, onSaved: saved, bottom, begin });
    this.making = null;   // (the pericope being made, begin()'s promise: until then nothing's written)   // (act: the Ctrl+/ menu's; holder: the QuoteView it's in)
    this.kids = new Set();       // the editors of the quotes in it
    this.peeking = new Set();    // the paraphrases whose source shows inside them (Show its source), this session
    this.saving = null;   // (a save in flight: a promise, settled when it's done)
    this.timer = null;
    this.message = "";
    this.view = new EditorView(host, {
      state: this.make(children),
      editable: () => !readOnly,
      handleScrollToSelection: (view) => keepInView(view),   // (the cursor kept on screen, never the whole block)
      nodeViews: { quote: (node, view, getPos) => new QuoteView(node, view, getPos, this), rawline: (node) => keptView(node, this.open) },
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
        if (tr.docChanged) {
          this.schedule();
          if (tr.getMeta("addToHistory") !== false) this.act(this, "changed");   // (what was undone can't be redone now)
        }
        this.status();
      },
    });
    this.giveIds();
    this.saved = this.draft();
    // (the one you're in: as the focus comes to it; left for anything but a menu or a question, or another window)
    this.view.dom.addEventListener("focus", () => setCurrent(this));
    this.view.dom.addEventListener("blur", (e) => {
      const to = e.relatedTarget;
      if (!to || to.closest?.(".fw-menu, .fw-ask, .ProseMirror")) return;
      if (current === this) setCurrent(null);
    });
  }

  make(children) {
    const ids = new Plugin({ appendTransaction: (trs, _, state) => (trs.some((t) => t.docChanged) ? idsTr(state) : null) });
    const guide = new Plugin({   // a paraphrase not written yet shows its source, dim; Show its source, the same
      props: {
        decorations: (state) => {
          const out = [];
          state.doc.descendants((n, pos) => {
            const para = n.attrs?.para;
            if (!para) return;
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
    const here = new Plugin({   // where you are, drawn: only in the editor you're in (setCurrent)
      props: {
        // (one focus, the user, 2026-11-18: either a caret, editing, or blocks selected whole, never both: selecting,
        // no caret shows)
        attributes: (state) => (current === this && (state.selection instanceof NodeSelection || state.selection instanceof BlockSelection)
          ? { class: "fw-selecting" } : {}),
        decorations: (state) => {
          if (current !== this) return null;
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
        plugins: [lensKeys, this.keys(), keymap(baseKeymap), history(), guard, here] });
    }
    const slash = slashMenu(this, (at) => this.enterQuote(at));
    return EditorState.create({ doc: schema.nodeFromJSON(pmDoc(children)),
      plugins: [slash, blocksPlugin(), clipboardPlugin(this), this.keys(), keymap(baseKeymap), history(), ids, here, guide] });
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
    return keymap({
      "Enter": chainCommands((state, dispatch) => {   // on blocks selected whole (a quote, a picture): a new block below them
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
      "ArrowDown": chainCommands(into("start"), out(1), edge(1)),
      "ArrowUp": chainCommands(into("end"), out(-1), edge(-1)),
      "ArrowLeft": side(-1),
      "ArrowRight": side(1),
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
      "Backspace": chainCommands(removeSelected, removeEmpty(-1)),
      "Delete": chainCommands(removeSelected, removeEmpty(1)),
      "Mod-Shift-v": () => {   // paste and match style: a plain copy of what was clipped, not live quotes
        this.staticPaste = true;
        setTimeout(() => { this.staticPaste = false; }, 1000);
        return false;   // (the browser pastes)
      },
      // the commands' keys: the user's, else the defaults (keys.js; the bindings page, #/keys)
      ...Object.fromEntries(["menu", "popout", "popopen", "detach", "lock", "mask", "showall", "delete", "link", "unlink"]
        .map((id) => [keyOf(id), () => this.act(this, id)])),
      [keyOf("nest")]: nestIn,
      [keyOf("open")]: (state) => {   // Open it: a quote selected whole; a link; in a quote's editor, its source at the cursor
        const q = quoteAt(state);
        if (q) { this.open(q.node.attrs.data || { target: q.node.attrs.target }); return true; }
        const link = this.context().link;
        if (link) { this.open({ target: link.to }); return true; }
        if (!this.exit) return false;
        const { $from } = state.selection;
        let at = null;
        for (let d = $from.depth; d > 0 && !at; d--) at = $from.node(d).attrs.id;
        this.open({ target: this.id, at });
        return true;
      },
    });
  }

  /** Where the cursor is, for the Ctrl+/ menu: the quote selected whole (`quote`: its node's attrs), the
   * quote it's written in through (`within`: that quote's attrs, if this is a quote's editor), and the block
   * of text it's in (`block`: id, whether it has text). */
  context() {
    const sel = this.view.state.selection;
    const quote = sel instanceof NodeSelection && sel.node.type.name === "quote" ? sel.node.attrs : null;
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
    return { quote, within: this.holder ? this.holder.node.attrs : null, block, link, span };
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
  }

  draft() {
    if (this.readOnly) return null;
    return this.lens ? lensOf(this.view.state.doc.toJSON(), this.lens.hole) : draftOf(this.view.state.doc.toJSON());
  }
  dirty() { return this.draft() !== this.saved; }
  /** Busy: unsaved, saving, or written in through a quote just now (then the store isn't followed here). */
  busy() {
    return this.dirty() || this.saving || !!document.querySelector(".fw-menu")   // (a menu's open: positions in use)
      || [...this.kids].some((k) => k.busy() || k.view.hasFocus());
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
    const body = this.lens ? { text: sent, base: this.base } : { draft, base: this.base, also: this.around.map((e) => e.id), ...extra };
    let r;
    try {
      r = await api(this.lens ? `/api/lens/${this.lens.qid}` : `/api/pericope/${this.id}`, { method: "PUT", body: JSON.stringify(body) });
    } finally {
      this.saving = null;
      done();
    }
    if (r.ok) {
      this.base = this.lens ? (r.body.bases || {})[this.id] || this.base : r.body.base;
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

  /** What it holds as the store now has it (nothing unsaved here): drawn again, the cursor kept near. */
  reload(children, base) {
    if (this.view.isDestroyed) return;   // (left meanwhile: nothing to draw into)
    window.fw && (window.fw.reloads = (window.fw.reloads || 0) + 1);   // (counted, for the tests' reports)
    // the cursor kept by the block it's in and how far into it (positions move when blocks before it change)
    const { $from } = this.view.state.selection;
    let keep = null;
    for (let d = $from.depth; d > 0 && !keep; d--) if ($from.node(d).attrs.id) keep = { id: $from.node(d).attrs.id, off: $from.pos - $from.start(d) };
    const at = this.view.state.selection.from;
    // (the quotes' editors are their views': ProseMirror keeps a view whose node is the same, and a view it
    // drops takes its editor with it, QuoteView.destroy)
    this.view.updateState(this.make(children));
    this.giveIds();
    this.base = base;
    this.saved = this.draft();
    let pos = Math.min(at, this.view.state.doc.content.size);
    if (keep) this.view.state.doc.descendants((n, p) => {
      if (n.attrs.id === keep.id && n.isTextblock) pos = Math.min(p + 1 + keep.off, p + 1 + n.content.size);
    });
    try { this.view.dispatch(this.view.state.tr.setSelection(Selection.near(this.view.state.doc.resolve(pos)))); } catch {}
  }

  /** Where the cursor goes, and the view (the user, 2026-11-18): at block `at` (its start, or it selected whole),
   * the cursor centered on the screen; else at the very start, the page from its top. */
  place(at = null) {
    const doc = this.view.state.doc;
    let start = null;
    if (at) doc.descendants((n, pos) => { if (start === null && n.attrs.id === at) start = pos; });
    const sel = start !== null
      ? (doc.nodeAt(start).isAtom ? NodeSelection.create(doc, start) : TextSelection.create(doc, start + 1))
      : Selection.atStart(doc);
    this.view.dispatch(this.view.state.tr.setSelection(sel));
    if (start === null) { window.scrollTo(0, 0); return; }
    try {   // the cursor centered on the screen (not the block: a big one would put the cursor off it)
      const { top } = this.view.coordsAtPos(this.view.state.selection.head);
      scrollBy(0, top - innerHeight / 2);
    } catch { this.view.nodeDOM(start)?.scrollIntoView?.({ block: "center" }); }
  }

  /** Ends with a quote or picture: a block to write in below it (dropped on save if nothing's written). */
  roomBelow() {
    const last = this.view.state.doc.lastChild;
    if (this.readOnly || !["quote", "image"].includes(last.type.name)) return;
    const end = this.view.state.doc.content.size;
    this.view.updateState(this.view.state.apply(this.view.state.tr.insert(end, schema.nodes.text_block.create()).setMeta("addToHistory", false)));
    this.giveIds();
    this.saved = this.draft();
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
    views.set(this.dom, this);
    if (data.tree || data.lens) {   // (written through: what it holds, or through its mask, the lens)
      const host = this.dom.querySelector(".fw-body");
      this.inner = new BlockEditor(host, {
        id: data.target, children: data.tree, base: data.base, around: [parent, ...parent.around],
        exit: (dir) => this.exit(dir), open: parent.open, status: parent.status, act: parent.act, holder: this,
        lens: data.lens ? { qid: data.id, segments: data.lens, hole: data.hole } : null,
      });
      parent.kids.add(this.inner);
      this.inner.view.dom.addEventListener("focus", () => this.dom.classList.add("fw-in"));
      this.inner.view.dom.addEventListener("blur", () => this.dom.classList.remove("fw-in"));
    }
  }

  /** Into it, at its start or its end. */
  enter(where) {
    const v = this.inner.view;
    v.focus();
    v.dispatch(v.state.tr.setSelection(where === "start" ? Selection.atStart(v.state.doc) : Selection.atEnd(v.state.doc)).scrollIntoView());
    return true;
  }

  /** Out of it: to the block before it (-1), after it (1), or it selected whole (0). */
  exit(dir) {
    const v = this.outer, pos = this.getPos(), doc = v.state.doc;
    // (the next thing that way: text, or a quote or picture selected whole; none in this editor: out of it too, a level
    // further, so the arrows flow on through quotes that end together)
    const near = dir < 0 ? Selection.findFrom(doc.resolve(pos), -1, false) : dir > 0 ? Selection.findFrom(doc.resolve(pos + this.node.nodeSize), 1, false) : null;
    if (!near && dir !== 0 && this.parent.exit) { this.parent.exit(dir); return; }
    v.focus();
    v.dispatch(v.state.tr.setSelection(near || NodeSelection.create(doc, pos)).scrollIntoView());
  }

  // (events inside it are its own, not the page's: its editor's, and masking's panel, whose keys and clicks the page
  // must never take: an arrow moving the page's selection, a click focusing the page and ending masking)
  stopEvent(e) { return !!((this.inner && this.inner.view.dom.contains(e.target)) || e.target.closest?.(".fw-masking")); }
  ignoreMutation() { return true; }
  selectNode() { this.dom.classList.add("ProseMirror-selectednode"); }
  deselectNode() { this.dom.classList.remove("ProseMirror-selectednode"); }
  update(node) {
    if (node.attrs.data !== this.node.attrs.data || node.attrs.target !== this.node.attrs.target) return false;
    this.node = node;   // (its id given since, say)
    return true;
  }
  destroy() {
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
  ed.view.dispatch(ed.view.state.tr.setSelection(selectBlock(ed.view.state.doc, at)));
  return true;
}
