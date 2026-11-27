// main.js — fw's web editor, the page: one page, App.svelte, drawn from where you are
// (state.svelte.js `here`, `where` here), which the address sets (the routing: #/ home, #/p/<id>[@<block>] a pericope, #/keys, #/kinds).
// One pericope on it, header and body, for every pericope; moving only changes what it shows. The page never
// touches the store: it asks the core (fw_web.py) for JSON and saves drafts back. Typing never waits on it: every
// key changes the document here, and saves go out in the background after every change (one at a time, each with all that changed by then).
import { waiting, spotOf, restoreSpot } from "./editor/editor.js";
import { readClip } from "./editor/clipboard.js";
import * as visits from "./lib/visits.js";
import { loadKeys, pressed } from "./lib/keys.js";
import { api, TEST, inflight } from "./lib/api.js";
import { travel, moving } from "./lib/motion.js";
import * as motion from "./lib/motion.js";
import { NodeSelection, TextSelection, Selection } from "prosemirror-state";
import { mount, tick } from "svelte";
import App from "./ui/App.svelte";
import { say, ui, here as where } from "./state/state.svelte.js";
import { review, reviewKey } from "./state/review.svelte.js";

// the page (Svelte 5, runes: App.svelte): what the page says at the top, the one pericope, home's parts below it
const app = mount(App, { target: document.querySelector("#app"), props: { go: (hash, how) => go(hash, how) } });


// --- what the page says (at the top, App.svelte; the old bottom bar's key hints are gone) ----------
function bar(text) {
  say(text.trim());
}

