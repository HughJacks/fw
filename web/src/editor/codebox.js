// codebox.js — an expression's code, written in CodeMirror ("we need to improve the expression
// editor experience, we could use codeMirror"; the box itself kept as it was: "i like the box how it is currently").
// Hazel's syntax highlighted; a reference `@<id>` stored by id and drawn as its pericope's title, a chip the caret steps
// over and ⌫ deletes whole (TYPE.md, references); typing `@` opens fw's own search (the one Quote a block uses) and a
// pick puts `@<id>` in; fw's built-ins and the code's own `let` names completed as you type. Its keys: Esc and the
// `code` command close it (exprview.js), Tab indents two spaces. Each change goes back as the block's `source`.
import { EditorState, RangeSetBuilder, Prec, Facet } from "@codemirror/state";
import { EditorView, Decoration, ViewPlugin, WidgetType, keymap, drawSelection } from "@codemirror/view";
import { StreamLanguage, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { autocompletion, completionKeymap, completionStatus, startCompletion, acceptCompletion } from "@codemirror/autocomplete";
import { history, historyKeymap, defaultKeymap } from "@codemirror/commands";
import { tags as t } from "@lezer/highlight";
import { api } from "../lib/api.js";
import { snapshot } from "../state/snapshot.svelte.js";
import * as hazel from "../expr/hazel.js";
import { receiverBefore, projectionsFor, typeOf, projectable } from "../expr/projections.js";

// --- Hazel's syntax, as far as colouring needs ---------------------------------------------------------------------

const KEYWORDS = new Set(["let", "in", "fun", "if", "then", "else", "case", "end", "type", "test", "rec", "and"]);
const ATOMS = new Set(["true", "false"]);
const RELATIVE = new Set(["this", "here", "self", "above", "below"]);   // (where the expression sits, worked out as it's viewed: drawn apart)
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
      if (RELATIVE.has(word)) return "relative";
      return /^[A-Z]/.test(word) ? "typeName" : "variableName";
    }
    if (s.match(/^(->|=>|\+\+|::|==\.?|!=|<=|>=|&&|\|\||[-+*\/<>=|!.,:;()[\]{}])/)) return "operator";
    s.next();
    return null;
  },
  tokenTable: { relative: t.special(t.variableName) },
});

const colours = HighlightStyle.define([
  { tag: t.keyword, color: "#c49bd6" },
  { tag: t.atom, color: "#d7a46f" },
  { tag: t.number, color: "#d7a46f" },
  { tag: t.string, color: "#a3c48a" },
  { tag: t.typeName, color: "var(--blue)" },
  { tag: t.special(t.variableName), class: "fw-relative" },
  { tag: t.comment, color: "var(--dim)", fontStyle: "italic" },
  { tag: t.operator, color: "var(--dim)" },
]);

// --- references drawn as titles ------------------------------------------------------------------------------------

let labels = { from: null, map: new Map(), homes: new Map(), tags: new Set() };
/** The index over the core's snapshot (rebuilt when it changes): each block's label and pericope, the tags. */
function index() {
  if (labels.from !== snapshot.store) {
    const map = new Map(), homes = new Map(), tags = new Set();
    const walk = (n, title, home) => {
      if (!n) return;
      if (n.id && !map.has(n.id)) { map.set(n.id, title ?? (n.t === "expr" ? `ƒ ${n.source || ""}` : n.text || "").replace(/\s+/g, " ").slice(0, 40)); homes.set(n.id, home); }
      for (const k of n.children || []) walk(k, null, home);
    };
    for (const p of snapshot.store?.pericopes || []) {
      map.set(p.id, p.title || ""); homes.set(p.id, p.id);
      if (p.tag) tags.add(p.id);
      for (const k of p.kinds || []) tags.add(k);
      walk(p.body, p.title || null, p.id);
    }
    labels = { from: snapshot.store, map, homes, tags };
  }
  return labels;
}
/** The pericope block `id` is in (a pericope its own), or null. */
export const homeOf = (id) => index().homes.get(id) ?? null;
/** Whether `id` is a tag. */
export const isTag = (id) => index().tags.has(id);
/** What a reference shows: its pericope's title, or the start of a block's text; "?" for one that isn't there. */
export function labelOf(id) {
  const l = index().map.get(id);
  return l === undefined ? null : l || "(untitled)";
}

