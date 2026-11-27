// motion.js — moving around the store, animated ("edits should feel instant but navigation
// should be animated so that people get a sense of moving around the store"). Every navigation goes through
// `travel`; edits never do.
//
// A step into a quote (⌘O, ⌘]), as the user set it out (the second time), one beat after another
// (step.svelte.js moves the page's own elements): the tabs fade · everything but the quote fades, the header too, the
// quote showing only as selected (nothing active inside it) · it widens to the page's width, if it isn't · [the page
// changes underneath, scrolled so its first block is where the quote is: a copy of the quote, the ghost, stands there
// meanwhile] · the ghost grows to that block, if it's taller (room for what the quote didn't show: ⋯ too deep, ↻ a
// cycle, a mask's hidden text), moving only if the scroll couldn't put it there · that block shows in its place, its
// selected border gone (its blocks are the page's now) · the header, the other blocks and the tabs fade in.
// Stepping out (⌘[) is the same backwards: the page's first block selected, everything else fading; the page it's in
// put under it, scrolled so the quote standing for it is there; the ghost shrinks into the quote; it narrows; the rest
// fades in, the quote selected whole. Only into a quote on the page, or back out of one; anything else just appears.
// ?slow=N plays it N times slower; ?beats stops after each beat until "." (the bar says which). On;
// off in the tests (but ?motion), and with reduced motion.
import { tick } from "svelte";
import { TEST } from "./api.js";
import { Step } from "../state/step.svelte.js";

const params = new URLSearchParams(location.search);
const OFF = TEST && !params.has("motion");   // (on, "install this into the main page"; off in the tests but for ?motion)
const STEPPING = params.has("beats");
const SLOW = Math.max(1, +(params.get("slow") || 1));
const reduced = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : { matches: true };
/** Nothing moves (the small motions: the active block's room easing out, the tabs following it): in the tests (but
 * ?motion), and with reduced motion. Also html.fw-still, for the CSS. */
export const still = (TEST && !params.has("motion")) || reduced.matches;
document.documentElement.classList.toggle("fw-still", still);
const BEAT = 140 * SLOW;   // ms a beat takes (one at a time, for now)
// the fades (the tabs, then the header and the other blocks, fading out a little apart; the
// header, the blocks and the glow fading in together, the tabs a little after): how long one takes, and how far into
// the first the second starts
const FADE = 160 * SLOW, STAGGER = 60 * SLOW;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
/** Beats `a` then `b` (each [name, to, what ?beats calls it]), `b` starting STAGGER into `a`; in ?beats, one whole
 * after the other, each stopped after. */
async function staggered(step, [a, ta, sa = a], [b, tb, sb = b]) {
  if (STEPPING) { await step.go(a, ta); await between(sa); await step.go(b, tb); await between(sb); return; }
  const first = step.go(a, ta);
  await wait(STAGGER);
  await Promise.all([first, step.go(b, tb)]);
}

/** What in `root` stands for pericope `id`: a quote of something in it, a link to it, its card or row; the one
 * you're at first (a quote selected whole, or written in through). */
export function pointing(root, id) {
  if (!id || !root) return null;
  const at = `[data-pericope="${id}"]`;
  return root.querySelector(`.fw-chosen${at}, .fw-quote${at}:has(.fw-current), .fw-sel${at}`)
    || root.querySelector(`.fw-link[data-to="${id}"]`) || root.querySelector(at);
}

/** The quote on page `frame` standing for pericope `id` (where a step out lands). */
const standing = (frame, id) => frame?.querySelector(`.fw-quote[data-pericope="${id}"]`) || null;

let running = 0;   // (steps under way: the tests' "settled" waits for them)
export let last = null;   // the last step: {dir} (for the tests)
export const moving = () => running > 0;

// (what each beat did, as ?beats says it)
const SAID = {
  "in hide": "the tabs off", "in veil": "everything but the quote off, the header too", "in widen": "the quote widened to the page",
  "in room": "the quote grown (or moved) over what it opens", "in show": "what it opens there (every block of it), the quote gone",
  "in header": "the header, the other blocks, the first block's glow on", "in tabs": "the tabs on",
  "out hide": "the tabs off", "out veil": "everything but what's leaving off, the header too",
  "out room": "what's leaving shrunk (or moved) into the quote", "out show": "the quote there, the page left gone", "out widen": "the quote narrowed to its place",
  "out header": "the header, the other blocks, the first block's glow on", "out tabs": "the tabs on",
};
let beatNo = 0, beatWay = "in";
/** In stepping mode (?beats): wait for "." after beat `name`, the bar saying which and what it did; `skipped`: said
 * instead, why the beat didn't happen. */
