// inlinecode.js — inline expressions in a line (TYPE.md "Inline"): `$source$` written in the text itself, marked as
// code (schema's `icode` mark, one key per expression so two side by side stay two). Typed like any text, the caret
// moving through it as through words (the user, 2026-11-25: "insert 2 green dollar signs in the text and we type
// between them … we should be able to cursor out of the dollar signs like normal"): with the caret between its
// dollar signs, its code shows, mono, coloured as code, the dollar signs green, references drawn as their titles;
// with the caret anywhere else, its code is folded away and its value shows, mono and green, live (worked out where
// its block sits: this, above, below). ← from just after one, or → from just before, steps in; ⌫ just after one (⌦
// just before) takes it whole; left empty, it goes. The store never changes shape: it's text.
import { Plugin, PluginKey, TextSelection } from "prosemirror-state";
import { Fragment, Slice } from "prosemirror-model";
import { Decoration, DecorationSet } from "prosemirror-view";
import { schema } from "./schema.js";
import * as hazel from "./hazel.js";
import { onSnapshot } from "./snapshot.svelte.js";
import { inlineValueEl, namesOf, hereOf } from "./views.js";
import { labelOf } from "./codebox.js";
import { units, newCodeKey } from "./draft.js";
import { pressed } from "./keys.js";

export const icodeKey = new PluginKey("icode");

/** Every inline expression in `doc`: {from, to, source, key, block} (from: its opening $, to: just past its closing). */
export function codeRuns(doc) {
  const out = [];
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true;
    let at = pos + 1, run = null;
    node.forEach((child) => {
      const m = child.isText && child.marks.find((x) => x.type.name === "icode");
      if (m && run && run.key === m.attrs.key && run.to === at) { run.to += child.nodeSize; run.text += child.text; }
      else if (m) { run = { from: at, to: at + child.nodeSize, key: m.attrs.key, text: child.text, block: node.attrs.id || "" }; out.push(run); }
      else run = null;
      at += child.nodeSize;
    });
    return false;
  });
  for (const r of out) r.source = /^\$[\s\S]*\$$/.test(r.text) && r.text.length >= 2 ? r.text.slice(1, -1) : null;
  return out;
}

const runAt = (state, test) => codeRuns(state.doc).find(test);
/** The run that's open (its code showing), if any: opened by a key (⌘⇧X) or by typing it (`$`), never by the caret
 * just passing through (the user, 2026-11-25: "just cursoring into a $$ span shouldn't open it"); open while the
 * caret stays between its dollar signs. */
const openRun = (state) => {
  const key = icodeKey.getState(state), { head, empty } = state.selection;
  return key && empty ? runAt(state, (r) => r.key === key && r.from < head && head < r.to) : null;
};

