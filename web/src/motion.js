// motion.js — moving around the store, animated (the user, 2026-11-18: "edits should feel instant but navigation
// should be animated so that people get a sense of moving around the store"). Every navigation goes through
// `travel`; edits never do.
//
// Built on the live elements themselves, beat by beat (Web Animations: element.animate on transforms and clips), never
// on snapshots: a picture of the page can only fade or swap, and nothing here fades but beat 2. The step, as the
// user set it out (stepping in; out is the same backwards), each beat finishing before the next:
//   1. the outermost header slides down behind the frame (no fade), the line under it drawn back with it
//   2. all text outside the opened box fades (the user, 2026-11-18: fade first, then widen)
//   3. the opened box's sides widen to the outermost frame's (the text inside stays put)
//   4. the outermost bottom border comes up to the opened box's bottom
//   5. the opened box (with that bottom) slides up to the frame's top
//   6. a stub inside (⋯, too deep) slides open, growing in height
//   7. the new page's header slides up from behind the frame
// The boxes that move are rigs drawn over the page (fixed, in screen coordinates): the opened box's border, the frame's
// border, and a veil round the opened box (beat 2's fade); the page switches under them at beat 6. Stepping out, the
// page left is copied (real elements, its .fw-doc, so it lays out as it was) to stand in while the page it's in is
// put under it and the quote standing for it is found.
//
// Which way a step goes needs no telling: if the page you're on points at where you're going, it's in; else out.
// ?beats in the address: the step stops after each beat (the bar says which) until "." is pressed. Off in the tests
// (but ?motion) and with reduced motion.
import { TEST } from "./api.js";

const params = new URLSearchParams(location.search);
// Off for now (the user, 2026-11-18: "this really isn't working all that well; keep the work but disable animations"):
// a step animates only with ?animate in the address (?animate&beats to step through it); the tests' ?motion too.
const OFF = !(params.has("animate") || (TEST && params.has("motion")));
const STEPPING = params.has("beats");
const reduced = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : { matches: true };
const BEAT = 150;   // ms a beat takes
const OVERLAP = 0.65;   // the next beat starts this far into one (the user, 2026-11-18: overlapping and quick for now;
                        // pixel-perfect later). ?beats plays each one whole.
const EASE = "cubic-bezier(.3, .7, .2, 1)";

/** What in `root` stands for pericope `id`: a quote of something in it, a link to it, its card or row; the one
 * you're at first (a quote selected whole, or written in through). */
export function pointing(root, id) {
  if (!id) return null;
  const at = `[data-pericope="${id}"]`;
  return root.querySelector(`.fw-chosen${at}, .fw-quote${at}:has(.fw-current), .fw-sel${at}`)
    || root.querySelector(`.fw-link[data-to="${id}"]`) || root.querySelector(at);
}

let running = 0;   // (steps under way: the tests' "settled" waits for them)
export let last = null;   // the last step: {dir, from, to}, what it went from and to (for the tests)
const what = (e) => (!e ? null : e.id ? `#${e.id}` : e.className.split(" ")[0]);
export const moving = () => running > 0;

/** In stepping mode (?beats): wait for "." after beat `n`, the bar saying so. */
function between(n, name) {
  if (!STEPPING) return Promise.resolve();
  const said = document.querySelector("#bar-left");
  const was = said?.textContent;
  if (said) said.textContent = ` beat ${n} of 7 done: ${name}.   press . for the next`;
  return new Promise((done) => {
    const go = (e) => {
      if (e.key !== ".") return;
      e.preventDefault();
      e.stopPropagation();
      window.removeEventListener("keydown", go, true);
      if (said) said.textContent = was;
      done();
    };
    window.addEventListener("keydown", go, true);
  });
}

// --- the pieces ----------------------------------------------------------------------------------------------
const header = (main) => main.querySelector(".fw-header");
const stem = (main) => main.querySelector(".fw-stem");
const frameOf = (main) => main.querySelector(".fw-doc > .ProseMirror");
const box = (r) => ({ left: r.left, top: r.top, width: r.width, height: r.height });
const px = (b) => ({ left: `${b.left}px`, top: `${b.top}px`, width: `${b.width}px`, height: `${b.height}px` });
const play = (e, frames) => {
  const done = e.animate(frames, { duration: BEAT, easing: EASE, fill: "forwards" }).finished;
  return STEPPING ? done : Promise.race([done, new Promise((r) => setTimeout(r, BEAT * OVERLAP))]);
};