// --- routing: #/ home, #/p/<id>[@<block>] a pericope (at a block) -----------------
function route() {
  if (location.hash === "#/keys") return { view: "keys" };
  if (location.hash === "#/tags" || location.hash === "#/kinds") return { view: "kinds" };   // (the tags view; #/kinds its old address)
  const m = location.hash.match(/^#\/p\/([^@]+)(?:@([^~]+))?(?:~(\d+))?$/);
  return m ? { view: "pericope", id: m[1], at: m[2] || null, off: m[3] != null ? +m[3] : null } : { view: "home" };
}
let arriving = {};   // (how the next place opened arrives: {quiet}, from go's second argument)
const go = (hash, how = {}) => { arriving = how; if (location.hash !== hash) location.hash = hash; else show(); };
// the trail: each place this tab has been numbered in its history (history.state.n), so ⌘[ steps out only
// within fw, never back past where it started
let here = -1;
function placed() {   // (a place not seen yet: one further along than where we came from; the first, 0). Returns whether it's new.
  const fresh = history.state?.n == null;
  if (fresh) history.replaceState({ n: here + 1 }, "");
  here = history.state.n;
  return fresh;
}
// ⌘[ and ⌘] (any step back or forward along the trail) land exactly where you were ("command
// bracket [ and ] should navigate you to exactly the place and cursor status you came from"): each place keeps, as you
// leave it, where you were in it (editor.js spotOf: the caret, text selected, blocks selected whole, nothing drawn) and
// how far down it was scrolled, both put back once it's drawn again (a step's motion then moves from there). The scroll
// is the page's own: the browser's restoration, on back and forward, moved the page before a step out had measured it.
// Kept by the trail's number (history.state.n); a reload keeps them in history.state.
history.scrollRestoration = "manual";
const kept = new Map();   // (history.state.n -> {y, spot})
const keep = () => ({ y: scrollY, spot: spotOf(current?.editor) });
window.addEventListener("beforeunload", () => history.replaceState({ ...history.state, ...keep() }, ""));
const back = () => { if (here > 0) history.back(); };
const forward = () => history.forward();

let current = null;   // the open view: { leave() } (saves what's unsaved)
let shown = null;     // the pericope open now (null: home)
let switching = Promise.resolve(), switches = 0;
/** The view the address names, after the one open has left (saved): one switch at a time, in order. */
function show() {
  const next = async () => {
    switches++;
    try {
      const from = here;
      if (from >= 0) kept.set(from, keep());
      const fresh = placed(), asLeft = fresh ? null : kept.get(here) ?? history.state ?? null;
      const backward = here < from;   // (a step back along the trail: ⌘[, the browser's back, a swipe; motion.js steps out)
      const r = route(), dest = r.view === "pericope" ? r.id : null;
      motion.unroom();   // (a step's room below is the page it was made for)
      // (moved there, animated: stepping in or out, motion.js)
      await travel(async () => {
        const was = current;
        current = null;
        if (was) { await was.leave(); visits.left(); }
        const how = arriving; arriving = {};
        current = r.view === "pericope" ? await openPericope(r.id, r.at, r.off, how) : r.view === "keys" ? await openKeys()
          : r.view === "kinds" ? await openKindsView() : await openHome();
        if (r.view === "pericope") visits.opened(r.id);
        shown = dest;
        if (asLeft) { restoreSpot(current?.editor, asLeft.spot); if (asLeft.y != null) scrollTo(0, asLeft.y); }   // (back or forward: as it was left)
      }, { dest, left: shown, back: backward, editor: () => current?.editor });
    } finally {
      switches--;
    }
  };
  switching = switching.then(next, next);
  return switching;
}
window.addEventListener("hashchange", show);

/** Where you are now `view`, the page's pericope showing `opening` (App.svelte draws it; nothing's made again but
 * the pericope's editor), once Svelte has drawn it: {leave(), editor, blank()}, the pericope open. */
async function place(view, opening) {
  where.view = view;
  where.written = false;
  where.opening = opening;
  await tick();
  const peri = app.pericope();
  if (!opening) return { editor: null, leave: async () => {}, blank: () => true };
  return { get editor() { return peri?.editor() || null; }, leave: async () => { await peri?.leave(); }, blank: () => peri?.blank() ?? true };
}

// --- home: the waiting pericope (blank: nothing's made until its first key), and Suggested.svelte under it --------------
const BLANK = { id: null, title: null, shown: "", type: "pericope", kind: false, words: 0, created: null, updated: null, visited: null, kinds: "",
  kindTokens: [], maybes: null, backlinks: "", base: null, children: [] };
const openHome = () => place("home", { id: null, at: null, first: BLANK, home: true });

// --- reviewing a kind's maybes: review.svelte.js (its keys, while it's at the pericope open) ------------------------
document.addEventListener("keydown", (e) => reviewKey(e, current?.editor?.id), true);

// --- a pericope -------------------------------------------------------------------
async function openPericope(id, at, off = null, how = {}) {   // Pericope.svelte (its header, the body's editor), once the core has said what it is
  const r = await api(`/api/pericope/${id}`);
  if (!r.ok) { go("#/"); return { leave: async () => {} }; }
  const flash = review.flash;
  review.flash = "";
  return place("pericope", { id, at, off, quiet: !!how.quiet, first: r.body, flash });
}

// --- for the tests (web/test): when the page has settled, and the cursor put where a test wants it ---------------
// (as the terminal's $FW_SYNC markers: tests wait on these, not on fixed sleeps)
window.fw = {
  /** Nothing in flight: no request to the core, no save waiting to go, no page switching. */
  settled: () => inflight.n === 0 && waiting.size === 0 && switches === 0 && !moving(),
  /** The cursor at the very end of the open pericope (ending with a quote or picture: in the block below it, made as
   * going down past it makes it). */
  end() {
    const ed = current?.editor, v = ed?.view;
    if (!v) return false;
    v.focus();
    v.dispatch(v.state.tr.setSelection(Selection.atEnd(v.state.doc)));
    ed.roomBelow();
    return true;
  },
  /** The last move (motion.js): which way, what zoomed from and to. */
  lastMove: () => motion.last,
  /** A quote (any atom) at `pos` selected whole, for a test to act on. */
  nodeSel: (doc, pos) => NodeSelection.create(doc, pos),
  /** The open pericope's editor (at home, the waiting pericope's; null on the keys page). */
  editor: () => current?.editor || null,
  /** Home is the view open (its waiting pericope written in or not). */
  home: () => where.view === "home",
  /** `text` selected (its `nth` place) in the open pericope, the cursor at its end if `collapse`; in an editor of
   * a quote inside when that's where it is. Returns whether it was found. */
  select(text, { collapse = false, start = false, nth = 0 } = {}) {
    const eds = [], add = (e) => { eds.push(e); for (const k of e.kids) add(k); };
    if (current?.editor) add(current.editor);
    for (const e of eds) {
      let at = null, seen = 0;
      e.view.state.doc.descendants((n, pos) => {
        if (at !== null || !n.isText) return;
        const i = n.text.indexOf(text);
        if (i >= 0 && seen++ === nth) at = pos + i;
      });
      if (at === null) continue;
      const from = collapse ? (start ? at : at + text.length) : at, to = collapse ? from : at + text.length;
      e.view.focus();
      e.view.dispatch(e.view.state.tr.setSelection(TextSelection.create(e.view.state.doc, from, to)));
      return true;
    }
    return false;
  },
};

// --- always the latest: the core rebuilds the page and restarts itself when the code changes;
// the page notices (GET /api/version) and reloads itself, once nothing's waiting to save and nothing's open over
// the text (a menu, masking), back at the block it was in. Not in the tests (?test).
let running = null;
async function latest() {
  if (TEST) return;
  const r = await api("/api/version").catch(() => null);
  if (!r || !r.ok) return;   // (the core starting again: next time)
  const now = `${r.body.code}/${r.body.page}`;
  if (running === null) { running = now; return; }
  if (now === running) return;
  if (!window.fw.settled() || ui.menus || review.now) return;   // (later: nothing lost)
  const ed = current?.editor, block = ed?.context()?.block?.id;
  const m = location.hash.match(/^#\/p\/([^@]+)/);
  if (m && block && ed.id === m[1]) history.replaceState(history.state, "", `#/p/${m[1]}@${block}`);
  location.reload();
}
if (!TEST) setInterval(latest, 1000);

// home, and the keys page, from anywhere (keys.js; the terminal's ^Q went home)
document.addEventListener("keydown", (e) => {
  if (document.querySelector(".fw-ask") || ui.capturing) return;
  if (pressed(e, "back")) { e.preventDefault(); back(); }
  else if (pressed(e, "forward")) { e.preventDefault(); forward(); }
  else if (pressed(e, "home")) { e.preventDefault(); go("#/"); }
  else if (pressed(e, "done")) { e.preventDefault(); sendAway(); }
  else if (pressed(e, "keys")) { e.preventDefault(); go("#/keys"); }
  else if (pressed(e, "kinds")) { e.preventDefault(); go("#/tags"); }
});

// --- send it away ("a key to all pericopes to send it away off the top of the screen and go to
// the garden, its different from back and more like 'done' for now"): saved, the pericope (only it:
// "fly away only the pericope and fade in a new one, suggested should stay where it is") slid up off the
// top (motion.js away), then home, a fresh waiting pericope fading in where it was, the suggestions below staying on
// the page (gliding to where home puts them, if that's elsewhere) and following it. Home is a new place on the trail,
// so ⌘[ still reaches what was sent away. On a blank pericope (empty, untitled), nothing.
async function sendAway() {
  if (!current?.editor || switches || ui.menus) return;
  if (current.blank()) { bar("nothing here to send away"); return; }
  const peri = document.querySelector("#main .fw-peri"), ed = current.editor;
  ed.view.setProps({ editable: () => false });   // (nothing typed into what's going)
  const slide = motion.away(peri);
  // saved as it goes (not left yet: leaving takes the editor down, and it's still sliding); left once it's gone, below
  await Promise.all([slide?.finished.catch(() => {}), ed.saveAll()]);
  const foot = document.querySelector("#main .fw-suggested"), was = foot?.getBoundingClientRect().top;
  history.pushState(null, "", "#/");   // (a new place: ⌘[ steps back to it)
  await show();
  slide?.cancel();
  if (slide) motion.arrive(peri, foot, was);   // (the new one fading in; the suggestions from where they were)
}

// --- the keys page (#/keys): Keys.svelte -----------------------------------------------------------------------------
async function openKeys() {
  const it = await place("keys", null);
  bar("");
  return it;
}
// --- the kinds view (#/kinds): KindsView.svelte -------------------------------------------------------------------------
async function openKindsView() {
  const it = await place("kinds", null);
  bar("");
  return it;
}
window.addEventListener("beforeunload", () => { if (current) current.leave(); });
window.addEventListener("focus", () => readClip());   // (clipped in another window, or the terminal, since)
loadKeys().finally(show);   // (the user's keys first: the editors' keymaps are made from them)