/** The pericope the expression is in (`this`): a reference to it is drawn as `this` ("any self
 * referential references should render as 'this'"). */
const hereFacet = Facet.define({ combine: (v) => v[0] ?? new Map() });   // ({id: this | here | self})

class RefChip extends WidgetType {
  constructor(id, here = null) { super(); this.id = id; this.here = here; }   // (here: its word, this/here/self, or null)
  eq(o) { return o.id === this.id && o.here === this.here; }
  toDOM() {
    const s = document.createElement("span");
    if (this.here) { s.className = "fw-ref fw-ref-this"; s.textContent = this.here; s.title = `@${this.id}`; return s; }
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
    const names = view.state.facet(hereFacet);
    for (const m of text.matchAll(REF)) b.add(from + m.index, from + m.index + m[0].length, Decoration.replace({ widget: new RefChip(m[1], names.get(m[1]) ?? null) }));
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

export const BUILTINS = [
  ["body", "Ref -> Block", "a quote of it: what it shows, from it"],
  ["text", "String -> Block", "a block of text"],
  ["origin", "Block -> Option(Ref)", "where a quoted block came from"],
  ["content", "Block -> Block", "what a quoted block holds"],
  ["title", "Ref -> String", "its title (written, or from its first line)"],
  ["writtenTitle", "Ref -> Option(String)", "the title written for it, if one is"],
  ["pericopes", "[Ref]", "every pericope"],
  ["tagged", "Ref -> [Ref]", "the pericopes with this tag"],
  ["tags", "Ref -> [Ref]", "its tags"],
  ["notTags", "Ref -> [Ref]", "the tags it was said not to be"],
  ["wordCount", "Ref -> Int", "its words, as the header counts them"],
  ["created", "Ref -> Date", "when it was made (its own: a block's, a pericope's)"],
  ["updated", "Ref -> Date", "when it last changed"],
  ["visits", "Ref -> Int", "how many times it's been visited"],
  ["firstVisit", "Ref -> Option(Date)", "its first visit"],
  ["lastVisit", "Ref -> Option(Date)", "its last visit"],
  ["recentVisits", "Ref -> [Visit]", "its last visits: Visit((when, [Opened, Stayed, Wrote, Through]))"],
  ["backlinks", "Ref -> [Ref]", "what points at it"],
  ["isPericope", "Ref -> Bool", "a pericope, not a block inside one"],
  ["pericopeOf", "Ref -> Ref", "the pericope it's in (a pericope: itself)"],
  ["now", "Date", "this moment (moves on each minute)"],
  ["year", "Date -> Int", ""], ["month", "Date -> Int", ""], ["day", "Date -> Int", ""],
  ["hour", "Date -> Int", ""], ["minute", "Date -> Int", ""], ["weekday", "Date -> Int", "1 Monday … 7 Sunday"],
  ["showDate", "Date -> String", "as fw writes it: Nov 25, 2026, 3:12 pm"],
  ["before", "(Date, Date) -> Bool", "the first earlier than the second"],
  ["daysBetween", "(Date, Date) -> Int", "the second less the first, in days"],
  ["minutesBetween", "(Date, Date) -> Int", "the second less the first, in minutes"],
  ["this", "Ref", "the pericope it's in, where it sits now (its own place in it: a loop)"],
  ["here", "Ref", "the pericope it's viewed from (through a quote: the quoting one; in its own: this)"],
  ["self", "Ref", "the block itself (read from inside: a loop)"],
  ["above", "Ref", "the block just above this one"],
  ["below", "Ref", "the block just below this one"],
  ["map", "", ""], ["filter", "", ""], ["length", "", ""],
];
const CASES = [["Text", "[Inline] -> Block"], ["Paraphrase", "(Ref, String) -> Block"], ["Blocks", "[Block] -> Block"],
  ["Plain", "String -> Inline"], ["Link", "(String, Ref) -> Inline"],
  ["Visit", "(Date, [Attention]) -> Visit"], ["Opened", "Attention"], ["Stayed", "Attention"], ["Wrote", "Attention"], ["Through", "Attention"]];   // (no From: sealed; a quote is body(@x), TYPE.md)

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

/** After a dot, `x.f` (TYPE.md "Projection"): what can be projected from x, the functions whose first argument fits its
 * type first (projections.js). */
function dotCompletions(ctx) {
  const m = ctx.matchBefore(/\.[A-Za-z0-9_']*$/);
  if (!m) return null;
  const x = receiverBefore(ctx.state.doc.sliceString(0, m.from), m.from);
  if (!projectable(x)) return null;
  const type = typeOf(hazel.run, x);
  return {
    from: m.from + 1,
    filter: true,
    options: projectionsFor(BUILTINS, type).map((p) => ({
      label: p.label, detail: p.detail, info: p.info || undefined, type: "function",
      boost: p.fits ? 10 : 0, section: p.fits ? `on ${type}` : "others",
    })),
    validFor: /^[A-Za-z0-9_']*$/,
  };
}

function nameCompletions(ctx) {
  const m = ctx.matchBefore(/[A-Za-z_][A-Za-z0-9_']*/);
  if (!m || (m.from === m.to && !ctx.explicit)) return null;
  if (ctx.state.doc.sliceString(m.from - 1, m.from) === ".") return null;   // (after a dot: dotCompletions)
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
export function codeBox(parent, source, { changed, close, isClose, names = new Map(), inline = false, leave = null, away = null }) {
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
        hereFacet.of(names),
        history(),
        drawSelection({ cursorBlinkRate: 1000 }),   // (CodeMirror's own caret: the browser's, in an editable inside the page's, sometimes isn't painted)
        hazelSyntax, syntaxHighlighting(colours),
        refChips,
        autocompletion({ override: [refCompletions, dotCompletions, nameCompletions], icons: false }),
        Prec.highest(EditorView.domEventHandlers({ keydown: (e, v) => closing(e, v) })),
        // (↓ on its last line, ↑ on its first: out of it, to the block after or before; the completions' own first)
        Prec.high(keymap.of([
          { key: "ArrowDown", run: (v) => !!leave && !completionStatus(v.state) && v.state.doc.lineAt(v.state.selection.main.head).number === v.state.doc.lines && (leave(1), true) },
          { key: "ArrowUp", run: (v) => !!leave && !completionStatus(v.state) && v.state.doc.lineAt(v.state.selection.main.head).number === 1 && (leave(-1), true) },
        ])),
        // (Tab takes the completion offered, when one is; else indents two spaces)
        Prec.high(keymap.of([{ key: "Tab", run: (v) => acceptCompletion(v) || (v.dispatch(v.state.replaceSelection("  ")), true) }])),
        keymap.of([...completionKeymap, ...historyKeymap, ...defaultKeymap]),
        EditorView.inputHandler.of((v, from, to, text) => {   // (@ typed: the search opens at once)
          if (text === "@" || text === ".") queueMicrotask(() => startCompletion(v));   // (@: the search; .: what can be projected)
          if (inline && text === "$") { close(); return true; }   // (an inline expression: its closing $ back to the line)
          return false;
        }),
        EditorView.updateListener.of((u) => { if (u.docChanged) changed(u.state.doc.toString()); }),
        EditorView.lineWrapping,
        look,
      ],
    }),
  });
  parent.fwCode = view;   // (the browser tests write in it through this)
  // (the focus gone elsewhere on the page, a click in another block, say: closed, never left open behind you; another
  // window taking it keeps it open)
  if (away) parent.addEventListener("focusout", (e) => {
    const to = e.relatedTarget;
    if (!to || parent.contains(to) || to.closest?.(".cm-tooltip")) return;
    // (looked at once things settle: focus handed straight back, the editor's own jitter after a click, isn't leaving)
    requestAnimationFrame(() => { if (parent.isConnected && !parent.contains(document.activeElement)) away(); });
  });
  return view;
}

/** Box `view`'s text set to `text` (an undo from outside, say), without telling it back as a change. */
export function setText(view, text) {
  if (view.state.doc.toString() === text) return;
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
}
