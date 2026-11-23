// visits.js — your attention, told to the core (POST /api/visit), which keeps it as visits as the terminal editor does
// (fw_block.attend) and writes them when they end (2026-11-20: the web editor recorded none, and home's memory and
// "where you went next" are read from them). Any key or click in a pericope: attention on it ("o"). The block the
// cursor's in counts once it's stayed DWELL or been written in ("c", "w"; "q" through a quote), and each key in it
// after that keeps its visit going. The same thing is told at most every AGAIN; the core counts in minutes.
import { api, TEST } from "./api.js";

const DWELL = TEST ? 300 : 3000;   // ms: the core's VISIT_DWELL
const AGAIN = 20000;               // ms: the same attention told again at most this often
let here = null;                   // {block, since, counted, through, timer}: the block the cursor's in
let lastInput = 0;
const told = new Map();            // what was told, when

function tell(body, key = null) {
  const now = Date.now();
  if (key && now - (told.get(key) || 0) < AGAIN) return;
  if (key) told.set(key, now);
  if (TEST) (window.fwVisits ||= []).push(body);
  api("/api/visit", { method: "POST", body: JSON.stringify(body) });
}
const pericopeOf = (ed) => (ed.around?.at(-1) || ed).id;
function blockOf(ed) {
  const { $from } = ed.view.state.selection;
  for (let d = $from.depth; d > 0; d--) if ($from.node(d).type.name === "text_block") return $from.node(d).attrs.id;
  return null;
}
function count(wrote) {
  const flags = "c" + (wrote ? "w" : "") + (here.through ? "q" : "");
  const ago = here.counted ? 0 : (Date.now() - here.since) / 1000;
  here.counted = true;
  tell({ block: here.block, flags, ago }, flags + here.block);
}

/** A pericope opened (or come back to): attention on it. */
export function opened(id) {
  if (here?.timer) clearTimeout(here.timer);
  here = null;
  if (id) tell({ pericope: id }, null);
}
/** Left it: whatever's under way, written. */
export function left() {
  if (here?.timer) clearTimeout(here.timer);
  here = null;
  told.clear();
  tell({ flush: true });
}
/** A key, a click, an input in editor `ed` (`wrote`: it changed the text): looked at once it's taken effect. */
export function input(ed, wrote = false) {
  lastInput = Date.now();
  setTimeout(() => {
    const p = pericopeOf(ed);
    if (!p || ed.gone) return;
    tell({ pericope: p }, "o" + p);
    const block = blockOf(ed);
    if (!block) { if (here?.timer) clearTimeout(here.timer); here = null; return; }
    if (!here || here.block !== block) {
      if (here?.timer) clearTimeout(here.timer);
      here = { block, since: Date.now(), counted: false, through: !!ed.exit, timer: null };
      here.timer = setTimeout(() => { if (here?.block === block && !here.counted) count(false); }, DWELL);
    }
    if (wrote || here.counted) count(wrote);
  }, 0);
}
/** The document changed: written in, if it came of a key or input just now (not the store's own redraw). */
export function changed(ed) { if (Date.now() - lastInput < 250) input(ed, true); }
