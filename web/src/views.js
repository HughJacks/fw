// views.js — how a quote and a picture are drawn in the editor (ProseMirror node views), and what a
// quote shows (the core's items: text, pictures, quotes inside, notes), read only for now.
import * as hazel from "./hazel.js";   // (the expr branch: an expression in a quote, worked out here)
import { api } from "./api.js";
import { snapshot, onSnapshot } from "./snapshot.svelte.js";
import { labelOf } from "./codebox.js";

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};

/** Text as the page shows it: each … (a hidden stretch of a masked quote) marked. */
function textEl(text) {
  const d = el("div", "fw-qtext");
  for (const part of text.split(/(…)/)) {
    d.appendChild(part === "…" ? el("span", "fw-hidden", "…") : document.createTextNode(part));
  }
  return d;
}

/** A date as the headers show it ("Nov 19, 2026, 11:00 PM"). */
export function prettyDate(iso) {
  return iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";
}

/** A quote's top line: a mini header, in the main header's style (the user, 2026-11-19), of what it shows of its source
 * (its `show`): a line of facts (the lock, its words, made, last update), then its title; empty, nothing shown. And a
 * way to open it. */
function topLine(q, open) {
  const top = el("div", "fw-top");
  const show = q.show || [], facts = [];
  if (q.lock) facts.push("⊘");
  if (show.includes("words")) facts.push(`words ${q.words ?? 0}`);
  if (show.includes("created") && q.created) facts.push(`made ${prettyDate(q.created)}`);
  if (show.includes("updated") && q.updated) facts.push(`updated ${prettyDate(q.updated)}`);
  const label = el("span", "fw-top-label");   // (left empty, no whitespace, when there's nothing: the CSS hides it)
  if (facts.length) label.appendChild(el("div", "fw-mini-facts", facts.join(" · ")));
  if (show.includes("title")) label.appendChild(el("div", "fw-mini-title", q.title));
  top.appendChild(label);
  if (open && q.target) {
    const go = el("button", "fw-open", "↗");
    go.title = "Open it (^O)";
    go.appendChild(el("span", "fw-open-name", q.title || labelOf(q.target) || ""));   // (hovered: its name, grown out to the right)
    go.addEventListener("mousedown", (e) => { e.preventDefault(); open(q); });
    top.appendChild(go);
  }
  return top;
}

/** What a quote shows, drawn into `box`. */
export function drawBody(box, items, open) {
  for (const item of items || []) {
    if (item.t === "text") box.appendChild(textEl(item.text));
    else if (item.t === "image" && item.file) {   // (in a block's box, as a picture anywhere: at the text's column, 2026-11-19)
      const pic = el("div", "fw-image"), img = el("img", "fw-pic");
      img.src = `/images/${item.file}`;
      pic.appendChild(img);
      box.appendChild(pic);
    } else if (item.t === "expr") {   // (an expression: what it works out to, read only)
      const box2 = el("div", "fw-expr");
      box.appendChild(box2);
      const stop = onSnapshot(() => {
        if (!box2.isConnected && box2.fwDrawn) { stop(); return; }   // (gone from the page: no longer followed)
        box2.fwDrawn = true;
        drawValue(box2, hazel.run(item.source || "", item.id), open);
      });
      hazel.load(() => drawValue(box2, hazel.run(item.source || "", item.id), open));
    } else if (item.t === "quote") box.appendChild(quoteEl(item, open, true));
    else box.appendChild(el("div", "fw-note", item.text || ""));
  }
}

/** A quote's box: its top line, then what it shows. */
export function quoteEl(q, open, inner = false) {
  const box = el("div", inner ? "fw-quote fw-inner" : "fw-quote");
  if (q.home || q.target) box.dataset.pericope = q.home || q.target;   // (where Open it goes: motion.js steps from or to it)
  if (q.target) box.dataset.target = q.target;   // (what it quotes: the pericope, or a block in it, a step arrives at)
  if (q.lock) box.classList.add("fw-locked");
  box.appendChild(topLine(q, inner ? null : open));
  const body = el("div", "fw-body");
  drawBody(body, q.body, open);
  box.appendChild(body);
  return box;
}

// --- a value, drawn (the expr branch: fw's type is Hazel's; an expression's value of type Block is drawn as fw's blocks)

const quotes = new WeakMap();   // the core's snapshot -> {target: a quote of it as the core draws one, or its promise}
/** A quote of `target` as the core draws one (GET /api/quote): known already, or a promise of it (asked once per
 * snapshot of the store, so it follows what's written there). */
