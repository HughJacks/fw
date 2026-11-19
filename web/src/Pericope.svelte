<!-- Pericope.svelte — a pericope open: its header (what it is, its facts, backlinks, a kind's maybes, its kinds, its
     title), the line joining it to the body, and the body, an editor over its blocks (ProseMirror: editor.js).
     Runes (the user, 2026-11-18): the pericope and the title as typed are $state; a tick counts the editor's changes;
     everything the header shows (words, updated, the title's placeholder, the title shown) is $derived from them, so
     it changes as you type with nothing redrawn by hand. The editor, the tabs, the follow are $effect. -->
<script>
  import { onDestroy, untrack } from "svelte";
  import { NodeSelection, Selection } from "prosemirror-state";
  import { api, TEST } from "./api.js";
  import { pressed } from "./keys.svelte.js";
  import { BlockEditor, selectBox } from "./editor.js";
  import { actions } from "./actions.js";
  import Kinds from "./Kinds.svelte";
  import { readClip } from "./clipboard.js";
  import { deriveTitle } from "./draft.js";
  import Tabs from "./Tabs.svelte";
  import { reviewingAt, reviewQuestion, startReview } from "./review.svelte.js";
  import { status as statusLine } from "./state.svelte.js";

  // id, at: the pericope and the block to open at; first: what the core said of it (fetched before mounting); go:
  // open a place; flash: said on opening. Home's waiting pericope (2026-11-19): no id, `first` a blank one; begun():
  // its first key (it's being made, in the background); bottom(): ↓ past its end (home's search)
  let { id: given, at, first, go, flash = "", begun = null, bottom = null } = $props();
  let id = $state(untrack(() => given));   // (the waiting pericope's comes once the core has made it)
  // a kind's maybes being reviewed here (review.svelte.js): derived from the review in hand
  let reviewing = $derived(reviewingAt(id));
  const FOLLOW = TEST ? 150 : 1000;

  const init = untrack(() => first);   // (what the core said when it opened: the start of its own state, read once)
  let p = $state(init);
  let titleSaved = $state(init.title || "");
  let titleValue = $state(init.kind ? init.shown : init.title || "");
  let tick = $state(0);   // (the editor changed: everything derived from its text again)
  let ed = null, deleted = false, pending = false, stamp = null;
  let gone = false;   // (left: an answer that comes after is for a page no longer here)
  let host = $state(), titleInput, kinds = $state();
  const picture = init.children.length === 1 && init.children[0].t === "image" && !init.children[0].id;

  // --- what the header shows: derived ---------------------------------------------------------------------------
  const ownText = (doc) => doc.textBetween(0, doc.content.size, "\n", (n) => (n.type.name === "hard_break" ? "\n" : ""));
  const words = (e) => e.view.state.doc.textBetween(0, e.view.state.doc.content.size, " ", " ").split(/\s+/).filter(Boolean).length;
  const editors = (e) => [e, ...[...e.kids].flatMap(editors)];
  let since = new Map();   // (each editor's words when the store's count was taken: what it's gained or lost since)
  let titleChanged = $derived(!p.kind && titleValue !== titleSaved);
  let auto = $derived.by(() => { tick; return p.kind ? p.shown : (ed && deriveTitle(ownText(ed.view.state.doc))) || (p.title ? "" : p.shown); });
  let shown = $derived(p.kind ? p.shown : titleValue.trim() || auto);
  let facts = $derived.by(() => {
    tick;
    let n = p.words || 0, dirty = false;
    if (ed) for (const e of editors(ed)) {
      if (e.readOnly) continue;
      const w = words(e);
      if (!since.has(e)) since.set(e, w);
      n += w - since.get(e);
      dirty ||= e.dirty();
    }
    const upd = dirty || titleChanged ? "updated just now" : p.updated && `updated ${prettyDate(p.updated)}`;
    return [`words ${n}`, upd].filter(Boolean).join("  ·  ");
  });
  function prettyDate(iso) {
    return iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";
  }
  /** The store's view of it, fresh: the header follows; the editors' words counted from here. */
  function fresh(next) {
    p = next;
    since = new Map();
    if (!titleChanged) {   // (the store's title, unless one's being written here)
      titleSaved = p.title || "";
      const v = p.kind ? p.shown : titleSaved;
      if (titleValue !== v && document.activeElement !== titleInput) titleValue = v;
    }
  }

  // --- the page says ----------------------------------------------------------------------------------------------
  function status() {
    tick++;
    if (reviewing) { statusLine.text = reviewQuestion(); return; }
    statusLine.text = ed?.message || [...(ed?.kids || [])].map((k) => k.message).find(Boolean) || "";
  }

  // --- the kinds line (Kinds.svelte): its tokens are p's, so it follows the store
  const kindsDone = async (said) => { await refresh(true); if (said) { ed.message = said; status(); } kinds?.focus(); };

  // --- the store ----------------------------------------------------------------------------------------------------
  async function refresh(headerOnly = false) {   // the store as it is now: the header always; the blocks when nothing here is unsaved
    if (!id) return;   // (waiting: nothing in the store yet)
    const asked = ed.base;
    const r = await api(`/api/pericope/${id}`);
    if (gone) return;
    if (!r.ok) { go("#/"); return; }
    if (ed.base !== asked) { pending = true; return; }   // (saved meanwhile: older than the page; ask again)
    const was = p.base;
    fresh(r.body);
    if (headerOnly) return;
    if (ed.busy() || titleChanged) { pending = true; return; }   // (written in here, or through a quote just now: later)
    pending = false;
    if (p.base === ed.base) return;
    ed.reload(p.children, p.base);
    ed.message = was !== p.base ? "updated from another session" : "";
    status();
  }
  async function rename() {   // a kind's title is its name: renamed as you leave it (refused empty, or another kind's)
    if (gone || !p.kind || titleValue.trim() === p.shown) return;
    const r = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "rename", kind: id, name: titleValue }) });
    if (!r.ok) { titleValue = p.shown; ed.message = r.body.error || "not renamed"; }
    await refresh(true);
    status();
  }
  function titleKey(e) {
    if (pressed(e, "done")) return;   // (send it away: main.js's, not ↵ here)
    if (e.key === "Enter" || e.key === "ArrowDown") { e.preventDefault(); ed.view.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); kinds?.focus(); }
  }
  function titleTyped() { if (p.kind) return; status(); if (titleChanged) ed.schedule(); }

  // --- the editor ---------------------------------------------------------------------------------------------------
  const open = (q) => {   // Open it: where the quoted block lives, at it
    const home = q.home || q.target, at2 = q.at || (home !== q.target ? q.target : null);
    go(`#/p/${home}` + (at2 ? `@${at2}` : ""));
  };
  $effect(() => untrack(() => {   // (made once: nothing it reads makes it again)
    readClip();   // (what fw last clipped: a paste here can be live quotes of it, or a move)
    const act = actions({
      root: () => ed, go, title: () => shown, gone: () => { deleted = true; },
      reload: async (selectQuote = null) => {   // the page drawn again from the store (after an action)
        const r = await api(`/api/pericope/${id}`);
        if (!r.ok || gone) return;
        fresh(r.body);
        ed.reload(p.children, p.base);
        if (selectQuote) {
          let at3 = null;
          ed.view.state.doc.descendants((n, pos) => { if (at3 === null && n.type.name === "quote" && n.attrs.id === selectQuote) at3 = pos; });
          if (at3 !== null) ed.view.dispatch(ed.view.state.tr.setSelection(NodeSelection.create(ed.view.state.doc, at3)));
        }
        ed.view.focus();
        status();
      },
    });
    ed = new BlockEditor(host, { id, children: init.children, base: init.base, readOnly: picture, open, status, act,
      top: () => titleInput.focus(),
      fields: () => (titleChanged ? { title: titleValue } : {}),   // (the title goes with the editor's next save)
      saved: (sent) => { if (sent.title !== undefined) titleSaved = sent.title; if (!sent.final) refresh(true); },
      bottom, begin: id ? null : make });
    if (!at && !reviewing) ed.roomBelow();
    ed.place(at);
    if (reviewing) ed.view.setProps({ editable: () => false });   // (reviewing: nothing types)
    ed.view.focus();
    if (flash) ed.message = flash;
    status();
    const follow = setInterval(async () => {   // changes made elsewhere, followed
      if (!id) return;
      const r = await api("/api/stamp");
      if (!r.ok || gone) return;
      if ((stamp !== null && r.body.stamp !== stamp) || (pending && !ed.busy())) await refresh();
      stamp = r.body.stamp;
    }, FOLLOW);
    const redraw = () => tick++;   // (a new width moves the boxes: the tabs with them)
    window.addEventListener("resize", redraw);
    return () => { clearInterval(follow); window.removeEventListener("resize", redraw); };
  }));

  /** Home's waiting pericope, its first key (typed in it, or its title): made in the store in the background (typing
   * never waits: the editor's saves wait for it); the address says it at once it's made, no new place on the trail. */
  function make() {
    begun?.();
    return api("/api/pericope", { method: "POST", body: JSON.stringify({ title: null }) }).then((r) => {
      if (!r.ok) return null;
      id = r.body.id;
      p = { ...p, id, base: r.body.base };
      if (!gone && ["", "#/"].includes(location.hash)) history.replaceState(history.state, "", `#/p/${id}`);   // (still home's place)
      return r.body;
    });
  }

  /** The editor (for main.js and the tests). */
  export function editor() { return ed; }
  /** Nothing in it, and no title: nothing to send away. */
  export function blank() {
    if (!ed || p.kind || titleValue.trim() || p.title) return false;
    let only = true;
    ed.view.state.doc.forEach((n) => { if (n.type.name !== "text_block" || n.textContent.trim()) only = false; });
    return only;
  }
  /** The cursor at its very end (↑ from home's search). */
  export function focusEnd() {
    ed.view.focus();
    ed.view.dispatch(ed.view.state.tr.setSelection(Selection.atEnd(ed.view.state.doc)).scrollIntoView());
  }
  /** Leaving: what's unsaved saved (the title with it; an empty, untitled pericope left behind discarded). Once:
   * asked again (sent away, then the page switching), the same leaving. */
  let leaving = null;
  export function leave() {
    return (leaving ||= (async () => {
      if (!ed) return;
      gone = true;
      if (deleted) { ed.destroy(); return; }
      await ed.leave({ final: true });
    })());
  }
  onDestroy(() => { gone = true; if (ed && !ed.gone) ed.destroy(); });
