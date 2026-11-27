// tabs.js — where you are, as an address in the gutter. Every block on your path, from the
// top-level block down to the one you're in (or have selected whole), gets a tab level with its top, joined to its
// box by a line: labelled by its place among its siblings, the top level numbered, then letters, then roman numerals,
// then numbers again. Only the focus's tab is bright (filled when it's selected whole); the path's are faint. Each is
// centred on its block's first line, unless boxes start on that one line: then stacked, the outer ones above, as they
// nest (worked out from the page alone, not from which tabs show), each line still meeting its own box. Which blocks
// are on the path comes from the editors' states (editor.svelte.js focusOf, the audit of: never read back
// from the page's classes); only where their boxes are is measured here; drawn by Tabs.svelte.

const BOX = ".fw-text, .fw-qtext, .fw-container, .fw-quote, .fw-image, .fw-expr";   // (.fw-expr: an expression block, the expr branch)
const GAP = 3;   // px between tabs moved apart
const PAD = 0.35;   // of a tab's height: how far inside its box, from its top and bottom, a tab's line keeps when it can

const roman = (n) => [["x", 10], ["ix", 9], ["v", 5], ["iv", 4], ["i", 1]].reduce((out, [s, v]) => { while (n >= v) { out += s; n -= v; } return out; }, "");
const alpha = (n) => { let s = ""; for (; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(97 + ((n - 1) % 26)) + s; return s; };
/** Block number `n` (from 1) as its level `level` (0: top) labels it. */
const label = (n, level) => [String(n), alpha(n), roman(n)][level % 3];

/** A quote showing one block: that block is the block it quotes, its box the quote's (no tab of its own). */
const ownBox = (e) => !((e.matches(".fw-text") && e.parentElement?.matches(".fw-quote > .fw-body > .ProseMirror") && e.parentElement.childElementCount === 1)
  || (e.parentElement?.matches(".fw-value") && e.parentElement.childElementCount === 1));   // (a value's one block: unwrapped, its holder's box)

/** The boxes from the top-level block down to `e`, outermost first. */
function path(e, frame) {
  const out = [];
  for (let x = e; x && x !== frame; x = x.parentElement) if (x.matches?.(BOX) && ownBox(x)) out.unshift(x);
  return out;
}

/** The screen middle of block `b`'s first line of text (its top, a little in, if it has none). */
function firstLine(b) {
  const w = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    if (!n.data.trim() || n.parentElement.closest(".fw-top, .fw-tabs, .fw-open")) continue;   // (its writing: not a quote's top line, its ↗)
    const r = document.createRange();
    r.setStart(n, 0); r.setEnd(n, 1);
    const rect = r.getBoundingClientRect();
    return rect.top + rect.height / 2;
  }
  return b.getBoundingClientRect().top + 16;
}

/** Its place among its parent's blocks, from 1. */
function place(e) {
  const kids = [...e.parentElement.children].filter((c) => c.matches(BOX));
  return kids.indexOf(e) + 1;
}

/** Where you are (editor.svelte.js focusOf: the editor you're in, what's drawn there) as boxes on the page:
 * {focus, first, last, chosen}, the block in focus (the first of blocks selected whole), the run's first and last, and
 * whether they're selected whole; or null. Each box is its node's own element (the view's nodeDOM). */
export function focusBoxes(f) {
  if (!f || f.editor.gone) return null;
  const view = f.editor.view;
  if (f.from === null) {   // (in it, nothing of it drawn: a quote showing one block, the quote)
    const q = f.editor.holder?.dom;
    return q ? { focus: q, first: q, last: q, chosen: false } : null;
  }
  const first = view.nodeDOM(f.from), last = view.nodeDOM(f.to);
  return first?.nodeType === 1 && last?.nodeType === 1 ? { focus: first, first, last, chosen: f.chosen } : null;
}

/** The tabs where you are on the page in `doc` (.fw-doc), measured: [{box, label, focus, filled, quote, left, top,
 * width, height, lineLeft, lineWidth}] in .fw-doc's coordinates (none when you're nowhere in it). `here`: where you are
 * (focusBoxes). Tabs.svelte draws them. */
