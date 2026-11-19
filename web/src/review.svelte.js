// review.svelte.js — reviewing a kind's maybes (the terminal's): each where it lives, selected whole, nothing typed;
// Enter yes, Backspace no, Tab skips, ⌘Z back (that answer taken back), Esc stops; then the kind again. The review
// in hand is a rune: the pericope it's at derives from it that it's being reviewed there, and what to ask.
import { api } from "./api.js";

// now: {kind, name, queue: [{block, home, title}], done: [{…, record}], yes, no, skipped}; flash: said on the next
// page opened (how a review went)
export const review = $state({ now: null, flash: "" });

/** Whether pericope `id` is where the review in hand is now. */
export const reviewingAt = (id) => !!review.now?.queue[0] && review.now.queue[0].home === id;
/** What to ask, there. */
export const reviewQuestion = () => {
  const r = review.now;
  return r?.queue[0] ? `review ${r.name}: is “${r.queue[0].title}” one?   ${r.queue.length} left   (↵ yes  ⌫ no  ⇥ skip  ⌘Z back  esc stop)` : "";
};

let goTo = () => {};
/** Kind `kind`'s maybes (named `name`) reviewed, each where it lives; `go` opens a place. */
export function startReview(kind, name, maybes, go) {
  if (!maybes?.length) return;
  goTo = go;
  review.now = { kind, name, queue: maybes.map((m) => ({ ...m })), done: [], yes: 0, no: 0, skipped: 0 };
  nextMaybe();
}
function nextMaybe() {
  const r = review.now;
  if (!r) return;
  if (!r.queue.length) {
    review.now = null;
    review.flash = `reviewed: ${r.yes} yes, ${r.no} no` + (r.skipped ? `, ${r.skipped} skipped` : "");
    goTo(`#/p/${r.kind}`);
    return;
  }
  const it = r.queue[0];
  goTo(`#/p/${it.home}` + (it.block !== it.home ? `@${it.block}` : ""));
}

/** A key while reviewing at pericope `id` (main.js listens): its answer, or a step. */
export async function reviewKey(e, id) {
  const r = review.now;
  if (!r || !reviewingAt(id) || e.target.closest?.(".fw-menu")) return;
  const key = e.key, undo = (e.metaKey || e.ctrlKey) && key === "z";
  if (!["Enter", "Backspace", "Tab", "Escape"].includes(key) && !undo) { if (key.length === 1 && !e.metaKey && !e.ctrlKey) e.preventDefault(); return; }
  e.preventDefault();
  e.stopPropagation();
  if (key === "Escape") { const k = r.kind; review.now = null; goTo(`#/p/${k}`); return; }
  if (undo) {   // back a step: its answer taken back, and there again
    const last = r.done.pop();
    if (!last) return;
    if (last.record) await api("/api/restore", { method: "POST", body: JSON.stringify({ record: last.record }) });
    if (last.answer === true) r.yes--; else if (last.answer === false) r.no--; else r.skipped--;
    r.queue.unshift(last);
    nextMaybe();
    return;
  }
  const it = r.queue.shift();
  if (key === "Tab") { r.done.push({ ...it, answer: null }); r.skipped++; nextMaybe(); return; }
  const yes = key === "Enter";
  const res = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "kind", block: it.block, kind: r.kind, answer: yes }) });
  r.done.push({ ...it, answer: yes, record: res.ok ? res.body.record : null });
  if (yes) r.yes++; else r.no++;
  nextMaybe();
}