</script>

<!-- the header (the terminal's H box): what the block is, its facts, its fields, its title -->
<div class="fw-header">
  <span class="fw-gutter">H</span>
  <div class="fw-box fw-hbox">
    <div class="fw-label">{p.type}</div>
    <div class="fw-dim">{facts}</div>
    <div class="fw-fields">
      {#if p.backlinks}<div class="fw-field"><span class="fw-key">backlinks</span><span>{p.backlinks}</span></div>{/if}
      {#if p.kind && p.maybes}
        <div class="fw-field"><span class="fw-key">maybes</span>
          <button class="fw-chip fw-chip-guess" onclick={() => startReview(id, p.shown, p.maybes, go)}
            onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); startReview(id, p.shown, p.maybes, go); } else if (e.key === "ArrowDown") { e.preventDefault(); kinds?.focus(); } }}>
            {p.maybes.length ? `${p.maybes.length} · ↵ review them` : "none"}</button>
        </div>
      {/if}
      <div class="fw-field"><span class="fw-key">kinds</span>
        <Kinds bind:this={kinds} {id} tokens={p.kindTokens || []} done={kindsDone} open={(k) => go(`#/p/${k}`)} down={() => titleInput.focus()} /></div>
    </div>
    <div class="fw-field"><span class="fw-key">title</span>
      <input class="fw-input fw-title" bind:this={titleInput} bind:value={titleValue} placeholder={auto} oninput={titleTyped} onblur={rename} onkeydown={titleKey} />
    </div>
  </div>
</div>
<div class="fw-stem"></div>
<div class="fw-doc" bind:this={host}><Tabs doc={host} {tick} hidden={reviewing} pick={(box) => selectBox(ed, box)} /></div>