export function tabsIn(doc, here) {
  const frame = doc?.querySelector(":scope > .ProseMirror");
  if (!frame || !here) return [];
  const focus = here.focus;
  if (!focus || !frame.contains(focus)) return [];
  const boxes = path(focus.matches(BOX) ? focus : focus.closest(BOX), frame);
  if (!boxes.length) return [];
  const d = doc.getBoundingClientRect(), f = frame.getBoundingClientRect();
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const tabW = 1.6 * rem, tabH = 1.45 * rem, left = f.left - d.left - 1.1 * rem - tabW;   // (the numbers' column; tall enough for any label)
  // Where each tab goes is worked out from the page alone, never from which other tabs show (
  // every block's tab "positioned, just not visible until they are needed"): boxes starting on one line (a box and its
  // first box inside, and so on down: its first-line chain) stack their tabs, the innermost on the line, each outer one
  // a tab above, as the boxes nest; the whole stack pushed down just enough for each line to stay on its own box, padded
  // from its ends (PAD, or as much of it as fits); if not even that, tight (a line just under its box's corner coming in
  // along its top edge).
  const top = (b) => b.getBoundingClientRect().top - d.top, bottom = (b) => b.getBoundingClientRect().bottom - d.top;
  const line = (b) => firstLine(b) - d.top;
  const same = (a, b) => Math.abs(line(a) - line(b)) < 1;
  const up = (b) => { const p = b.parentElement?.closest(BOX); return p && frame.contains(p) ? (ownBox(p) ? p : up(p)) : null; };
  const firstIn = (b) => { const k = b.querySelector(BOX); return k && !ownBox(k) ? firstIn(k) : k; };
  function chainOf(b) {   // the boxes starting on b's line, outermost first
    let outer = b;
    for (let p = up(outer); p && same(p, b); p = up(p)) outer = p;
    const out = [outer];
    for (let k = firstIn(outer); k && same(k, outer); k = firstIn(k)) out.push(k);
    return out;
  }
  function stack(chain, pad) {   // the chain's tops: innermost on the line, outer ones above, pushed down to fit
    const at = line(chain[chain.length - 1]) - tabH / 2;
    const tops = chain.map((b, i) => at - (chain.length - 1 - i) * (tabH + GAP));
    const by = Math.max(0, ...chain.map((b, i) => top(b) + pad - tabH / 2 - tops[i]));
    const placed = tops.map((t) => t + by);
    return { tops: placed, fits: chain.every((b, i) => placed[i] <= bottom(b) - pad - tabH / 2) };
  }
  const where = new Map();   // box → its tab's top
  for (const b of boxes) {
    if (where.has(b)) continue;
    const chain = chainOf(b);
    // (as much padding as fits, up to PAD: found by halving, so a box growing or shrinking moves its tabs smoothly,
    // never from one rule to another at once)
    let { tops: ts, fits } = stack(chain, PAD * tabH);
    if (!fits && stack(chain, 2).fits) {
      let lo = 2, hi = PAD * tabH;
      for (let i = 0; i < 12; i++) { const mid = (lo + hi) / 2; if (stack(chain, mid).fits) lo = mid; else hi = mid; }
      ({ tops: ts, fits } = stack(chain, lo));
    }
    if (!fits) {   // tight: each on its own box (clamped), a line just under its box's corner snapped to the top edge
      ts = stack(chain, 2).tops.map((t, i) => Math.min(t, bottom(chain[i]) - 2 - tabH / 2));
      const SNAP = 0.4 * tabH;
      chain.forEach((b, i) => {
        const edge = top(b), mid = ts[i] + tabH / 2, t = edge - tabH / 2;
        if (mid > edge && mid - edge < SNAP && ts.every((u, k) => k === i || t + tabH + GAP <= u || t >= u + tabH + GAP)) ts[i] = t;
      });
    }
    chain.forEach((c, i) => where.set(c, ts[i]));
  }
  const tops = boxes.map((b) => where.get(b));
  return boxes.map((b, level) => {
    const r = b.getBoundingClientRect(), focusHere = b === boxes[boxes.length - 1];
    const inItem = b.classList.contains("fw-in-item");   // (on an item of its value: where you are, its tab not filled)
    return { box: b, label: label(place(b), level), focus: focusHere, filled: focusHere && b === focus && here.chosen && !inItem, quote: b.matches(".fw-quote, .fw-para, .fw-expr[data-tone='window']"), expr: false,   // (a box coloured only as a window: app.css)
      left, top: tops[level], width: tabW, height: tabH, lineLeft: left + tabW, lineWidth: Math.max(0, r.left - d.left - left - tabW) };
  });
}