export function quoteOf(target) {
  const store = snapshot.store || {};
  if (!quotes.has(store)) quotes.set(store, new Map());
  const known = quotes.get(store);
  if (!known.has(target)) {
    known.set(target, api(`/api/quote?target=${encodeURIComponent(target)}`).then((r) => {
      const q = r.ok ? r.body : { t: "quote", target, title: "missing block", body: [{ t: "note", text: `missing block ${target}` }] };
      known.set(target, q);
      return q;
    }));
  }
  return known.get(target);
}

/** A Block value (the bridge's tree) as fw's blocks: a block of text, a paraphrase (drawn as one is), a quote (drawn as
 * quotes are, its source's own), blocks (a container), or a hole (what's left unfinished, "?"). */
export function blockEl(t, open) {
  switch (t.t) {
    case "text": return el("div", "fw-qtext fw-vblock", t.text);
    case "paraphrase": { const d = el("div", "fw-qtext fw-para fw-vblock", t.text); d.title = "a paraphrase"; return d; }
    case "blocks": {
      const d = el("div", "fw-container fw-vblock");
      for (const k of t.children) d.appendChild(blockEl(k, open));
      if (!t.children.length) d.appendChild(el("div", "fw-note", "(no blocks)"));
      return d;
    }
    case "from":   // (blocks that came from a pericope unchanged: a quote of it, green; TYPE.md)
    case "quote": {   // (the core's drawing of it, once it's here)
      const q = quoteOf(t.target), box = (q) => { const d = quoteEl(q, open, true); d.classList.add("fw-vblock"); if (t.t === "from") d.classList.add("fw-from"); return d; };
      if (!q.then) return box(q);
      const d = el("div", "fw-quote fw-inner fw-vblock");
      d.appendChild(el("div", "fw-note", "…"));
      q.then((q) => d.replaceWith(box(q)));
      return d;
    }
    default: { const h = el("span", "fw-vhole", "?"); h.title = t.printed || "unfinished"; return h; }
  }
}

/** What an expression (or an application) works out to, drawn into `box` (replacing what was there): a Block value as
 * blocks; any other value printed; a function its type, dim; why it can't be worked out yet. Hazel's errors in its
 * title. */
/** The ids a value drawn in editor `ed` is seen from inside: the expression itself (`self`), the pericope it's in and
 * every block it's being looked through (the quotes around it, their targets). A reference to one of them is the
 * recursive case (the user, 2026-11-25): drawn with a loop. */
export function insideOf(ed, self) {
  const ids = new Set(self ? [self] : []);
  for (const e of ed ? [ed, ...ed.around] : []) {
    if (e.id) ids.add(e.id);
    const t = e.holder?.node?.attrs?.target;
    if (t) ids.add(t);
  }
  return ids;
}

/** The pericope `this` is for an expression (or a call) `self` in editor `ed`: the core's (its facts), else the
 * pericope open on the page (a block just written, the core's word on it still to come). */
export function thisOf(ed, self) {
  const chain = ed ? [ed, ...ed.around] : [];
  return snapshot.store?.facts?.[self]?.pericope ?? chain.at(-1)?.id ?? null;
}
/** The pericope it's viewed from (`here`): the one open on the page, whatever it's seen through. */
export function hereOf(ed) {
  return (ed ? [ed, ...ed.around] : []).at(-1)?.id ?? null;
}
/** The words a reference is drawn as, relative to where it's seen (TYPE.md: this, here, self): {id: word}; the
 * pericope it's in is `this` even when it's also `here`. */
export function namesOf(ed, self) {
  const m = new Map();
  if (self) m.set(self, "self");
  const h = hereOf(ed), t = thisOf(ed, self);
  if (h) m.set(h, "here");
  if (t) m.set(t, "this");
  return m;
}

/** A value as Hazel prints it, each Ref in it drawn as a chip, as references are in the code (its pericope's title; a
 * click opens it); a Ref to where it's seen from (`inside`), the recursive case, with a loop: ↻. */
function printedEl(printed, open, inside = new Set(), names = new Map()) {
  const out = el("div", "fw-expr-out");
  let at = 0;
  for (const m of printed.matchAll(/Ref\("([0-9]{8}T[0-9]{6}-[0-9a-f]{4})"\)/g)) {
    if (m.index > at) out.append(printed.slice(at, m.index));
    if (names.has(m[1])) {   // (this, here, self: as the code says them)
      const word = names.get(m[1]), chip = el("span", "fw-ref fw-ref-this", word);
      chip.title = `@${m[1]}: ${{ this: "the pericope it's in", here: "the pericope it's seen from", self: "the block itself" }[word]}`;
      out.append(chip);
      at = m.index + m[0].length;
      continue;
    }
    const label = labelOf(m[1]), loop = inside.has(m[1]);
    const chip = el("span", "fw-ref" + (label === null ? " fw-ref-gone" : "") + (loop ? " fw-ref-loop" : ""), (label ?? "?") + (loop ? " ↻" : ""));
    chip.title = `@${m[1]}`;
    if (open && label !== null) chip.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); open({ target: m[1] }); });
    out.append(chip);
    at = m.index + m[0].length;
  }
  if (at < printed.length) out.append(printed.slice(at));
  return out;
}