function between(name, skipped = null) {
  if (!STEPPING) return Promise.resolve();
  const said = document.querySelector("#bar-left");
  const was = said?.textContent;
  beatNo++;
  if (said) said.textContent = ` ${beatWay} · beat ${beatNo}: ${skipped ? `${name} skipped (${skipped})` : SAID[`${beatWay} ${name}`] || name}   ·   press . for the next`;
  return new Promise((done) => {
    const go = (e) => {
      if (e.key !== ".") return;
      e.preventDefault(); e.stopPropagation();
      window.removeEventListener("keydown", go, true);
      if (said) said.textContent = was;
      done();
    };
    window.addEventListener("keydown", go, true);
  });
}

// --- the pieces ----------------------------------------------------------------------------------------------
const frameIn = (main) => main.querySelector(".fw-doc:not(.fw-ghost) > .ProseMirror");
const els = (main) => ({ header: main.querySelector(".fw-header"), stem: main.querySelector(".fw-stem"), host: main.querySelector(".fw-doc:not(.fw-ghost)") });
/** The screen top of the first text in `el` (null: none): what the ghost's text is lined up by. */
function firstText(el) {
  if (!el) return null;
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    if (!n.data.trim() || n.parentElement.closest(".fw-top")) continue;
    const r = document.createRange();
    r.setStart(n, 0); r.setEnd(n, 1);
    return r.getBoundingClientRect().top;
  }
  return null;
}
/** How far block `quote`'s sides go out to the page's (the frame's) width. */
function measure(frame, quote) {
  const f = frame.getBoundingClientRect(), q = quote.getBoundingClientRect();
  return { left: Math.max(0, q.left - f.left), right: Math.max(0, f.right - q.right) };
}
/** The page's frame copied where it is (the ghost: everything in it veiled but the block the step goes through, marked
 * .fw-target), to stand there while the page changes under it. */
function ghostOf(frame, whole = false) {
  const host = frame.parentElement, h = host.getBoundingClientRect();
  const wrap = document.createElement("div");
  wrap.className = `${host.className} fw-ghost`;   // (its classes: as veiled as the page)
  wrap.style.setProperty("--step-veil", "1");
  Object.assign(wrap.style, { position: "fixed", left: `${h.left}px`, top: `${h.top}px`, width: `${h.width}px`, margin: "0", maxWidth: "none", zIndex: "40", pointerEvents: "none" });
  const copy = frame.cloneNode(true);
  copy.removeAttribute("contenteditable");
  wrap.append(copy);
  document.body.append(wrap);
  return { wrap, quote: whole ? copy : copy.querySelector(".fw-target"), move: 0, grow: 0, shift: 0, quoteHeight: 0 };
}
/** The screen top of the caret (the text cursor, where you're writing), or null: none showing. */
function caretTop() {
  const s = window.getSelection();
  if (!s || !s.rangeCount || !s.isCollapsed || !document.activeElement?.closest?.(".ProseMirror")) return null;
  const r = s.getRangeAt(0).getClientRects()[0] || s.getRangeAt(0).startContainer.parentElement?.getBoundingClientRect();
  return r ? r.top : null;
}
/** The block `next` on the page just put under the ghost, scrolled so the caret is where it was on the screen (the
 * user: the text you're at stays put; no caret, its top where the ghost's block is), the ghost moving only
 * by what the scroll couldn't do (sliding up, never down: the page has room below to scroll), and how the ghost becomes
 * it: grows or shrinks to it, its text lined up. */
function meet(ghost, next, caretWas = null) {
  const t = ghost.quote.getBoundingClientRect(), caretNow = caretWas != null ? caretTop() : null;
  const by = caretNow != null ? caretNow - caretWas : next.getBoundingClientRect().top - t.top;
  room(scrollY + by - (document.documentElement.scrollHeight - innerHeight));
  window.scrollBy(0, by);
  const n = next.getBoundingClientRect();
  const a = firstText(ghost.quote), b = firstText(next);
  Object.assign(ghost, { move: n.top - t.top, quoteHeight: t.height, grow: n.height - t.height });
  ghost.shift = a != null && b != null ? b - (a + ghost.move) : 0;
  return Math.abs(ghost.move) > 0.5 || Math.abs(ghost.grow) > 0.5 || Math.abs(ghost.shift) > 0.5;
}
/** Room below the page (#main's --room), `px` more than it has, when a step needs to scroll further than the page goes;
 * none otherwise. It shrinks as you scroll back up, never past what's in view, so a page ends at its foot again. */
