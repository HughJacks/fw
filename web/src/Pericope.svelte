<!-- Pericope.svelte — the pericope open: its header (Header.svelte), the line joining it to the body, and the body
     (Body.svelte), an editor over its blocks (ProseMirror: editor.js). One for the whole page (the user, 2026-11-19: one
     page, "header and body can be shared between all pericopes because every pericope has one"): it never leaves the
     page; `opening` says what it shows (a new object each time something's opened: home's waiting pericope, blank, or one
     of the store's), and opening one makes its editor again in the same body under the same header.
     Runes (the user, 2026-11-18): the pericope, the title as typed and the editor are $state, and the editor's own
     document and message are (editor.svelte.js: each editor's ProseMirror state is a $state.raw set as each transaction
     is applied); everything the header shows (words, updated, the title's placeholder, the title shown), what the page
     says and where you are (the tabs' path) is $derived from them, so it changes as you type with nothing counted or
     redrawn by hand (the audit of 2026-11-19). The editor, the follow are $effect. -->
<script>
  import { onDestroy, untrack } from "svelte";
  import { NodeSelection, Selection } from "prosemirror-state";
  import { api, TEST } from "./api.js";
  import { BlockEditor, selectBox, spotOf, keepSpot, focusOf, wordsIn } from "./editor.js";
  import { actions } from "./actions.js";
  import { readClip } from "./clipboard.js";
  import { deriveTitle } from "./draft.js";
  import { prettyDate } from "./views.js";
  import Header from "./Header.svelte";
  import Body from "./Body.svelte";
  import Members from "./Members.svelte";
  import Backlinks from "./Backlinks.svelte";
  import { reviewingAt, reviewQuestion } from "./review.svelte.js";
  import { status as statusLine } from "./state.svelte.js";   // (whose the line is: the pericope's, once it says something)

  // opening: what to show, {id, at, first, flash, home} (first: what the core said of it, fetched before; at: the block
  // to open at; flash: said on opening; home: home's waiting pericope, no id, first a blank one), or null (nothing: the
  // keys page); go: open a place; begun(): home's waiting pericope, its first key (it's being made, in the background);
  // bottom(): ↓ past home's waiting pericope's end (home's search)
  // now (bound by App.svelte): what's open, {id, base, reviewing} (base: changes with each save), or null while it
  // waits: the suggestions below it follow it (Suggested.svelte, one for the page)
  let { opening, go, begun = null, bottom = null, now = $bindable(null) } = $props();
  const FOLLOW = TEST ? 150 : 1000;
  // (nothing open: the header's fields as a blank pericope's)
  const NONE = { id: null, title: null, shown: "", type: "pericope", kind: false, words: 0, created: null, updated: null, visited: null, kinds: "",
    kindTokens: [], maybes: null, backlinks: "", base: null, children: [] };

  let id = $state(null);   // (home's waiting pericope's comes once the core has made it)
  let p = $state(NONE);
  let titleSaved = $state("");
  let titleValue = $state("");
  let width = $state(innerWidth);   // (the window's: a new width moves the boxes, the tabs with them)
  // a kind's maybes being reviewed here (review.svelte.js): derived from the review in hand
  let reviewing = $derived(reviewingAt(id));
  let host = $state(), header = $state(), members = $state(), backs = $state();
  // (a kind's page: its members below what it says, ↓ past its last block into them)
  let hasMembers = $derived(p.kind && !!p.members?.length);
  // what belongs to the pericope open now, made again each time one opens (show)
  let ed = $state.raw(null);   // (the editor over its blocks: what's derived reads its $state, editor.svelte.js)
  let deleted = false, pending = false, stamp = null, leaving = null;
  let gone = false;   // (left: an answer that comes after is for a pericope no longer here)

  // --- what the header shows: derived ---------------------------------------------------------------------------
  const ownText = (doc) => doc.textBetween(0, doc.content.size, "\n", (n) => (n.type.name === "hard_break" ? "\n" : ""));
  const editors = (e) => [e, ...[...e.kids].flatMap(editors)];
  let clock = $state(Date.now());   // (now, every 20 s: "just now" passes)
  $effect(() => { const t = setInterval(() => (clock = Date.now()), 20000); return () => clearInterval(t); });
  let titleChanged = $derived(!p.kind && titleValue !== titleSaved);
  // what it is, from what's in it now (as fw_block.type_label says it: its one block's type, else "pericope"; a kind's
  // the core's), so it changes as you write (the user, 2026-11-23: "changing the displayed type ... doesnt work instantly")
  let type = $derived.by(() => {
    if (p.kind || !ed?.pm) return p.type;
    const doc = ed.pm.doc;
    if (doc.childCount !== 1) return "pericope";
    const n = doc.firstChild;
    return n.type.name === "text_block" ? (n.attrs.para ? "paraphrase" : "text")
      : n.type.name === "quote" || n.type.name === "image" ? n.type.name : "pericope";
  });
  let auto = $derived(p.kind ? p.shown : (ed?.pm && deriveTitle(ownText(ed.pm.doc))) || (p.title ? "" : p.shown));
  let shown = $derived(p.kind ? p.shown : titleValue.trim() || auto);
  let facts = $derived.by(() => {   // (the store's count, and what each editor's gained or lost since it was taken: `since`)
    let n = p.words || 0, dirty = false;
    if (ed?.pm) for (const e of editors(ed)) {
      if (e.readOnly || !e.pm) continue;
      n += wordsIn(e.pm.doc) - e.since;
      dirty ||= e.pm && e.dirty();
    }
    // every field, an empty one saying so (the user, 2026-11-21: "dont hide metadata in headers")
    const when = (iso) => (iso ? prettyDate(iso) : "none");
    // (just now: unsaved, or saved in the last minute, as every change is saved at once now; `clock` ticks it on)
    const recent = p.updated && clock - Date.parse(p.updated) < 60000;
    const upd = dirty || titleChanged || recent ? "just now" : when(p.updated);
    return [`created ${when(p.created)}`, `updated ${upd}`, `words ${n}`, `last visited ${when(p.visited)}`].join("  ·  ");
  });
  // what the page says, while it's the pericope's line (state.svelte.js status.from): the reviewing question, else
  // what its editor says, else what one of its quotes' says
  let said = $derived(reviewing ? reviewQuestion() : ed?.message || [...(ed?.kids || [])].map((k) => k.message).find(Boolean) || "");
  // where you are (the tabs' path), from the editors' states; drawn: anything that moves the boxes (Tabs.svelte measures)
  let focus = $derived(ed?.pm ? focusOf(ed) : null);
  let drawn = $derived(ed?.pm ? [width, ...editors(ed).map((e) => e.pm)] : [width]);
  /** The store's view of it, fresh: the header follows; the editors' words counted from here. */
  function fresh(next) {
    p = next;
    if (ed) for (const e of editors(ed)) if (e.pm) e.since = wordsIn(e.pm.doc);
    if (!titleChanged) {   // (the store's title, unless one's being written here)
      titleSaved = p.title || "";
      const v = p.kind ? p.shown : titleSaved;
      if (titleValue !== v && !header?.editingTitle()) titleValue = v;
    }
  }

  // --- the page says ----------------------------------------------------------------------------------------------
  /** The pericope has something to say (its editor changed, saved, was told something): the line is its (`said`). */
  function status() { statusLine.from = "pericope"; }

  // --- the kinds line (Kinds.svelte, in the header): its tokens are p's, so it follows the store
  const kindsDone = async (said) => { await refresh(true); if (said) { ed.message = said; status(); } header?.focusKinds(); };

  // --- the store ----------------------------------------------------------------------------------------------------
  async function refresh(headerOnly = false) {   // the store as it is now: the header always; the blocks when nothing here is unsaved
    if (!id || !ed) return;   // (waiting, or nothing open: nothing in the store to follow)
    const e = ed, asked = e.base;
    const r = await api(`/api/pericope/${id}`);
    if (gone || e !== ed) return;
    if (!r.ok) { go("#/"); return; }
    if (e.base !== asked) { pending = true; return; }   // (saved meanwhile: older than the page; ask again)
    const was = p.base;
    fresh(r.body);
    if (headerOnly) return;
    if (e.busy() || titleChanged) { pending = true; return; }   // (written in here, or through a quote just now: later)
    pending = false;
    if (p.base === e.base) return;
    e.reload(p.children, p.base);
    e.message = was !== p.base ? "updated from another session" : "";
    status();
  }
  async function rename() {   // a kind's title is its name: renamed as you leave it (refused empty, or another kind's)
    if (gone || !p.kind || titleValue.trim() === p.shown) return;
    const r = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "rename", kind: id, name: titleValue }) });
    if (!r.ok) { titleValue = p.shown; ed.message = r.body.error || "not renamed"; }
    await refresh(true);
    status();
  }
  function titleTyped() { if (p.kind || !ed) return; status(); if (titleChanged) ed.schedule(); }

  // --- the editor ---------------------------------------------------------------------------------------------------
  const open = (q) => {   // Open it: where the quoted block lives, at it
    const home = q.home || q.target, at2 = q.at || (home !== q.target ? q.target : null);
    go(`#/p/${home}` + (at2 ? `@${at2}` : "") + (at2 && q.off != null ? `~${q.off}` : ""), { quiet: !!q.whole });   // (~: where the cursor was in it)
  };
  const act = actions({
    root: () => ed, go: (h) => go(h), title: () => shown, gone: () => { deleted = true; },
    // (focus off: a toggle in the ⌘/ menu, which stays open: the cursor kept, the focus left in the menu)
    reload: async (selectQuote = null, { focus = true } = {}) => {   // the page drawn again from the store (after an action); the editor the cursor's in
      const e = ed;
      const spot = selectQuote ? null : spotOf(e);   // (where the cursor is, as the action left it: kept, below)
      const r = await api(`/api/pericope/${id}`);
      if (!r.ok || gone || e !== ed) return;
      fresh(r.body);
      e.reload(p.children, p.base);
      if (focus) e.view.focus();
      if (selectQuote) {
        let at3 = null;
        e.view.state.doc.descendants((n, pos) => { if (at3 === null && n.type.name === "quote" && n.attrs.id === selectQuote) at3 = pos; });
        if (at3 !== null) e.view.dispatch(e.view.state.tr.setSelection(NodeSelection.create(e.view.state.doc, at3)));
        status();
        return e;
      }
      const at = keepSpot(e, spot, { focus }) || e;   // (the cursor where it was, following its text into a quote or out of one)
      status();
      return at;   // (the editor the cursor's in now)
    },
  });

  /** `o` shown: everything of the pericope left before (main.js has left it, saved) put aside, and its own made: the
   * header's fields from what the core said, an editor over its blocks in the body. */
  function show(o) {
    if (ed && !ed.gone) ed.destroy();   // (left already, as main.js does before opening another: else gone unsaved)
    ed = null;
    deleted = false; pending = false; stamp = null; leaving = null; gone = false;
    const first = o?.first || NONE;
    id = o?.home ? null : o?.id ?? null;
    p = first;
    titleSaved = first.title || "";
    titleValue = first.kind ? first.shown : first.title || "";
    if (!o) { status(); return; }
    readClip();   // (what fw last clipped: a paste here can be live quotes of it, or a move)
    const picture = first.children.length === 1 && first.children[0].t === "image" && !first.children[0].id;
    ed = new BlockEditor(host, { id, children: first.children, base: first.base, readOnly: picture, open, status, act,
      top: () => header.focusTitle(),
      fields: () => (titleChanged ? { title: titleValue } : {}),   // (the title goes with the editor's next save)
      saved: (sent) => { if (sent.title !== undefined) titleSaved = sent.title; if (!sent.final) refresh(true); },
      bottom: () => (hasMembers ? members?.enter() : bottom?.()), begin: id ? null : make });
    ed.place(o.at, o.off);
    if (reviewing) ed.view.setProps({ editable: () => false });   // (reviewing: nothing types)
    ed.view.focus();
    if (o.quiet) ed.hush();   // (from a block selected whole: nothing shown as where you are until you move or type)
    if (o.flash) ed.message = o.flash;
    status();
  }
  $effect(() => { const o = opening; untrack(() => show(o)); });   // (opened: shown; nothing else it reads shows it again)
  $effect(() => { now = id ? { id, base: p.base, reviewing } : null; });   // (what's open, told the page: its suggestions follow)

  $effect(() => untrack(() => {   // changes made elsewhere, followed (once, for whatever's open)
    const follow = setInterval(async () => {
      if (!id || !ed || gone) return;
      const r = await api("/api/stamp");
      if (!r.ok || gone) return;
      if ((stamp !== null && r.body.stamp !== stamp) || (pending && !ed.busy())) await refresh();
      stamp = r.body.stamp;
    }, FOLLOW);
    const redraw = () => { width = innerWidth; };   // (a new width moves the boxes: the tabs with them)
    window.addEventListener("resize", redraw);
    return () => { clearInterval(follow); window.removeEventListener("resize", redraw); };
  }));

  /** Home's waiting pericope, its first key (typed in it, or its title): made in the store in the background (typing
   * never waits: the editor's saves wait for it); the address says it at once it's made, no new place on the trail. */
  function make() {
    begun?.();
    const e = ed;
    return api("/api/pericope", { method: "POST", body: JSON.stringify({ title: null }) }).then((r) => {
      if (!r.ok) return null;
      if (e === ed) {   // (still the one open)
        id = r.body.id;
        p = { ...p, id, base: r.body.base };
        if (!gone && ["", "#/"].includes(location.hash)) history.replaceState(history.state, "", `#/p/${id}`);   // (still home's place)
      }
      return r.body;
    });
  }

  /** The editor of the pericope open (for main.js and the tests); null with nothing open. */
  export function editor() { return ed && !ed.gone ? ed : null; }
  /** Nothing in it, and no title: nothing to send away. */
  export function blank() {
    if (!ed || p.kind || titleValue.trim() || p.title) return false;
    let only = true;
    ed.view.state.doc.forEach((n) => { if (n.type.name !== "text_block" || n.textContent.trim()) only = false; });
    return only;
  }
  /** The cursor at its very end (↑ from home's search). */
  export function focusEnd() {
    if (!ed) return;
    ed.view.focus();
    ed.view.dispatch(ed.view.state.tr.setSelection(Selection.atEnd(ed.view.state.doc)).scrollIntoView());
  }
  /** Leaving the pericope open: what's unsaved saved (the title with it; an empty, untitled pericope left behind
   * discarded), its editor gone. Once: asked again (sent away, then the page switching), the same leaving. */
  export function leave() {
    return (leaving ||= (async () => {
      if (!ed) return;
      gone = true;
      if (deleted) { ed.destroy(); return; }
      await ed.leave({ final: true });
    })());
  }
  /** What the pericope says (App.svelte draws it while the line is the pericope's). */
  export function says() { return said; }
  onDestroy(() => { gone = true; if (ed && !ed.gone) ed.destroy(); });
</script>

<Backlinks bind:this={backs} rows={p.backlinkRows || []} {go} out={() => header?.focusBacklinks()} />
<Header bind:this={header} backs={() => backs?.enter()} {p} {type} {id} {facts} {auto} bind:title={titleValue} {go} typed={titleTyped} left={rename} {kindsDone}
  body={() => ed?.view.focus()} />
<div class="fw-stem"></div>
<Body bind:host {drawn} {focus} hidden={reviewing} pick={(box) => selectBox(ed, box)} />
{#if hasMembers && !reviewing}<Members bind:this={members} rows={p.members} kind={id} {go} up={focusEnd} down={bottom} />{/if}
