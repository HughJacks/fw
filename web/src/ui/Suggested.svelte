<!-- Suggested.svelte — the foot of every page, the same everywhere ("the pages should be the
     same"): the search (go to), then the suggestions, which become its results while something's typed, in place (the
     user: "typing should not open a new menu it should sort the suggested list and bring in a longer list":
     rows already there move, the rest ease in), a line each, said lightly ("suggested from this"; those filled from home's order "unrelated"), then +
     new pericope. `from`: the pericope open, its suggestions "from here" (GET
     /api/exits/<id>, fw_search.exits: what points here, alongside it, where you go next, by meaning, filled from home's
     order), asked as it opens, then again with the search service, and again as what's written in it is saved (`version`), at
     most every AGAIN ms ("reactive to the content in the current pericope … update it at
     semi-frequent periods"): nothing in it, home's order; something, what's specific to it; or none, home's waiting
     pericope above, and they're home's order, every pericope (GET /api/home, fw_search.home_order), followed as the
     store changes. One for the page (App.svelte): it stays as pericopes come and go, its rows changing in place. ↓ past the pericope's
     end comes to the search (toSearch), ↑ from its top goes back (up). One selection runs through the rows: with
     nothing typed, [the suggestions…, + new]; typing, [the results…, + new titled with it]; drawn only while you're in it. ⌘⌫ deletes the
     pericope selected. Runes: what's typed, the rows, the selection are $state; everything shown is $derived. -->
<script>
  import { onDestroy, tick, untrack } from "svelte";
  import { flip } from "svelte/animate";
  import { fade } from "svelte/transition";
  import { api, TEST } from "../lib/api.js";
  import { ask } from "../lib/ask.js";
  import { pressed } from "../lib/keys.js";
  import { keep as keepSel, MOVE } from "../lib/results.js";
  import { say } from "../state/state.svelte.js";
  import { onStore } from "../lib/live.js";

  // (go: open a place, its address; up(): back into the pericope above; from: the pericope open, or none: home;
  // version: its base, new with each save)
  let { go, up, from = null, version = null } = $props();
  const MEANING_AFTER = TEST ? 50 : 400;  // ms after the last key: the search service asked too
  const AGAIN = TEST ? 200 : 8000;        // ms: how often, at most, a pericope being written in has its suggestions asked again
  const NEW = { key: "new", label: "+ new pericope", right: "" };

  let query = $state(""), sel = $state(0), rows = $state([]), list = $state([]);
  let pending = $state(false);   // (pending: the search service's answer to this query still to come)
  let input = $state(), page = $state();   // (bound inside {#if}: runes)
  let inSearch = $state(false);
  let still = $state(false), lastQuery = "";
  // (hold: px, the room above the search pinned while something's typed, "the list should grow
  // down but the search bar should probably stay where it was"; null: the page's own, margin-top auto)
  // (floor: px, the least the list below it takes while something's typed, from the search to the window's foot as it
  // was: results shrinking never make the page shorter than what's on screen, which would pull the scroll and the
  // search with it; null: the list's own height)
  let hold = $state(null), floor = $state(null), box = $state();
  /** Into the search (↓ past the pericope's end), its first row selected. */
  export function toSearch() { sel = 0; input?.focus(); reveal(); }
  let seq = 0, meaningTimer = null;
  let following = undefined, againTimer = null, askedAt = 0;   // (following: the pericope the rows are for)

  // what's listed: the suggestions, or what's typed found (the core's pinned + new taken from its top), + new last (the
  // user)
  let shown = $derived(query ? rows.filter((r) => r.key !== "new") : list.map((l) => ({ ...l, label: l.title })));
  let items = $derived([...shown, query ? rows.find((r) => r.key === "new") || { ...NEW, label: `+ new pericope “${query}”` } : NEW]);
  let firstUnrelated = $derived(query ? -1 : list.findIndex((l) => l.unrelated));   // (where those filled from home's order begin, -1: none)
  let hint = $derived(query ? (shown.length || pending ? "found" : "nothing found") : from ? "suggested from this" : "suggested");
  let picked = $derived(items[sel]);
  let foot = $derived(!picked ? "" : picked.key === "new" ? `↵ a new pericope titled “${query}”` : picked.at ? "↵ open it where it lives" : "↵ open it");

  async function load() {
    const at = from;
    if (!at) { const r = await api("/api/home"); if (r.ok && !from) list = r.body.rows; return; }
    const r = await api(`/api/exits/${at}`);
    if (!r.ok || from !== at) return;
    rowsFrom(r.body.rows);
    await again();   // (then with the search service)
  }
  /** The open pericope's suggestions asked again, with the search service (what it says now, as saved). */
  async function again() {
    const at = from;
    askedAt = Date.now();
    const m = await api(`/api/exits/${at}?meaning=1`);
    if (m.ok && from === at) rowsFrom(m.body.rows);
  }
  /** The suggestions, `next`: what's selected stays selected, wherever it moves. */
  function rowsFrom(next) {
    const was = items[sel]?.key;
    list = next;
    if (!query) sel = inSearch ? keepSel(items, was, sel) : 0;   // (not in the search: nothing chosen to keep)
  }
  async function search(meaning) {
    const n = ++seq, q = query;
    const r = await api(`/api/search?q=${encodeURIComponent(q)}${meaning ? "&meaning=1" : ""}`);
    if (!r.ok || n !== seq) return;   // (an answer to an older query)
    const was = meaning ? items[sel]?.key : null;   // (the search service's answer: what's selected stays selected)
    // (the search service's answer never re-sorts what's shown, "remove the constant bouncing": what it
    // adds goes after the rows already there, in its order)
    rows = meaning ? steady(rows, r.body.rows) : r.body.rows;
    if (meaning) pending = false;
    sel = keepSel(items, was, Math.min(sel, items.length - 1));   // (the best result first)
  }
  /** `next` with the rows of `now` it still has first, in `now`'s order, then its others (pure). */
  function steady(now, next) {
    const there = new Set(now.map((r) => r.key + (r.at || "")));
    const got = new Map(next.map((r) => [r.key + (r.at || ""), r]));
    return [...now.filter((r) => got.has(r.key + (r.at || ""))).map((r) => got.get(r.key + (r.at || ""))),
            ...next.filter((r) => !there.has(r.key + (r.at || "")))];
  }
  function typed() {
    if (query && !lastQuery) {   // (the room above it, and below it to the window's foot, as they were)
      hold = parseFloat(getComputedStyle(box).marginTop);
      floor = Math.max(0, innerHeight - page.getBoundingClientRect().top);
    }
    if (!query) hold = floor = null;
    still = !!query && !!lastQuery;   // (a key into what's already a search: the rows change in place, nothing moves)
    lastQuery = query;
    sel = 0;
    clearTimeout(meaningTimer);
    if (!query) { pending = false; return; }
    pending = true;   // (the search service asked once the typing pauses: shown coming)
    search(false);
    meaningTimer = setTimeout(() => search(true), MEANING_AFTER);
  }
  async function pick() {
    const it = items[sel];
    if (!it) return;
    const q = query;
    query = ""; lastQuery = ""; hold = floor = null; rows = []; pending = false;   // (gone where it said: the search empty again, as it stays on the page)
    input?.blur();
    if (it.key === "new") {
      const r = await api("/api/pericope", { method: "POST", body: JSON.stringify({ title: q || null }) });
      if (r.ok) go(`#/p/${r.body.id}`);
      return;
    }
    go(`#/p/${it.open || it.key}` + (it.at ? `@${it.at}` : it.key !== (it.open || it.key) ? `@${it.key}` : ""));
  }
  async function deleteSelected() {   // the selected pericope, deleted (asked first), as the terminal's ^D on home
    const it = items[sel];
    if (!it || it.key === "new" || (it.open && it.open !== it.key)) { say("that's a block inside a pericope: open it to delete it"); return; }
    const title = it.title || it.label;
    if (!(await ask(`delete “${title}”? quotes of it elsewhere keep its last text. this can't be undone.`))) { input.focus(); return; }
    const r = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "delete", pericope: it.key }) });
    await load();
    if (query) await search(false);
    sel = Math.min(sel, items.length - 1);
    say(r.ok ? `deleted “${title}”` : r.body.error || "couldn't");
    input.focus();
  }
  /** Where an arrow goes from `at`: down or up the rows. */
  function step(key, at) {
    return key === "ArrowDown" ? Math.min(items.length - 1, at + 1) : key === "ArrowUp" ? Math.max(0, at - 1) : at;
  }
  function onkey(e) {
    if (pressed(e, "done")) return;   // (send it away: main.js's, not ↵ here)
    if (e.key === "ArrowUp" && sel === 0) { e.preventDefault(); up(); return; }   // (the search's top: back into the pericope)
    if (e.key.startsWith("Arrow") && !(query && (e.key === "ArrowLeft" || e.key === "ArrowRight"))) { sel = step(e.key, sel); reveal(); }
    else if (e.key === "Enter") { e.preventDefault(); pick(); return; }
    else if (e.key === "Escape") { query = ""; typed(); }
    else if (pressed(e, "deleteHome")) { e.preventDefault(); deleteSelected(); return; }
    else return;
    e.preventDefault();
  }
  const choose = (e, n) => { e.preventDefault(); sel = n; pick(); };

  /** The selected row kept in view, arrowed to (only then, typing never scrolls the page; a row
   * mid-move as results come in is drawn where it was, far down, and would pull the page to it). */
  function reveal() { tick().then(() => page?.querySelector(".fw-sel")?.scrollIntoView({ block: "nearest" })); }
  // written elsewhere: home again (home's own: a page's suggestions are asked as it opens)
  $effect(() => {
    if (from) return;
    return onStore(async () => { await load(); if (query) search(false); }, { first: false });
  });
  // what's open: another pericope (or home), its rows asked, in place of the last one's as they come; the same one,
  // saved again, asked again at most every AGAIN ms
  $effect(() => {
    const f = from; version;
    untrack(() => {
      if (f !== following) {
        following = f;
        clearTimeout(againTimer); againTimer = null;
        sel = 0;
        if (!f) say("");   // (a page's line is its pericope's, not cleared here)
        askedAt = Date.now();
        load();
        return;
      }
      if (!f || againTimer) return;   // (one's coming: it asks for what's saved then)
      againTimer = setTimeout(() => { againTimer = null; if (from === f) again(); }, Math.max(0, askedAt + AGAIN - Date.now()));
    });
  });
  onDestroy(() => clearTimeout(againTimer));