let roomPx = 0;
function room(px) {
  if (px <= 0) return;
  roomPx += Math.ceil(px);
  document.querySelector("#main")?.style.setProperty("--room", `${roomPx}px`);
}
/** No room below: a new page, ending at its foot. */
export function unroom() { roomPx = 0; document.querySelector("#main")?.style.removeProperty("--room"); }
addEventListener("scroll", () => {
  if (!roomPx) return;
  const natural = document.documentElement.scrollHeight - roomPx;   // (where the page ends without it)
  const keep = Math.max(0, Math.min(roomPx, Math.ceil(scrollY + innerHeight - natural)));
  if (keep !== roomPx) { roomPx = keep; document.querySelector("#main")?.style.setProperty("--room", `${roomPx}px`); }
}, { passive: true });
const html = document.documentElement.classList;
const arrivedAt = new Map();   // (pericope id -> the block a step in arrived at: stepping back out, it's the one that leaves)
function tidy() {
  for (const c of ["fw-veil", "fw-target", "fw-arrive", "fw-depart", "fw-all", "fw-headless"]) document.querySelectorAll(`.${c}`).forEach((e) => e.classList.remove(c));
  html.remove("fw-stepping", "fw-swapping");
}

// --- a step in, and a step out ----------------------------------------------------------------------------------
async function stepIn(main, frame, quote, update, dest, editor) {
  beatNo = 0; beatWay = "in";
  const step = new Step(els(main), BEAT, FADE);
  const beat = async (name, to = 1) => { await step.go(name, to); await between(name); };
  try {
    html.add("fw-stepping");
    const host = frame.parentElement;
    host.classList.add("fw-veil", "fw-headless"); quote.classList.add("fw-target");
    step.els = { ...els(main), quote };
    step.g = measure(frame, quote);
    await staggered(step, ["hide", 1], ["veil", 1]);
    if (step.g.left > 0.5 || step.g.right > 0.5) await beat("widen"); else await between("widen", "already the page's width");
    const caretWas = caretTop();   // (where on the screen the text you're at is: kept there)
    const ghost = ghostOf(frame);
    html.add("fw-swapping");   // (the new page unseen, and laid out at rest: nothing easing)
    await update();
    await tick();
    // what arrives where the ghost is: the quote showed a whole pericope, every block of it; a block, that block (the
    // rest veiled)
    const next = frameIn(main);
    const ed = editor(), whole = !(quote.dataset.target && quote.dataset.target !== dest);
    let arriving = null;
    if (whole) { host.classList.add("fw-all", "fw-arrive"); arriving = next; }
    else arriving = ed?.mark(quote.dataset.target, "fw-target fw-arrive");
    if (!arriving || !ghost.quote) { html.remove("fw-swapping"); ghost.wrap.remove(); ed?.mark(null); return; }
    arrivedAt.set(dest, whole ? "*" : quote.dataset.target);
    step.els = { ...els(main) }; step.g = null;
    const room = meet(ghost, arriving, caretWas);
    step.ghost = ghost;
    html.remove("fw-swapping");
    if (room) await beat("room"); else await between("room", "already its size, in its place");
    await beat("show");
    ghost.wrap.remove(); step.ghost = null;
    await staggered(step, ["veil", 0, "header"], ["hide", 0, "tabs"]);
    host.classList.remove("fw-headless");
    ed?.mark(null);
  } finally {
    step.end();
    tidy();
  }
}