// --- its code, coloured (as the code box colours Hazel) --------------------------------------------------------------
const KEYWORDS = new Set(["let", "in", "fun", "if", "then", "else", "case", "end", "type", "test", "rec", "and"]);
const RELATIVE = new Set(["this", "here", "self", "above", "below"]);
const TOKENS = /(#[^#\n]*#?)|("(?:[^"\\]|\\.)*"?)|(@[0-9]{8}T[0-9]{6}-[0-9a-f]{4})|([0-9]+(?:\.[0-9]*)?)|([A-Za-z_][A-Za-z0-9_']*)|(->|=>|\+\+|::|==|!=|<=|>=|&&|\|\||[-+*/<>=|!.,:;()[\]{}])/g;
function tokens(src) {
  const out = [];
  for (const m of src.matchAll(TOKENS)) {
    const [text] = m, at = m.index;
    const kind = m[1] ? "comment" : m[2] ? "string" : m[3] ? "ref" : m[4] ? "number"
      : m[5] ? (KEYWORDS.has(text) ? "keyword" : ["true", "false"].includes(text) ? "number" : RELATIVE.has(text) ? "relative" : /^[A-Z]/.test(text) ? "type" : null)
      : "operator";
    if (kind) out.push({ at, len: text.length, kind, text });
  }
  return out;
}

const refChip = (id, names) => () => {
  const s = document.createElement("span");
  s.className = names.has(id) ? "fw-tok-relative" : "fw-iref";
  s.textContent = names.get(id) ?? labelOf(id) ?? "?";
  s.title = `@${id}`;
  return s;
};

function decorations(state, editor) {
  const open = openRun(state), decos = [];
  for (const r of codeRuns(state.doc)) {
    if (r.source === null) continue;
    if (open && open.key === r.key) {
      decos.push(Decoration.inline(r.from, r.to, { class: "fw-icode-src" }));
      decos.push(Decoration.inline(r.from, r.from + 1, { class: "fw-icode-dollar" }), Decoration.inline(r.to - 1, r.to, { class: "fw-icode-dollar" }));
      const names = namesOf(editor, r.block);
      for (const k of tokens(r.source)) {
        const a = r.from + 1 + k.at, b = a + k.len;
        if (k.kind === "ref") {   // (its id folded away, its title in its place: the caret steps over it whole, handleKeyDown)
          decos.push(Decoration.inline(a, b, { class: "fw-icode-folded" }));
          decos.push(Decoration.widget(b, refChip(k.text.slice(1), names), { side: -1, key: `r:${k.text}:${names.get(k.text.slice(1)) ?? ""}:${version}` }));
        }
        else decos.push(Decoration.inline(a, b, { class: `fw-tok-${k.kind}` }));
      }
    } else {
      // (its code folded away, its value in its place; its closing $ kept, but taking no room, so the caret just after it
      // is drawn just after the value, never lost in folded text)
      decos.push(Decoration.inline(r.from, r.to - 1, { class: "fw-icode-folded" }), Decoration.inline(r.to - 1, r.to, { class: "fw-icode-tail" }));
      // (selected, the caret's middle stop over it: lit, the caret hidden; the user, 2026-11-25: "the caret should go
      // before the expression, no selected state; it can go in the expression and disappear but with selected state")
      const sel = isSelected(state, r);
      const value = () => {
        const el = inlineValueEl(hazel.run(r.source, r.block, hereOf(editor)), editor?.open, namesOf(editor, r.block));
        if (sel) el.classList.add("fw-icode-sel");
        if (BARE.test(r.source)) el.classList.add("fw-bare");   // (a bare reference computes nothing: no ƒ, the user, 2026-11-25)
        el.addEventListener("mousedown", (e) => {   // (a click on it: selected, the middle stop; a reference in it opens)
          if (e.target.closest?.(".fw-ref")) return;
          e.preventDefault();
          const v = editor.view, now = runAt(v.state, (x) => x.key === r.key);
          if (now) v.dispatch(selectRun(v.state, now));
          v.focus();
        });
        return el;
      };
      // (drawn at its start, before its folded code: a line ending in one still ends in text, so ProseMirror adds no
      // break after it, no empty line below, the user, 2026-11-25)
      decos.push(Decoration.widget(r.from, value, { side: 1, ignoreSelection: true, key: `v:${r.key}:${r.source}:${r.block}:${hazel.status()}:${version}:${sel}` }));
    }
  }
  return DecorationSet.create(state.doc, decos);
}

let version = 0;   // (the snapshot's: a value drawn again when anything it could read changes)
const BARE = /^\s*@[0-9]{8}T[0-9]{6}-[0-9a-f]{4}\s*$/;   // (code that's just a reference: @x, a mention)

/** Whether run `r` is selected, just it: the stop between before it and after it. */
const isSelected = (state, r) => !state.selection.empty && state.selection.from === r.from && state.selection.to === r.to;
const selectRun = (state, r) => state.tr.setSelection(TextSelection.create(state.doc, r.from, r.to));

/** A new inline expression's mark. */
export const codeMark = () => schema.marks.icode.create({ key: newCodeKey() });

/** ⌘⇧X: the inline expression the caret's against opened (the caret just before its closing $), or the open one
 * closed (the caret just after it): true when there was one. */
export function enterCode(view) {
  const s = view.state, { head, empty } = s.selection;
  const chosen = codeRuns(s.doc).find((x) => x.source !== null && isSelected(s, x));
  if (chosen) { view.dispatch(s.tr.setSelection(TextSelection.create(s.doc, chosen.to - 1)).setMeta(icodeKey, { open: chosen.key })); return true; }
  if (!empty) return false;
  const open = openRun(s);
  if (open) { view.dispatch(s.tr.setSelection(TextSelection.create(s.doc, open.to)).setMeta(icodeKey, { open: null })); return true; }
  const r = runAt(s, (x) => x.source !== null && (x.to === head || x.from === head));
  if (!r) return false;
  view.dispatch(s.tr.setSelection(TextSelection.create(s.doc, r.to - 1)).setMeta(icodeKey, { open: r.key }));
  return true;
}

export function inlineCode(editor) {
  return new Plugin({
    key: icodeKey,
    state: {   // (the open run's key, or null; it closes as the caret leaves it)
      init: () => null,
      apply(tr, key, _, state) {
        const meta = tr.getMeta(icodeKey);
        if (meta && typeof meta === "object" && "open" in meta) return meta.open;
        if (!key) return null;
        const { head, empty } = state.selection;
        return empty && codeRuns(state.doc).some((r) => r.key === key && r.from < head && head < r.to) ? key : null;
      },
    },
    props: {
      decorations: (state) => decorations(state, editor),
      handleKeyDown(view, e) {
        const s = view.state, { head, empty } = s.selection;
        if (pressed(e, "open")) {   // (⌘O on one selected: what its value is, a reference's pericope; never what its code reads)
          const r = codeRuns(s.doc).find((x) => x.source !== null && isSelected(s, x));
          if (!r) return false;
          const chip = view.dom.querySelector(".fw-icode-sel .fw-ref");
          const id = chip?.title.match(/^@([0-9]{8}T[0-9]{6}-[0-9a-f]{4})/)?.[1];
          if (id) editor.open({ target: id });
          return true;
        }
        if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return false;
        const runs = codeRuns(s.doc).filter((r) => r.source !== null);
        const set = (pos) => { view.dispatch(s.tr.setSelection(TextSelection.create(s.doc, pos)).scrollIntoView()); return true; };
        const chosen = runs.find((r) => isSelected(s, r));
        if (chosen) {   // (selected: → after it, ← before it; ↑/↓ a line from there, as from a caret, never still selected)
          if (e.key === "ArrowRight") return set(chosen.to);
          if (e.key === "ArrowLeft") return set(chosen.from);
          if (e.key === "ArrowUp" || e.key === "ArrowDown") { set(e.key === "ArrowUp" ? chosen.from : chosen.to); return false; }
          return false;   // (⌫ takes it, typing replaces it, as with any selection)
        }
        if (!empty) return false;
        const open = openRun(s);
        if (open) {   // (a reference in its code: one piece)
          const refs = tokens(open.source).filter((k) => k.kind === "ref").map((k) => ({ from: open.from + 1 + k.at, to: open.from + 1 + k.at + k.len }));
          const end = refs.find((x) => x.to === head), start = refs.find((x) => x.from === head);
          if (e.key === "ArrowLeft" && end) return set(end.from);
          if (e.key === "ArrowRight" && start) return set(start.to);
          if (e.key === "Backspace" && end) { view.dispatch(s.tr.delete(end.from, end.to)); return true; }
          if (e.key === "Delete" && start) { view.dispatch(s.tr.delete(start.from, start.to)); return true; }
        }
        if (e.key === "Escape" && open) { view.dispatch(s.tr.setSelection(TextSelection.create(s.doc, open.to)).setMeta(icodeKey, { open: null })); return true; }
        const choose = (r) => { view.dispatch(selectRun(s, r).scrollIntoView()); return true; };
        if (e.key === "ArrowLeft") { const r = runs.find((x) => x.to === head && x.key !== open?.key); if (r) return choose(r); }   // (onto it, closed: selected)
        if (e.key === "ArrowRight") { const r = runs.find((x) => x.from === head && x.key !== open?.key); if (r) return choose(r); }
        if (e.key === "Backspace") { const r = runs.find((x) => x.to === head); if (r) { view.dispatch(s.tr.delete(r.from, r.to)); return true; } }
        if (e.key === "Delete") { const r = runs.find((x) => x.from === head); if (r) { view.dispatch(s.tr.delete(r.from, r.to)); return true; } }
        return false;
      },
      // (pasted text read as written: its $…$ code, its \$ dollar signs)
      transformPastedText: (text) => text,
      transformPasted(slice) {
        const fix = (frag) => {
          const out = [];
          frag.forEach((n) => {
            if (n.isText) {
              const link = n.marks.filter((m) => m.type.name !== "icode");
              for (const u of units(n.text)) {
                if (u.k === "code") out.push(schema.text(`$${u.source}$`, [...link, codeMark()]));
                else if (u.k === "break") out.push(schema.nodes.hard_break.create());
                else out.push(schema.text(u.c, link));
              }
            } else out.push(n.copy(fix(n.content)));
          });
          return Fragment.fromArray(out);
        };
        return new Slice(fix(slice.content), slice.openStart, slice.openEnd);
      },
    },
    // (each run kept a run: a broken one ($ deleted) is text again; an empty one the caret has left, gone)
    appendTransaction(trs, old, state) {
      if (!trs.some((t) => t.docChanged || t.selectionSet)) return null;
      const open = openRun(state);
      let tr = null;
      // (the caret landed inside a closed one, a click or ↑/↓: put at its nearer end, as if it were one piece)
      const { head, empty } = state.selection;
      const inside = empty && codeRuns(state.doc).find((r) => r.source !== null && r.from < head && head < r.to && r.key !== open?.key);
      if (inside) tr = selectRun(state, inside);   // (a click on its value, ↑/↓ into it: selected, the middle stop)
      for (const r of codeRuns(state.doc).reverse()) {
        if (r.source === null) (tr ||= state.tr).removeMark(r.from, r.to, schema.marks.icode);
        else if (r.source === "" && !(open && open.key === r.key)) (tr ||= state.tr).delete(r.from, r.to);
      }
      if (tr && !tr.docChanged) return tr;
      return tr?.setMeta("addToHistory", trs.every((t) => t.getMeta("addToHistory") !== false)) ?? null;
    },
    view(view) {
      // (later, never while the editor's still being made: its view isn't its own yet)
      const redraw = () => queueMicrotask(() => {
        version++;
        if (!view.isDestroyed && editor.view === view && codeRuns(view.state.doc).length) view.dispatch(view.state.tr.setMeta(icodeKey, "redraw").setMeta("addToHistory", false));
      });
      const stop = onSnapshot(redraw);
      hazel.load(redraw);
      return { destroy: () => stop?.() };
    },
  });
}