/** A box drawn over the page (fixed, in screen coordinates), at `b`: `cls` says how (app.css: fw-rig-*). */
function rig(b, cls) {
  const e = document.createElement("div");
  e.className = `fw-rig ${cls}`;
  Object.assign(e.style, px(b));
  document.body.append(e);
  return e;
}
/** The rigs `es` moved from box `a` to box `b`, together. */
const reshape = (es, a, b) => Promise.all(es.map((e) => play(e, [px(a), px(b)])));

/** The header (and the line under it) slid down behind the frame, or (`back`) up again from there. No fade. */
async function slideHeader(main, back = false) {
  const h = header(main), s = stem(main), f = frameOf(main);
  if (!h || !f) return;
  f.style.position = "relative"; f.style.zIndex = "2";   // (the frame over the header: it goes behind; both opaque)
  h.style.position = "relative"; h.style.zIndex = "1";
  // (measured where it rests: anything holding it tucked taken off first, else rising from tucked it'd measure no way to go)
  for (const e of [h, s].filter(Boolean)) for (const a of e.getAnimations()) a.cancel();
  const down = f.getBoundingClientRect().top - h.getBoundingClientRect().top;
  const tucked = { transform: `translateY(${down}px)` }, home = { transform: "none" };
  await Promise.all([h, s].filter(Boolean).map((e) => play(e, back ? [tucked, home] : [home, tucked])));
}
/** The header (and line) put where it's tucked, at once (the new page's, before it rises). */
function hideHeader(main) {
  const h = header(main), s = stem(main), f = frameOf(main);
  if (!h || !f) return;
  f.style.position = "relative"; f.style.zIndex = "2";
  h.style.position = "relative"; h.style.zIndex = "1";
  const down = f.getBoundingClientRect().top - h.getBoundingClientRect().top;
  for (const e of [h, s].filter(Boolean)) e.animate([{ transform: `translateY(${down}px)` }], { duration: 0, fill: "forwards" });
}
/** The screen top of the first text in `el` (null: none): what a copy is lined up by, onto the same text elsewhere. */
function firstText(el) {
  if (!el) return null;
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    if (!n.data.trim()) continue;
    const r = document.createRange();
    r.setStart(n, 0); r.setEnd(n, 1);
    return r.getBoundingClientRect().top;
  }
  return null;
}
/** Block `e`'s depth: how many boxes it's inside (app.css's --d). */
const depth = (e) => parseFloat(getComputedStyle(e).getPropertyValue("--d")) || 0;
/** What an animation of `e` ended at (`to`) made its own style: so a copy of it (cloneNode) carries it, and the
 * animation can go. */
function settle(e, to) {
  for (const [k, v] of Object.entries(to)) { if (k.startsWith("--")) e.style.setProperty(k, v); else e.style[k] = v; }
  for (const a of e.getAnimations()) if (a.effect?.getKeyframes?.().some((f) => "--lift" in f || "marginLeft" in f)) a.cancel();
}
/** A clip-path showing, of a copy laid at box `d`, just box `b`. */
const clipTo = (d, b) => `inset(${b.top - d.top}px ${d.left + d.width - b.left - b.width}px ${d.top + d.height - b.top - b.height}px ${b.left - d.left}px)`;

/** Everything the step put on the page taken off again. */
function clearUp(main, rigs) {
  for (const r of rigs) r?.remove();
  for (const e of [header(main), stem(main), frameOf(main)].filter(Boolean)) {
    for (const a of e.getAnimations()) a.cancel();
    e.style.position = ""; e.style.zIndex = "";
  }
}

