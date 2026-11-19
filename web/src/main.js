// main.js — fw's web editor, the page. Two views, as the terminal's: home (the garden, and the search
// typing hands over to) and a pericope open in the editor. The page never touches the store: it asks the
// core (fw_web.py) for JSON and saves drafts back. Typing never waits on it: every key changes the
// document here, and saves go out in the background once the keys stop.
import { waiting } from "./editor.js";
import { readClip } from "./clipboard.js";
import { loadKeys, pressed } from "./keys.js";
import { api, TEST, inflight } from "./api.js";
import { travel, moving } from "./motion.js";
import * as motion from "./motion.js";
import { NodeSelection, TextSelection, Selection } from "prosemirror-state";
import { mount, tick } from "svelte";
import App from "./App.svelte";
import { status as statusLine, ui, page } from "./state.svelte.js";
import { review, reviewKey } from "./review.svelte.js";

// the page's shell (Svelte 5, runes: App.svelte): what the page says at the top, the view below
mount(App, { target: document.querySelector("#app") });


// --- what the page says (at the top, App.svelte; the old bottom bar's key hints are gone, 2026-11-18) ----------
function bar(text) {
  statusLine.text = text.trim();
}

// --- routing: #/ home, #/p/<id>[@<block>] a pericope (at a block) -----------------
function route() {
  if (location.hash === "#/keys") return { view: "keys" };
  const m = location.hash.match(/^#\/p\/([^@]+)(?:@(.+))?$/);
  return m ? { view: "pericope", id: m[1], at: m[2] || null } : { view: "home" };
}
const go = (hash) => { if (location.hash !== hash) location.hash = hash; else show(); };
// the trail: each place this tab has been numbered in its history (history.state.n), so ⌘[ steps out only
// within fw, never back past where it started
let here = -1;
function placed() {   // (a place not seen yet: one further along than where we came from; the first, 0)
  const fresh = history.state?.n == null;
  if (fresh) history.replaceState({ n: here + 1 }, "");
  here = history.state.n;
}
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
      placed();
      const r = route(), dest = r.view === "pericope" ? r.id : null;
      // (moved there, animated: stepping in or out, motion.js)
      await travel(async () => {
        const was = current;
        current = null;
        if (was) await was.leave();
        current = r.view === "pericope" ? await openPericope(r.id, r.at) : r.view === "keys" ? await openKeys() : await openHome();
        shown = dest;
      }, { dest, left: shown });
    } finally {
      switches--;
    }
  };
  switching = switching.then(next, next);
  return switching;
}
window.addEventListener("hashchange", show);

/** View `kind` drawn in #main with `props` (App.svelte), once Svelte has drawn it: {leave(), editor}. */
async function open(kind, props) {
  page.instance = null;
  page.view = { kind, props };
  await tick();
  const it = page.instance;
  return { get editor() { return it?.editor?.() || null; }, leave: async () => { await it?.leave?.(); }, blank: () => it?.blank?.() ?? true };
}

// --- home: Home.svelte (the search, the garden, the library) ------------------------------------------------------
const openHome = () => open("home", { go });

// --- reviewing a kind's maybes: review.svelte.js (its keys, while it's at the pericope open) ------------------------
document.addEventListener("keydown", (e) => reviewKey(e, current?.editor?.id), true);

// --- a pericope -------------------------------------------------------------------
async function openPericope(id, at) {   // Pericope.svelte (its header, the body's editor), once the core has said what it is
  const r = await api(`/api/pericope/${id}`);
  if (!r.ok) { go("#/"); return { leave: async () => {} }; }
  const flash = review.flash;
  review.flash = "";
  return open("pericope", { id, at, first: r.body, go, flash });
}

// --- for the tests (web/test): when the page has settled, and the cursor put where a test wants it ---------------
// (as the terminal's $FW_SYNC markers: tests wait on these, not on fixed sleeps)
window.fw = {
  /** Nothing in flight: no request to the core, no save waiting to go, no page switching. */
  settled: () => inflight.n === 0 && waiting.size === 0 && switches === 0 && !moving(),
  /** The cursor at the very end of the open pericope. */
  end() {
    const v = current?.editor?.view;
    if (!v) return false;
    v.focus();
    v.dispatch(v.state.tr.setSelection(Selection.atEnd(v.state.doc)));
    return true;
  },
  /** The last move (motion.js): which way, what zoomed from and to. */
  lastMove: () => motion.last,
  /** A quote (any atom) at `pos` selected whole, for a test to act on. */
  nodeSel: (doc, pos) => NodeSelection.create(doc, pos),
  /** The open pericope's editor (at home, the waiting pericope's; null on the keys page). */
  editor: () => current?.editor || null,
  /** Home is the view open (its waiting pericope written in or not). */
  home: () => page.view?.kind === "home",
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

// --- always the latest (the user, 2026-11-18): the core rebuilds the page and restarts itself when the code changes;
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
  if (!window.fw.settled() || document.querySelector(".fw-menu, .fw-masking") || review.now) return;   // (later: nothing lost)
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
});

// --- send it away (the user, 2026-11-19: "a key to all pericopes to send it away off the top of the screen and go to
// the garden, its different from back and more like 'done' for now"): saved, slid up off the top (motion.js away), then
// home, a fresh waiting pericope. Home is a new place on the trail, so ⌘[ still reaches what was sent away. On a
// blank pericope (empty, untitled), nothing.
async function sendAway() {
  if (!current?.editor || switches || document.querySelector(".fw-menu, .fw-masking")) return;
  if (current.blank()) { bar("nothing here to send away"); return; }
  const main = document.querySelector("#main"), ed = current.editor;
  ed.view.setProps({ editable: () => false });   // (nothing typed into what's going)
  const slide = motion.away(main);
  // saved as it goes (not left yet: leaving takes the editor down, and it's still sliding); left once it's gone, below
  await Promise.all([slide?.finished.catch(() => {}), ed.saveAll()]);
  history.pushState(null, "", "#/");   // (a new place: ⌘[ steps back to it)
  await show();
  slide?.cancel();   // (home drawn under it: the page back where it was)
}

// --- the keys page (#/keys): Keys.svelte -----------------------------------------------------------------------------
async function openKeys() {
  const it = await open("keys", { home: () => go("#/") });
  bar("");
  return it;
}
window.addEventListener("beforeunload", () => { if (current) current.leave(); });
window.addEventListener("focus", () => readClip());   // (clipped in another window, or the terminal, since)
loadKeys().finally(show);   // (the user's keys first: the editors' keymaps are made from them)