/** The lines linking the deepest block that's active (the one you're in, or selected whole; a quote showing one block,
 * you in it, is that block) to the blocks just before and after it at its level (every level a
 * chain of blocks, linked; the lines seen only as the active block and its glow are): [{left, top, height, from, to}]
 * in .fw-doc's coordinates, each a line at the text's column, from the neighbour's lit colour to the active one's. */
export function linksIn(doc, here) {
  const frame = doc?.querySelector(":scope > .ProseMirror");
  if (!frame || !here) return [];
  const focus = here.focus;
  if (!focus || !frame.contains(focus)) return [];
  const boxes = path(focus.matches(BOX) ? focus : focus.closest(BOX), frame);
  let first = boxes.at(-1), last = first;
  if (!first) return [];
  const sib = (e, dir) => { let x = dir < 0 ? e.previousElementSibling : e.nextElementSibling; while (x && !x.matches(BOX)) x = dir < 0 ? x.previousElementSibling : x.nextElementSibling; return x; };
  const chosen = here.chosen && first === focus && !first.classList.contains("fw-in-item");   // (on an item: where you are, not selected whole)
  if (chosen) { first = here.first; last = here.last; }   // (several selected whole: the run's ends)
  // (every line on one x, the page's text column, as the header's line: not stepped in with the depth)
  const d = doc.getBoundingClientRect(), cs = getComputedStyle(first), root = getComputedStyle(document.documentElement);
  const rem = parseFloat(root.fontSize), at = (v) => parseFloat(root.getPropertyValue(v)) * rem;
  const x = frame.getBoundingClientRect().left - d.left + 3 * at("--u") + at("--pad");   // (--text-at)
  // (each end its box's own lit colour, never its border as drawn: that may be easing in, and a line measured then kept
  // its half-way colour)
  const level = chosen ? "--own-bright" : "--own-mid";
  const own = (e) => getComputedStyle(e).getPropertyValue(level).trim() || cs.borderTopColor;
  const lit = own(first);
  const out = [], before = sib(first, -1), after = sib(last, 1);
  if (before) {
    const a = before.getBoundingClientRect().bottom, b = first.getBoundingClientRect().top;
    if (b > a) out.push({ left: x, top: a - d.top, height: b - a, from: own(before), to: lit });
  }
  if (after) {
    const a = last.getBoundingClientRect().bottom, b = after.getBoundingClientRect().top;
    if (b > a) out.push({ left: x, top: a - d.top, height: b - a, from: lit, to: own(after) });
  }
  return out;
}

/** The right edge of the page in `doc` (.fw-doc): every tab there (a quote's or a paraphrase's ↗, an expression's ƒ, a
 * dependency's ↙ or "+n"), whatever block it's in and however deep, one stack. Each wants the y it's drawn at; taken in
 * that order down the page (on one y, the page's order), each is pushed down to the slot after the one above, a ↙'s
 * gap apart, never meeting it. */
export function stackRight(doc) {
  const all = [...doc.querySelectorAll(".fw-open, .fw-fn, .fw-dep")];
  for (const x of all) x.style.translate = "";
  const gap = 0.35 * parseFloat(getComputedStyle(document.documentElement).fontSize);
  const tabs = all.filter((x) => x.getBoundingClientRect().height && x.checkVisibility({ visibilityProperty: true })).map((x) => {
    const r = x.getBoundingClientRect(), line = x.matches(".fw-dep") ? 0 : 1;   // (its line drawn 1px outside it; a ↙'s is its border)
    return { x, top: r.top - line, bottom: r.bottom + line };
  }).sort((a, b) => a.top - b.top);
  let floor = -Infinity;
  for (const t of tabs) {
    const by = Math.max(0, floor - t.top);
    if (by) t.x.style.translate = `0 ${by}px`;
    floor = t.bottom + by + gap;
  }
}