// --- stepping in: the beats, in order ---------------------------------------------------------------------------
async function stepIn(main, opened, update) {
  // 1. the header behind the frame
  await slideHeader(main);
  await between(1, "the header behind the frame");
  const f = box(frameOf(main).getBoundingClientRect()), q = box(opened.getBoundingClientRect());
  const frame = rig(f, "fw-rig-frame"), open = rig(q, "fw-rig-open"), veil = rig(q, "fw-rig-veil");
  opened.style.borderColor = "transparent";   // (its border is the rig's now)
  // the opened box over everything (the veil's inside is solid, so nothing of the page shows round it as it moves): the
  // header, tucked behind the frame, hidden outright (it looks the same), so the frame needn't be a layer of its own
  for (const e of [header(main), stem(main)].filter(Boolean)) e.style.visibility = "hidden";
  const fr = frameOf(main); fr.style.position = ""; fr.style.zIndex = "";
  Object.assign(opened.style, { position: "relative", zIndex: "55", background: "var(--bg)" });
  const rigs = [frame, open, veil];
  try {
    // 2. everything outside it fades (the only fade)
    await play(veil, [{ boxShadow: "0 0 0 300vmax rgba(17, 17, 17, 0)" }, { boxShadow: "0 0 0 300vmax rgba(17, 17, 17, 1)" }]);
    await between(2, "all outside it faded");
    // 3. its sides widen to the frame's, its blocks stepping out with it a tier at a time (in proportion: it becomes
    // the frame, they the frame's blocks), the text still
    const wide = { ...q, left: f.left, width: f.width };
    const fp = getComputedStyle(frameOf(main)).paddingLeft, cs = getComputedStyle(opened);
    const lifted = { marginLeft: `${f.left - q.left}px`, marginRight: `${q.left + q.width - f.left - f.width}px`,
      paddingLeft: fp, paddingRight: fp, "--lift": String(depth(opened) + 1) };
    await Promise.all([reshape([open, veil], q, wide),
      play(opened, [{ marginLeft: "0px", marginRight: "0px", paddingLeft: cs.paddingLeft, paddingRight: cs.paddingRight, "--lift": "0" }, lifted])]);
    settle(opened, lifted);
    await between(3, "its sides out to the frame's, its blocks with it");
    // 4. the frame's bottom comes up to its bottom
    const met = { ...f, height: q.top + q.height - f.top };
    await reshape([frame], f, met);
    await between(4, "the frame's bottom up to it");
    // (the new page put in now, under the cover, so where it lands can be measured: the opened box, copied as it is
    // (real elements: the old page's .fw-doc, clipped to it), stands in on top meanwhile)
    const doc = main.querySelector(".fw-doc"), d0 = box(doc.getBoundingClientRect()), was = firstText(opened);
    const copy = rig(d0, "fw-rig-copy fw-rig-copy-over");
    copy.append(doc.cloneNode(true));
    copy.style.clipPath = clipTo(d0, wide);
    rigs.push(copy);
    await update();
    window.scrollTo(0, 0);
    hideHeader(main);
    const nf = frameOf(main) ? box(frameOf(main).getBoundingClientRect()) : f;
    const now = firstText(frameOf(main)), dy = now !== null && was !== null ? now - was : nf.top - q.top;
    // 5. it (and that bottom) slides up to the new page's frame: its text onto the new page's same text, exactly
    const up = { left: nf.left, width: nf.width, top: q.top + dy, height: q.height };
    await Promise.all([reshape([open, veil, frame], { ...wide, top: q.top }, up),
      play(copy, [{ transform: "none" }, { transform: `translateY(${dy}px)` }])]);
    await between(5, "up to the frame's top");
    // 6. the copy hands over to the new page, in place; the box grows down to the page's length, revealing what the
    // opened box didn't show (a stub, opened)
    veil.style.background = "transparent";
    copy.remove();
    const grown = { ...nf, height: Math.min(nf.height, window.innerHeight - nf.top) };
    await reshape([open, veil, frame], up, grown);
    open.style.borderColor = "var(--frame)";
    await between(6, "the new page, grown to its length");
    // 7. the new header slides up from behind the frame
    for (const r of rigs) r.remove();
    await slideHeader(main, true);
  } finally {
    clearUp(main, rigs);
    Object.assign(opened.style, { position: "", zIndex: "", background: "", borderColor: "", transform: "",
      marginLeft: "", marginRight: "", paddingLeft: "", paddingRight: "" });
    opened.style.removeProperty("--lift");
  }
}

