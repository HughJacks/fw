// codebox.js — an expression's code, written in CodeMirror (the user, 2026-11-24: "we need to improve the expression
// editor experience, we could use codeMirror"; the box itself kept as it was: "i like the box how it is currently").
// Hazel's syntax highlighted; a reference `@<id>` stored by id and drawn as its pericope's title, a chip the caret steps
// over and ⌫ deletes whole (TYPE.md, references); typing `@` opens fw's own search (the one Quote a block uses) and a
// pick puts `@<id>` in; fw's built-ins and the code's own `let` names completed as you type. Its keys: Esc and the
// `code` command close it (exprview.js), Tab indents two spaces. Each change goes back as the block's `source`.
import { EditorState, RangeSetBuilder, Prec } from "@codemirror/state";
import { EditorView, Decoration, ViewPlugin, WidgetType, keymap, drawSelection } from "@codemirror/view";
import { StreamLanguage, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { autocompletion, completionKeymap, completionStatus, startCompletion } from "@codemirror/autocomplete";
import { history, historyKeymap, defaultKeymap } from "@codemirror/commands";
import { tags as t } from "@lezer/highlight";
import { api } from "./api.js";
import { snapshot } from "./snapshot.svelte.js";

// --- Hazel's syntax, as far as colouring needs ---------------------------------------------------------------------

const KEYWORDS = new Set(["let", "in", "fun", "if", "then", "else", "case", "end", "type", "test", "rec", "and"]);
const ATOMS = new Set(["true", "false"]);
export const REF = /@([0-9]{8}T[0-9]{6}-[0-9a-f]{4})/g;   // (a pericope or block id, as fw makes them)
/** The ids a source refers to, in order, each once (fw_block.expr_refs). */
export const refsIn = (src) => [...new Set([...(src || "").matchAll(REF)].map((m) => m[1]))];

const hazelSyntax = StreamLanguage.define({
  name: "hazel",
  token(s) {
    if (s.eatSpace()) return null;
    if (s.match(/^#[^#\n]*#?/)) return "comment";
    if (s.match(/^"(?:[^"\\]|\\.)*"?/)) return "string";
    if (s.match(/^@[0-9]{8}T[0-9]{6}-[0-9a-f]{4}/)) return "link";
    if (s.match(/^[0-9]+(\.[0-9]*)?/)) return "number";
    const w = s.match(/^[A-Za-z_][A-Za-z0-9_']*/);
    if (w) {
      const word = w[0];
      if (KEYWORDS.has(word)) return "keyword";
      if (ATOMS.has(word)) return "atom";
      return /^[A-Z]/.test(word) ? "typeName" : "variableName";
    }
    if (s.match(/^(->|=>|\+\+|::|==\.?|!=|<=|>=|&&|\|\||[-+*\/<>=|!.,:;()[\]{}])/)) return "operator";
    s.next();
    return null;
  },
});

const colours = HighlightStyle.define([
  { tag: t.keyword, color: "#c49bd6" },
  { tag: t.atom, color: "#d7a46f" },
  { tag: t.number, color: "#d7a46f" },
  { tag: t.string, color: "#a3c48a" },
  { tag: t.typeName, color: "var(--blue)" },
  { tag: t.comment, color: "var(--dim)", fontStyle: "italic" },
  { tag: t.operator, color: "var(--dim)" },
]);

// --- references drawn as titles ------------------------------------------------------------------------------------

let labels = { from: null, map: new Map() };
/** What a reference shows: its pericope's title, or the start of a block's text; "?" for one that isn't there. */
export function labelOf(id) {
  if (labels.from !== snapshot.store) {   // (an index over the core's snapshot, rebuilt when it changes)
    const map = new Map();
    const walk = (n, title) => {
      if (!n) return;
      if (n.id && !map.has(n.id)) map.set(n.id, title ?? (n.text || "").replace(/\s+/g, " ").slice(0, 40));
      for (const k of n.children || []) walk(k, null);
    };
    for (const p of snapshot.store?.pericopes || []) {
      map.set(p.id, p.title || "");
      walk(p.body, p.title || null);
    }
    labels = { from: snapshot.store, map };
  }
  const l = labels.map.get(id);
  return l === undefined ? null : l || "(untitled)";
}

class RefChip extends WidgetType {
  constructor(id) { super(); this.id = id; }
  eq(o) { return o.id === this.id; }
  toDOM() {
    const s = document.createElement("span");
    const label = labelOf(this.id);
    s.className = "fw-ref" + (label === null ? " fw-ref-gone" : "");
    s.textContent = label ?? "?";
    s.title = `@${this.id}`;
    return s;
  }
  ignoreEvent() { return false; }
}

function chips(view) {
  const b = new RangeSetBuilder();
  for (const { from, to } of view.visibleRanges) {
    const text = view.state.doc.sliceString(from, to);
    for (const m of text.matchAll(REF)) b.add(from + m.index, from + m.index + m[0].length, Decoration.replace({ widget: new RefChip(m[1]) }));
  }
  return b.finish();
}

const refChips = ViewPlugin.fromClass(class {
  constructor(view) { this.decorations = chips(view); this.from = snapshot.store; }
  update(u) {
    if (u.docChanged || u.viewportChanged || this.from !== snapshot.store) { this.decorations = chips(u.view); this.from = snapshot.store; }
  }
}, {
  decorations: (v) => v.decorations,
  provide: (p) => EditorView.atomicRanges.of((view) => view.plugin(p)?.decorations || Decoration.none),
});

// --- completion: @ → fw's search; names → fw's built-ins, Block's cases, the code's own lets -----------------------

const BUILTINS = [
  ["body", "Ref -> Block", "a quote of it: what it shows, from it"],
  ["text", "String -> Block", "a block of text"],
  ["origin", "Block -> Option(Ref)", "where a quoted block came from"],
  ["content", "Block -> Block", "what a quoted block holds"],
  ["title", "Ref -> String", "its title"],
  ["pericopes", "[Ref]", "every pericope"],
  ["tagged", "Ref -> [Ref]", "the pericopes with this tag"],
  ["tags", "Ref -> [Ref]", "its tags"],
  ["wordCount", "Ref -> Int", "its words, as the header counts them"],
  ["created", "Ref -> String", "when it was made (ISO)"],
  ["updated", "Ref -> String", "when it last changed (ISO)"],
  ["visits", "Ref -> Int", "how many times it's been visited"],
  ["backlinks", "Ref -> [Ref]", "the pericopes pointing at it"],
  ["above", "Ref", "the block just above this one"],
  ["below", "Ref", "the block just below this one"],
  ["map", "", ""], ["filter", "", ""], ["length", "", ""],
];
const CASES = [["Text", "[Inline] -> Block"], ["Paraphrase", "(Ref, String) -> Block"], ["Blocks", "[Block] -> Block"],
  ["Plain", "String -> Inline"], ["Link", "(String, Ref) -> Inline"]];   // (no From: sealed; a quote is body(@x), TYPE.md)

async function refCompletions(ctx) {
  const m = ctx.matchBefore(/@[^\s@()\[\],]*/);
  if (!m) return null;
  const q = m.text.slice(1);
  const r = await api(`/api/search?q=${encodeURIComponent(q)}`);
  if (!r.ok) return null;
  const rows = (r.body.rows || []).filter((row) => row.source && !row.dim);
  return {
    from: m.from,
    filter: false,   // (fw's search has ranked them already)
    options: rows.slice(0, 30).map((row) => ({
      label: row.label.trim(), detail: row.right || "", type: row.inside ? "block" : "pericope", apply: `@${row.source}`,
    })),
  };
}

function nameCompletions(ctx) {
  const m = ctx.matchBefore(/[A-Za-z_][A-Za-z0-9_']*/);
  if (!m || (m.from === m.to && !ctx.explicit)) return null;
  const own = [...ctx.state.doc.toString().matchAll(/\blet\s+([a-z_][A-Za-z0-9_']*)/g)].map((x) => x[1]);
  return {
    from: m.from,
    options: [
      ...BUILTINS.map(([label, detail, info]) => ({ label, detail, info: info || undefined, type: "function" })),
      ...CASES.map(([label, detail]) => ({ label, detail, type: "type" })),
      ...[...new Set(own)].map((label) => ({ label, type: "variable" })),
      ...[...KEYWORDS].map((label) => ({ label, type: "keyword" })),
    ],
    validFor: /^[A-Za-z0-9_']*$/,
  };
}

// --- the box -------------------------------------------------------------------------------------------------------

const look = EditorView.theme({
  "&": { color: "var(--fg)", backgroundColor: "transparent" },
  "&.cm-focused": { outline: "none" },
  ".cm-content": { caretColor: "var(--fg)", padding: "0", fontFamily: "inherit" },
  ".cm-line": { padding: "0" },
  ".cm-scroller": { fontFamily: "inherit", lineHeight: "inherit", overflow: "visible" },
  ".cm-cursor, &.cm-focused .cm-cursor": { borderLeftColor: "var(--fg)", borderLeftWidth: "1.5px" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": { backgroundColor: "rgba(120, 160, 220, .35)" },
  ".cm-tooltip": { backgroundColor: "#1b1b1b", border: "1px solid var(--rule)", color: "var(--fg)" },
  ".cm-tooltip-autocomplete > ul > li[aria-selected]": { backgroundColor: "#2c3a52", color: "var(--fg)" },
  ".cm-completionDetail": { color: "var(--dim)", fontStyle: "normal", marginLeft: ".6em" },
}, { dark: true });

/** A code box in `parent`, holding `source`. `changed(text)` on each change; `close()` for Esc or `isClose(e)`. */
export function codeBox(parent, source, { changed, close, isClose }) {
  // (Esc with the completions open closes them first; the `code` command always closes the box)
  const closing = (e, v) => {
    if (!(isClose(e) || (e.key === "Escape" && !completionStatus(v.state)))) return false;
    e.preventDefault(); close(); return true;
  };
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc: source,
      extensions: [
        history(),
        drawSelection({ cursorBlinkRate: 1000 }),   // (CodeMirror's own caret: the browser's, in an editable inside the page's, sometimes isn't painted)
        hazelSyntax, syntaxHighlighting(colours),
        refChips,
        autocompletion({ override: [refCompletions, nameCompletions], icons: false }),
        Prec.highest(EditorView.domEventHandlers({ keydown: (e, v) => closing(e, v) })),
        Prec.high(keymap.of([{ key: "Tab", run: (v) => { v.dispatch(v.state.replaceSelection("  ")); return true; } }])),
        keymap.of([...completionKeymap, ...historyKeymap, ...defaultKeymap]),
        EditorView.inputHandler.of((v, from, to, text) => {   // (@ typed: the search opens at once)
          if (text === "@") queueMicrotask(() => startCompletion(v));
          return false;
        }),
        EditorView.updateListener.of((u) => { if (u.docChanged) changed(u.state.doc.toString()); }),
        EditorView.lineWrapping,
        look,
      ],
    }),
  });
  parent.fwCode = view;   // (the browser tests write in it through this)
  return view;
}

/** Box `view`'s text set to `text` (an undo from outside, say), without telling it back as a change. */
export function setText(view, text) {
  if (view.state.doc.toString() === text) return;
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
}