async function stepOut(main, update, left, editor) {
  beatNo = 0; beatWay = "out";
  const step = new Step(els(main), BEAT, FADE);
  const beat = async (name, to = 1) => { await step.go(name, to); await between(name); };
  try {
    html.add("fw-stepping");
    // what leaves: what a step in arrived at (a block, or every block of the page), else every block; the rest veiled
    const was = frameIn(main), host = was?.parentElement, ed0 = editor(), at = arrivedAt.get(left) ?? "*", whole = at === "*";
    const from = whole ? was : ed0?.mark(at, "fw-target fw-depart");
    if (!from) { await update(); return; }
    host.classList.add("fw-veil", "fw-headless");
    if (whole) host.classList.add("fw-all");
    step.els = { ...els(main) };
    await staggered(step, ["hide", 1], ["veil", 1]);
    const ghost = ghostOf(was, whole);
    html.add("fw-swapping");
    await update();
    await tick();
    const frame = frameIn(main), quote = standing(frame, left);
    if (!quote || !ghost.quote) {   // (nothing on the page standing for where you were: it just appears)
      html.remove("fw-swapping"); ghost.wrap.remove(); host.classList.remove("fw-all", "fw-headless");
      await step.go("veil", 0, true); await step.go("hide", 0, true);
      return;
    }
    host.classList.remove("fw-all");
    // (where you were on this page was put back as it was drawn (main.js), before anything's measured: laid out as it'll
    // rest. Put back only at the end, the block the page opened with the cursor in kept its room until then, and losing
    // it moved the quote up after the step, further each time:)
    quote.classList.add("fw-target");
    step.els = { ...els(main), quote }; step.g = measure(frame, quote);
    await step.go("widen", 1, true);   // (as wide as the block it was)
    await tick();
    quote.style.opacity = "0"; step.arriving = quote;
    const room = meet(ghost, quote);
    step.ghost = ghost;
    html.remove("fw-swapping");
    if (room) await beat("room"); else await between("room", "already the quote's size, in its place");
    await beat("show");
    ghost.wrap.remove(); step.ghost = null;
    if (step.g.left > 0.5 || step.g.right > 0.5) await beat("widen", 0); else await between("widen", "already its own width");
    await staggered(step, ["veil", 0, "header"], ["hide", 0, "tabs"]);
    host.classList.remove("fw-headless");
  } finally {
    step.end();
    tidy();
  }
}

/** Run `update` (it changes the page from where you are, `left`, to `dest`; ids, null for home), animated: a step in
 * when a quote of `dest` is on the page, a step out when it's a step back along the trail (`back`: ⌘[, the browser's
 * back, a swipe); else it just appears. */
export async function travel(update, { dest, left, back = false, editor = () => null }) {
  const main = document.querySelector("#main"), frame = main && frameIn(main);
  const opened = frame ? pointing(frame, dest) : null;
  const dir = !back && opened?.matches(".fw-quote") ? "in" : back && dest && left ? "out" : null;   // (back: along the trail, however)
  if (OFF || reduced.matches || !dir) { await update(); last = { dir: null }; return; }
  running++;
  const swallow = (e) => { if (!(STEPPING && e.key === ".")) { e.preventDefault(); e.stopPropagation(); } };   // (no keys while it moves)
  window.addEventListener("keydown", swallow, true);
  try {
    if (dir === "in") await stepIn(main, frame, opened, update, dest, editor);
    else await stepOut(main, update, left, editor);
    last = { dir };
  } finally {
    window.removeEventListener("keydown", swallow, true);
    running--;
  }
}

// --- sent away ("a key to all pericopes to send it away off the top of the screen and go to the
// garden, its different from back and more like 'done' for now"): the page slides up off the top. On by default,
// unlike a step's motion; instant in the tests (but ?motion) and with reduced motion.
const AWAY = 280;   // ms
/** `el` (the page's pericope) slid up off the top of the screen, held there (fill) until the caller cancels it once
 * home's drawn; null when there's no motion (instant). */
export function away(el) {
  if ((TEST && !params.has("motion")) || reduced.matches || !el.animate) return null;
  const lift = Math.min(el.getBoundingClientRect().bottom, innerHeight) + 16;   // (what shows of it, all past the top)
  running++;
  const a = el.animate([{ transform: "translateY(0)" }, { transform: `translateY(${-lift}px)` }],
    { duration: AWAY, easing: "cubic-bezier(.5, 0, .75, 0)", fill: "forwards" });
  a.finished.catch(() => {}).finally(() => running--);
  return a;
}

/** After sending away: `el` (the page's pericope, a new one now) fading in, and `foot` (the suggestions, the same
 * element, staying on the page) moved from `was` (its top before) to where it is now, as one glide, not a jump. */
export function arrive(el, foot, was) {
  if ((TEST && !params.has("motion")) || reduced.matches || !el.animate) return;
  running++;
  const all = [el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: AWAY, easing: "ease-out" })];
  const dy = foot && was != null ? was - foot.getBoundingClientRect().top : 0;
  if (Math.abs(dy) > 1) all.push(foot.animate([{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }], { duration: AWAY, easing: "cubic-bezier(.3, 0, .2, 1)" }));
  Promise.all(all.map((a) => a.finished.catch(() => {}))).finally(() => running--);
}