// --- stepping out: the same beats, backwards ---------------------------------------------------------------------
async function stepOut(main, update, left) {
  // 7. the header behind the frame
  await slideHeader(main);
  await between(7, "the header behind the frame");
  // (the page left, copied as it is: real elements, standing in for it while the page it's in is put under it)
  const doc = main.querySelector(".fw-doc"), f0 = box(frameOf(main).getBoundingClientRect()), d0 = box(doc.getBoundingClientRect());
  const shown = { ...f0, height: Math.min(f0.height, window.innerHeight - Math.max(f0.top, 0)) };
  const copy = rig(d0, "fw-rig-copy");
  copy.append(doc.cloneNode(true));
  const frame = rig(shown, "fw-rig-frame"), open = rig(shown, "fw-rig-open"), veil = rig(shown, "fw-rig-veil");
  veil.style.boxShadow = "0 0 0 300vmax rgba(17, 17, 17, 1)";
  veil.style.background = "transparent";   // (the copy, under it, has its own: seen through its inside)
  open.style.borderColor = "var(--frame)";
  const rigs = [copy, frame, open, veil];
  const clip = (b) => ({ clipPath: `inset(${b.top - d0.top}px ${d0.left + d0.width - b.left - b.width}px ${d0.top + d0.height - b.top - b.height}px ${b.left - d0.left}px)` });
  copy.style.clipPath = clip(shown).clipPath;
  try {
    await update();   // (the page it's in, under the cover, the quote standing for it on screen)
    hideHeader(main);
    const quote = pointing(main, left);
    quote?.scrollIntoView({ block: "nearest" });
    const nf = frameOf(main);
    if (!quote || !nf) return;
    const q = box(quote.getBoundingClientRect()), f = box(nf.getBoundingClientRect());
    quote.style.visibility = "hidden";   // (the copy stands for it until it's back in place)
    open.style.borderColor = "";
    // 6. it shrinks to the quote's height (what was a stub there, closed)
    const short = { ...shown, height: q.height };
    await Promise.all([reshape([open, veil, frame], shown, short), play(copy, [clip(shown), clip(short)])]);
    await between(6, "down to the quote's height");
    // 5. it slides down (or up) to where the quote is
    const there = { ...short, top: q.top }, dy = q.top - short.top;
    await Promise.all([reshape([open, veil, frame], short, there), play(copy, [{ transform: "none", ...clip(short) }, { transform: `translateY(${dy}px)`, ...clip(short) }])]);
    await between(5, "to the quote's place");
    // 4. the frame's bottom goes down to the page's
    await reshape([frame], there, { ...f, height: Math.min(f.height, window.innerHeight - f.top + 400) });
    await between(4, "the frame's bottom down");
    // 3. its sides narrow to the quote's, its blocks stepping in with it a tier at a time (in proportion: the frame
    // becomes the quote, its blocks the quote's), the text still
    const narrow = { ...there, left: q.left, width: q.width }, moved = (b) => ({ ...b, top: b.top - dy });
    const pm = copy.querySelector(".fw-doc > .ProseMirror"), pc = getComputedStyle(pm), qc = getComputedStyle(quote);
    await Promise.all([reshape([open, veil], there, narrow),
      play(copy, [{ transform: `translateY(${dy}px)`, ...clip(moved(there)) }, { transform: `translateY(${dy}px)`, ...clip(moved(narrow)) }]),
      play(pm, [{ marginLeft: pc.marginLeft, marginRight: pc.marginRight, paddingLeft: pc.paddingLeft, paddingRight: pc.paddingRight, "--lift": "0" },
        { marginLeft: `${parseFloat(pc.marginLeft) + q.left - there.left}px`, marginRight: `${parseFloat(pc.marginRight) + there.left + there.width - q.left - q.width}px`,
          paddingLeft: qc.paddingLeft, paddingRight: qc.paddingRight, "--lift": String(-(depth(quote) + 1)) }])]);
    await between(3, "its sides in to the quote's");
    // 2. what's around it fades in
    await play(veil, [{ boxShadow: "0 0 0 300vmax rgba(17, 17, 17, 1)" }, { boxShadow: "0 0 0 300vmax rgba(17, 17, 17, 0)" }]);
    quote.style.visibility = "";
    for (const r of rigs) r.remove();
    await between(2, "what's around it back");
    // 1. the header slides up
    await slideHeader(main, true);
  } finally {
    clearUp(main, rigs);
    main.querySelectorAll("[style*='visibility']").forEach((e) => { e.style.visibility = ""; });
  }
}

/** Run `update` (it changes the page from where you are, `left`, to `dest`; ids, null for home), animated. */
export async function travel(update, { dest, left }) {
  const main = document.querySelector("#main");
  const from = pointing(main, dest), dir = from ? "in" : "out";
  const record = () => { last = { dir, from: dir === "in" ? what(from) : "body", to: dir === "in" ? "body" : what(pointing(main, left)) }; };
  // (nothing on screen to move from, a first load or home; or a step home: the page just appears)
  if (OFF || reduced.matches || !header(main) || !frameOf(main) || (dir === "out" && !dest)) { await update(); record(); return; }
  running++;
  document.documentElement.classList.add("fw-stepping");   // (the numbers and ↗ hidden while it moves: app.css)
  try {
    if (dir === "in") await stepIn(main, from, update);
    else await stepOut(main, update, left);
    record();
  } finally {
    running--;
    document.documentElement.classList.remove("fw-stepping");
  }
}

// --- sent away (the user, 2026-11-19: "a key to all pericopes to send it away off the top of the screen and go to the
// garden, its different from back and more like 'done' for now"): the page slides up off the top. On by default,
// unlike a step's motion; instant in the tests (but ?motion) and with reduced motion.
const AWAY = 280;   // ms
/** `el` (the page's #main) slid up off the top of the screen, held there (fill) until the caller cancels it once
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
