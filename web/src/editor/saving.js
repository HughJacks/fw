// saving.js — BlockEditor's saves and following the store: every change saved as it's made, one save in flight at a
// time, each with all that's changed by then (PUT /api/pericope/<id>, or /api/lens/<quote> through a mask); what the
// store holds now taken in as one step, the cursor and undo carried through it.
import { ui } from "../state/state.svelte.js";
import { api, TEST } from "../lib/api.js";
import { draftOf, lensOf } from "./draft.js";
import { wordsIn } from "./here.js";

const RETRY = TEST ? 150 : 1000;       // ms: a save the store refused, tried again
export const waiting = new Set();     // the editors with a save scheduled, not yet begun (the tests' "settled")

export const saving = {
  draft() {
    if (this.readOnly) return null;
    return this.lens ? lensOf(this.view.state.doc.toJSON(), this.lens.hole) : draftOf(this.view.state.doc.toJSON());
  },
  dirty() { return this.draft() !== this.saved; },
  /** Busy: unsaved or saving here or in a quote it holds, or a menu open (positions in use); then what changed elsewhere
   * waits, for a moment. Being in it isn't busy: a view follows the store while you're in it (reload). */
  busy() {
    return this.dirty() || this.saving || ui.menus > 0 || [...this.kids].some((k) => k.busy());
  },

  schedule() {
    if (!this.id && this.begin && !this.making) {   // the first change to a pericope not made yet: made now, typing never waiting
      this.making = this.begin().then((made) => { if (made) Object.assign(this, { id: made.id, base: made.base }); else this.making = null; },
        () => { this.making = null; });
    }
    clearTimeout(this.timer);
    waiting.add(this);
    this.timer = setTimeout(() => { waiting.delete(this); this.save(); }, 0);
  },

  /** It and every quote's editor in it, saved. */
  async saveAll() {
    for (const k of this.kids) await k.saveAll();
    await this.save();
  },

  /** Saved into its block: the draft, with what the header has changed (fields()) and whatever `extra` (final). One
   * save at a time: another asked for meanwhile waits for it, then goes (never dropped). */
  async save(extra = {}) {
    if (!this.id) {   // (not made yet: nothing to save into until it is; never made, nothing written)
      if (!this.making) return true;
      await this.making;
      if (!this.id) { if (!this.gone) this.schedule(); return false; }
    }
    while (this.saving) await this.saving;
    extra = { ...this.fields(), ...extra };
    const more = Object.keys(extra).length;
    if (this.readOnly && !more) return true;
    if (!this.dirty() && !more) return true;
    let done;
    this.saving = new Promise((r) => { done = r; });
    const sent = this.draft();
    // (nothing changed here: no draft, so the store's blocks stay as they are; the save is for `extra`)
    const draft = this.dirty() ? sent : null;
    const body = this.lens ? { text: sent, base: this.base, version: this.version }
      : { draft, base: this.base, version: this.version, also: this.around.map((e) => e.id), ...extra };
    let r;
    try {
      r = await api(this.lens ? `/api/lens/${this.lens.qid}` : `/api/pericope/${this.id}`, { method: "PUT", body: JSON.stringify(body) });
    } finally {
      this.saving = null;
      done();
    }
    if (r.ok) {
      this.base = this.lens ? (r.body.bases || {})[this.id] || this.base : r.body.base;
      this.version = r.body.version ?? this.version;   // (what it wrote, on what it saw: after a merge, it follows the rest)
      this.saved = sent;
      for (const e of this.around) if (r.body.bases && r.body.bases[e.id]) e.base = r.body.bases[e.id];   // (their shown text changed)
      this.message = (r.body.notes || []).slice(-1)[0] || "";
      this.onSaved(extra);
      this.status();
      return r.body;
    }
    this.message = r.body.error || "the core isn't answering: your writing is here, and goes through when it does";
    this.status();
    if (!this.gone) setTimeout(() => this.save(), RETRY);
    return false;
  },

  /** Its quotes kept live (its own blocks unchanged): `children` as the core has them now; a quote whose source changed
   * elsewhere redrawn, just it (its editor, when written through; else the whole); one being written in left till it
   * isn't. Never anything it wrote itself: its saves keep its quotes' bases up. */
  followQuotes(children, version) {
    const now = new Map();
    const walk = (n) => { if (!n) return; if (n.t === "quote") { now.set(n.id, n); (n.tree || []).forEach(walk); } else (n.children || []).forEach(walk); };
    (children || []).forEach(walk);
    let whole = false;
    const visit = (e) => {
      for (const k of e.kids) {
        if (k.holder?.node.attrs.data?.expr) continue;   // (a call's result: it follows the snapshot)
        const q = now.get(k.holder?.node.attrs.id);
        if (q && q.base && q.base !== k.base && !k.busy()) { if (k.lens || !q.tree) whole = true; else k.reload(q.tree, q.base, version); }
        else visit(k);
      }
    };
    visit(this);
    this.view.state.doc.descendants((n, pos) => {   // (a quote drawn from its data, nothing written through it: a locked one, say)
      if (n.type.name !== "quote" || !n.attrs.data) return;
      const q = now.get(n.attrs.id);
      if (n.attrs.data.expr) {   // (a call: its result follows the snapshot, its code the store)
        const here = this.view.nodeDOM(pos)?.fwCall?.source ?? n.attrs.data.expr.source;
        if (q?.expr && q.expr.source !== here) whole = true;
        return;
      }
      if (n.attrs.data.tree || n.attrs.data.lens) return;
      if (q && q.base && n.attrs.data.base && q.base !== n.attrs.data.base) whole = true;
    });
    if (whole && !this.busy()) this.reload(children, this.base, version);
  },

  /** What it holds as the store now has it (nothing unsaved here): just what differs changed, as one step, so the
   * cursor, a selection and undo are carried through it; quotes whose node is the same keep their views. */
  reload(children, base, version) {
    if (this.view.isDestroyed) return;
    if (version !== undefined) this.version = version;   // (first: the quotes drawn new in it take it)
    window.fw && (window.fw.reloads = (window.fw.reloads || 0) + 1);   // (counted, for the tests' reports)
    const now = this.view.state.doc, next = this.make(children).doc;
    const from = now.content.findDiffStart(next.content);
    if (from !== null) {
      let { a, b } = now.content.findDiffEnd(next.content);
      const over = from - Math.min(a, b);   // (a repeated stretch: the ends found past the start)
      if (over > 0) { a += over; b += over; }
      this.view.dispatch(this.view.state.tr.replace(from, a, next.slice(from, b)).setMeta("fw-follow", true).setMeta("fw-value", true).setMeta("addToHistory", false));
      this.giveIds();
    }
    this.since = wordsIn(this.view.state.doc);
    this.base = base;
    this.saved = this.draft();
  },
};