</script>

{#snippet row(it, n)}
  <div class={"fw-row" + (n === sel && inSearch ? " fw-sel" : "") + (it.dim ? " fw-dim" : "") + (it.kind ? " fw-kind" : "")}
    data-pericope={it.key !== "new" ? it.open || it.key : undefined} onmousedown={(e) => choose(e, n)} role="button" tabindex="-1">
    <span class="fw-row-label">{it.label}</span><span class="fw-dim">{it.right}</span>
  </div>
{/snippet}

<section class="fw-suggested" class:fw-from={!!from} bind:this={box} style:margin-top={hold == null ? null : `${hold}px`}>
<div class="fw-search">
  <div class="fw-prompt fw-go">
    <span class="fw-dim">go to</span>
    <input class="fw-input" bind:this={input} bind:value={query} oninput={typed} onkeydown={onkey}
      onfocus={() => (inSearch = true)} onblur={() => (inSearch = false)} />
  </div>
</div>
<div class="fw-home-page" bind:this={page} style:min-height={floor == null ? null : `${floor}px`}>
  <div class="fw-rows fw-library">
    {#if hint && firstUnrelated !== 0}<div class="fw-hint">{hint}</div>{/if}
    {#each shown as it, i (it.key + (it.at || ""))}
      <div animate:flip={{ duration: still ? 0 : MOVE }} in:fade={{ duration: still ? 0 : MOVE }}>
        {#if i === firstUnrelated}<div class="fw-hint">{i ? "unrelated" : "suggested"}</div>{/if}   <!-- (nothing related yet: just suggested) -->
        {@render row(it, i)}
      </div>
    {/each}
    {#if query}<div class="fw-pending" class:fw-gone={!pending}>finding more by meaning…</div>{/if}   <!-- (its room kept: + new doesn't jump) -->
  </div>
  <div class="fw-rows fw-new">{@render row(items.at(-1), items.length - 1)}</div>
  {#if query}<div class="fw-dim fw-foot">{foot}</div>{/if}
</div>
</section>