/** An inline expression's value, as it sits in a line (TYPE.md "Inline"): text, or anything cast to text (a string
 * its words, a list its things, a Ref its chip, `this` its pericope); blocks can't sit in a line: `!`, a note why. */
/** What a value is, as its colour says it (the user, 2026-11-25: colour by the evaluated type, not how it was made):
 * "data" (numbers, dates, true/false), "ref" (a Ref), "window" (blocks from somewhere: a From, a Loop), "hole" (not a
 * value yet: empty, an error, a hole in it), else "text". */
export function toneOf(r) {
  if (!r || r.kind === "empty" || r.kind === "error" || r.errors?.length) return "hole";
  if (r.kind === "function") return "text";
  if (r.kind === "block") return ["from", "loop"].includes(r.block?.t) ? "window" : "text";
  const t = (r.type || "").replace(/^\[(.*)\]$/, "$1").replace(/^Option\((.*)\)$/, "$1");
  if (/^(Int|Float|Bool|Date)$/.test(t)) return "data";
  if (t === "Ref") return "ref";
  return "text";
}

/** A value's printed form as its place shows it (TYPE.md "Casting", the result first): a String (a Date) its words,
 * never its quotes; anything else as printed. */
function words(r) {
  if (r.type !== "String" && r.type !== "Date") return r.printed;   // (a Date prints as fw writes one: words too)
  try { return JSON.parse(r.printed); } catch { return r.printed.replace(/^"|"$/g, ""); }
}
/** A value's type, and the casts put in to get it (TYPE.md "Casting": visible), for its tooltip. */
export function typeNote(r) {
  const casts = (r?.casts || []).map((c) => `${c.from} → ${c.to} (${c.cast})`);
  return [r?.type || "", ...(casts.length ? [`cast: ${casts.join(", ")}`] : [])].filter(Boolean).join(" · ");
}

export function inlineValueEl(r, open, names = new Map()) {
  const span = (cls, text, title = "") => { const s = el("span", `fw-icode-out fw-tone-${toneOf(r)}` + (cls ? " " + cls : ""), text); s.title = title; return s; };
  if (!r) return span("fw-icode-wait", "…");
  if (r.kind === "empty") return span("fw-icode-wait", "$ $", "an empty inline expression · ⌘⇧X to write it");
  if (r.kind === "error") return span("fw-icode-hole", "?", r.message);
  if (r.kind === "function") return span("fw-icode-wait", r.type);
  if (r.kind === "block") return span("fw-icode-bad", "!", "this works out to blocks, which can't sit in a line: write it as an expression block ($ in an empty block)");
  const printed = words(r);
  const out = span(r.errors?.length ? "fw-icode-hole" : "", "", typeNote(r));
  out.append(...printedEl(printed, open, new Set(), names).childNodes);
  return out;
}

export function drawValue(box, r, open, inside = new Set(), names = new Map()) {
  let out;
  if (!r) out = el("div", "fw-expr-out fw-expr-wait", hazel.status() === "failed" ? "(the expression engine didn't load)" : "…");
  else if (r.kind === "empty") out = el("div", "fw-expr-out fw-expr-wait", "an empty expression · ⌘⇧X to write it");
  else if (r.kind === "error") out = el("div", "fw-expr-out fw-expr-holes", r.message);
  else if (r.kind === "function") out = el("div", "fw-expr-out fw-expr-fn", r.type);
  else if (r.kind === "block") { out = el("div", "fw-expr-out fw-expr-block"); out.appendChild(blockEl(r.block, open)); }
  else if (r.items?.length) {   // (a list: each item its own piece, stepped through with the arrows: ExprView.selectItem)
    out = el("div", "fw-expr-out");
    r.items.forEach((item, n) => {
      if (n) out.append(", ");
      const span = el("span", "fw-item");
      span.append(...printedEl(item, open, inside, names).childNodes);
      out.append(span);
    });
  }
  else out = printedEl(words(r), open, inside, names);
  if (r?.errors?.length) out.classList.add("fw-expr-holes");
  out.title = r?.type ? `${typeNote(r)}${r.errors?.length ? " · " + r.errors.map((e) => e.message).join("; ") : ""}` : "";
  const was = box.querySelector(":scope > .fw-expr-out");
  if (was) was.replaceWith(out); else box.appendChild(out);
  return out;
}
