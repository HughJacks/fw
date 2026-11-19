// tabs.js — where you are, as an address in the gutter (the user, 2026-11-18). Every block on your path, from the
// top-level block down to the one you're in (or have selected whole), gets a tab level with its top, joined to its
// box by a line: labelled by its place among its siblings, the top level numbered, then letters, then roman numerals,
// then numbers again. Only the focus's tab is bright (filled when it's selected whole); the path's are faint. Each is
// centred on its block's first line, the focus's always; one that would overlap another moves just above or below the
// others, wherever its line still meets its own box (never a line pointing at nothing). Measured here from the DOM's
// marks (editor.js: fw-current, fw-here, fw-chosen); drawn by Tabs.svelte.

const BOX = ".fw-text, .fw-qtext, .fw-container, .fw-quote, .fw-image";
const GAP = 3;   // px between tabs moved apart
const PAD = 0.35;   // of a tab's height: how far inside its box, from its top and bottom, a tab's line keeps when it can

const roman = (n) => [["x", 10], ["ix", 9], ["v", 5], ["iv", 4], ["i", 1]].reduce((out, [s, v]) => { while (n >= v) { out += s; n -= v; } return out; }, "");
const alpha = (n) => { let s = ""; for (; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(97 + ((n - 1) % 26)) + s; return s; };
/** Block number `n` (from 1) as its level `level` (0: top) labels it. */
const label = (n, level) => [String(n), alpha(n), roman(n)][level % 3];

/** A quote showing one block: that block is the block it quotes, its box the quote's (no tab of its own). */
const ownBox = (e) => !(e.matches(".fw-text") && e.parentElement?.matches(".fw-quote > .fw-body > .ProseMirror") && e.parentElement.childElementCount === 1);

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
    if (!n.data.trim() || n.parentElement.closest(".fw-top, .fw-tabs")) continue;   // (its writing: not a quote's top line, its ↗)
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

/** The tabs where you are on the page in `doc` (.fw-doc), measured: [{box, label, focus, filled, quote, left, top,
 * width, height, lineLeft, lineWidth}] in .fw-doc's coordinates (none when you're nowhere in it). Tabs.svelte
 * draws them. */
export function tabsIn(doc) {
  const frame = doc?.querySelector(":scope > .ProseMirror");
  if (!frame) return [];
  const focus = document.querySelector(".fw-current .fw-chosen") || document.querySelector(".fw-current .fw-here")
    || document.querySelector(".fw-current")?.closest(".fw-quote");   // (in a quote showing one block: the quote)
  if (!focus || !frame.contains(focus)) return [];
  const boxes = path(focus.matches(BOX) ? focus : focus.closest(BOX), frame);
  if (!boxes.length) return [];
  const d = doc.getBoundingClientRect(), f = frame.getBoundingClientRect();
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const tabW = 1.6 * rem, tabH = 1.45 * rem, left = f.left - d.left - 1.1 * rem - tabW;   // (the numbers' column; tall enough for any label)
  // (never a tab whose line misses its box: each tab's middle stays within its own box's top and bottom, `pad` in from
  // each (the user, 2026-11-19: padding at both ends, things pushed down to make it). The focus's goes on its line;
  // each around it, from the inside out, takes the first of its own line, just above the tabs placed, just above them
  // with them nudged down just enough to make room (an outer block starting on the inner one's line: the outer's tab
  // above the inner's, as the boxes nest; only if every tab nudged still meets its own box, padded), just below them;
  // that clears them and keeps its line on its box. Placed with the padding if every tab fits so; else tight, a line
  // that then meets its box just under the corner coming in along the box's top edge instead)
  const want = boxes.map((b) => firstLine(b) - d.top - tabH / 2);
  const rects = boxes.map((b) => b.getBoundingClientRect());
  function stack(pad) {
    const tops = [], ranges = [];
    let fits = true;
    const placed = () => tops.map((t, k) => k).filter((k) => tops[k] !== undefined);
    const clear = (t) => placed().every((k) => t + tabH + GAP <= tops[k] || t >= tops[k] + tabH + GAP);
    for (let i = boxes.length - 1; i >= 0; i--) {
      const r = rects[i], lo = r.top - d.top + pad - tabH / 2, hi = r.bottom - d.top - pad - tabH / 2;
      ranges[i] = [lo, hi];
      const onBox = (t) => t >= lo && t <= hi;
      const ks = placed(), first = ks.length ? Math.min(...ks.map((k) => tops[k])) : want[i];
      const above = first - GAP - tabH, below = ks.length ? Math.max(...ks.map((k) => tops[k])) + tabH + GAP : want[i];
      let t = [want[i], above].find((x) => onBox(x) && clear(x));
      if (t === undefined && ks.length && above < lo && lo <= hi) {   // above, the rest nudged down by what it lacks
        const by = lo - above;
        if (ks.every((k) => tops[k] + by <= ranges[k][1])) { for (const k of ks) tops[k] += by; t = lo; }
      }
      t ??= [below].find((x) => onBox(x) && clear(x));
      if (t === undefined) { fits = false; t = Math.min(Math.max(want[i], lo), hi); }
      tops[i] = t;
    }
    return { tops, fits };
  }
  const padded = stack(PAD * tabH);
  const tops = padded.fits ? padded.tops : stack(2).tops;
  if (!padded.fits) {   // (tight: a line just under its box's corner comes in along the top edge, the user, 2026-11-19)
    const SNAP = 0.4 * tabH;
    boxes.forEach((b, i) => {
      const edge = rects[i].top - d.top, mid = tops[i] + tabH / 2, t = edge - tabH / 2;
      const others = tops.filter((u, k) => k !== i);
      if (mid > edge && mid - edge < SNAP && others.every((u) => t + tabH + GAP <= u || t >= u + tabH + GAP)) tops[i] = t;
    });
  }
  return boxes.map((b, level) => {
    const r = b.getBoundingClientRect(), focusHere = b === boxes[boxes.length - 1];
    return { box: b, label: label(place(b), level), focus: focusHere, filled: focusHere && b.matches(".fw-chosen"), quote: b.matches(".fw-quote"),
      left, top: tops[level], width: tabW, height: tabH, lineLeft: left + tabW, lineWidth: Math.max(0, r.left - d.left - left - tabW) };
  });
}
