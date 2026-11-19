<!-- Home.svelte — home (the user, 2026-11-18, -19): in the middle of the first screen a waiting pericope, empty and
     untitled, the cursor in it (Pericope.svelte, with no id: nothing's written until its first key); below it the search,
     its results dropping down over the page, and the garden (12 cards), running off the bottom; below them the whole
     library, a line each. Typing in the pericope makes it (in the background) and takes the rest away: the page is then
     just that pericope. ↓ past its end goes to the search, ↑ from the search's top back into it. One selection runs
     through the search's rows: with nothing typed, [+ new, …the garden, …the library]; typing, the results; drawn only
     while you're in the search. Runes: what's typed, the rows, the selection are $state; everything shown is $derived. -->
<script>
  import { tick } from "svelte";
  import { flip } from "svelte/animate";
  import { fade } from "svelte/transition";
  import { api, TEST } from "./api.js";
  import { ask } from "./ask.js";
  import { pressed } from "./keys.svelte.js";
  import { keep as keepSel, MOVE } from "./results.js";
  import { status } from "./state.svelte.js";
  import Pericope from "./Pericope.svelte";

  let { go } = $props();   // (open a place: its address)
  const FOLLOW = TEST ? 150 : 1000;       // ms: how often home looks at the store for changes made elsewhere
  const MEANING_AFTER = TEST ? 50 : 400;  // ms after the last key: the search service asked too
  const NEW = { key: "new", label: "+ new pericope", right: "" };

  let query = $state(""), sel = $state(0), rows = $state([]), garden = $state([]), library = $state([]);
  let pending = $state(false), grid = $state(true);   // (pending: the search service's answer to this query still to come)
  let input = $state(), gardenEl = $state(), page = $state(), found = $state();   // (bound inside {#if}: runes)
  let waiting = $state(), written = $state(false), inSearch = $state(false);   // (written: typed in the waiting pericope)
  // the waiting pericope: as the core gives a new, empty, untitled one (nothing asked of it: it's made on the first key)
  const BLANK = { id: null, title: null, shown: "", type: "block", kind: false, words: 0, updated: null, kinds: "",
    kindTokens: [], maybes: null, backlinks: "", base: null, children: [] };
  function begun() { written = true; window.scrollTo(0, 0); }   // (an edit: the rest gone at once, the page just the pericope, still where it was)
  function toSearch() { sel = 0; input?.focus(); }
  let seq = 0, meaningTimer = null;

  let items = $derived(query ? rows : [NEW, ...garden.map((g) => ({ ...g, label: g.title, open: g.key })), ...library.map((l) => ({ ...l, label: l.title }))]);
  let picked = $derived(items[sel]);
  let foot = $derived(!picked ? "" : picked.key === "new" ? `↵ a new pericope titled “${query}”` : picked.at ? "↵ open it where it lives" : "↵ open it");

  async function load() {
    const r = await api("/api/home");
    if (!r.ok) return;
    garden = r.body.rows;
    library = r.body.library || [];
  }
  async function search(meaning) {
    const n = ++seq, q = query;
    const r = await api(`/api/search?q=${encodeURIComponent(q)}${meaning ? "&meaning=1" : ""}`);
    if (!r.ok || n !== seq) return;   // (an answer to an older query)
    const was = meaning ? rows[sel]?.key : null;   // (the search service's answer: what's selected stays selected, wherever it moves)
    rows = r.body.rows;
    if (meaning) pending = false;
    let s = Math.min(sel, rows.length - 1);
    if (s <= 0) s = rows.length > 1 ? 1 : 0;   // the best result, else the pinned row
    sel = keepSel(rows, was, s);
  }
  function typed() {
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
    if (it.key === "new") {
      const r = await api("/api/pericope", { method: "POST", body: JSON.stringify({ title: query || null }) });
      if (r.ok) go(`#/p/${r.body.id}`);
      return;
    }
    go(`#/p/${it.open || it.key}` + (it.at ? `@${it.at}` : it.key !== (it.open || it.key) ? `@${it.key}` : ""));
  }
  async function deleteSelected() {   // the selected pericope, deleted (asked first), as the terminal's ^D on home
    const it = items[sel];
    if (!it || it.key === "new" || (it.open && it.open !== it.key)) { status.text = "that's a block inside a pericope: open it to delete it"; return; }
    const title = it.title || it.label;
    if (!(await ask(`delete “${title}”? quotes of it elsewhere keep its last text. this can't be undone.`))) { input.focus(); return; }
    const r = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "delete", pericope: it.key }) });
    await load();
    if (query) await search(false);
    sel = Math.min(sel, items.length - 1);
    status.text = r.ok ? `deleted “${title}”` : r.body.error || "couldn't";
    input.focus();
  }
  /** Where an arrow goes from `at`: through the results; else + new, the garden (across its grid), the library. */
  function step(key, at) {
    const n = items.length, g = garden.length;
    if (query) return key === "ArrowDown" ? Math.min(n - 1, at + 1) : key === "ArrowUp" ? Math.max(0, at - 1) : at;
    const cols = grid && gardenEl ? Math.max(1, getComputedStyle(gardenEl).gridTemplateColumns.split(" ").length) : 1;
    const inGarden = at >= 1 && at <= g, lastRow = 1 + Math.floor((g - 1) / cols) * cols;
    if (key === "ArrowRight") return inGarden ? Math.min(g, at + 1) : at;
    if (key === "ArrowLeft") return inGarden ? Math.max(1, at - 1) : at;
    if (key === "ArrowDown") {
      if (at === 0) return Math.min(n - 1, 1);
      if (inGarden) return at >= lastRow ? Math.min(n - 1, g + 1) : Math.min(g, at + cols);
      return Math.min(n - 1, at + 1);
    }
    if (key === "ArrowUp") {
      if (inGarden) return at <= cols ? 0 : at - cols;
      if (at === g + 1 && g) return lastRow;   // (out of the library: the garden's last row)
      return Math.max(0, at - 1);
    }
    return at;
  }
  function onkey(e) {
    if (pressed(e, "done")) return;   // (send it away: main.js's, not ↵ here)
    if (e.key === "ArrowUp" && sel === 0) { e.preventDefault(); waiting?.focusEnd(); return; }   // (the search's top: back into the pericope)
    if (e.key.startsWith("Arrow") && !(query && (e.key === "ArrowLeft" || e.key === "ArrowRight"))) sel = step(e.key, sel);
    else if (e.key === "Enter") { e.preventDefault(); pick(); return; }
    else if (e.key === "Escape") { query = ""; typed(); }
    else if (pressed(e, "list")) grid = !grid;
    else if (pressed(e, "deleteHome")) { e.preventDefault(); deleteSelected(); return; }
    else return;
    e.preventDefault();
  }
  const choose = (e, n) => { e.preventDefault(); sel = n; pick(); };

  /** The waiting pericope's editor (main.js, the tests); leaving home, what's in it saved; whether it's blank. */
  export const editor = () => waiting?.editor() || null;
  export const leave = () => waiting?.leave();
  export const blank = () => !waiting || waiting.blank();

  // the selected row kept in view, as it changes (only while you're in the search: opening home leaves the page put)
  $effect(() => {
    sel; query; if (!inSearch) return;
    tick().then(() => (query ? found : page)?.querySelector(".fw-sel")?.scrollIntoView({ block: "nearest" }));
  });
  // home's own: the page says nothing; here, "home"; the results over the page while something's typed (#main's class)
  $effect(() => {
    const main = document.querySelector("#main");
    main?.classList.toggle("fw-searching", !!query);
    return () => main?.classList.remove("fw-searching");
  });
  // written elsewhere: home again
  $effect(() => {
    let stamp = null;
    const follow = setInterval(async () => {
      if (written) return;
      const r = await api("/api/stamp");
      if (!r.ok) return;
      if (stamp !== null && r.body.stamp !== stamp) { await load(); if (query) search(false); }
      stamp = r.body.stamp;
    }, FOLLOW);
    return () => clearInterval(follow);
  });
  $effect(() => {
    status.text = "";
    load();
  });
</script>

{#snippet row(it, n, card)}
  <div class={(card ? "fw-card" : "fw-row") + (n === sel && inSearch ? " fw-sel" : "") + (it.dim ? " fw-dim" : "") + (it.kind ? " fw-kind" : "")
      + (card && it.preview?.some((x) => x.t === "image") ? " fw-card-with-pic" : "")}
    data-pericope={it.key !== "new" ? it.open || it.key : undefined} onmousedown={(e) => choose(e, n)} role="button" tabindex="-1">
    {#if card}
      <div class="fw-card-title">{it.title}</div>
      <div class="fw-dim">{it.right}  ·  {it.last}</div>
      <div class="fw-card-body">
        {#each it.preview || [] as piece}
          {#if piece.t === "image"}<img class="fw-card-pic" src={`/images/${piece.file}`} loading="lazy" alt="" />
          {:else}<div class="fw-card-text">{piece.text}</div>{/if}
        {/each}
      </div>
    {:else}
      <span class="fw-row-label">{it.label}</span><span class="fw-dim">{it.right}</span>
    {/if}
  </div>
{/snippet}

<div class={written ? "fw-centre" : "fw-centre fw-waiting"}>   <!-- (centred, typed in or not: it grows from the middle; the user, 2026-11-19) -->
  <Pericope bind:this={waiting} id={null} at={null} first={BLANK} {go} {begun} bottom={toSearch} />
</div>
{#if !written}
<div class="fw-search">
  <div class="fw-prompt fw-box">
    <span class="fw-dim">open › </span>
    <input class="fw-input" bind:this={input} bind:value={query} oninput={typed} onkeydown={onkey}
      onfocus={() => (inSearch = true)} onblur={() => (inSearch = false)} />
  </div>
  <div class="fw-results">
    <div class="fw-rows" bind:this={found}>
      {#each query ? rows : [] as it, n (it.key + (it.at || ""))}
        <div animate:flip={{ duration: MOVE }} in:fade={{ duration: MOVE }}>{@render row(it, n, false)}</div>
      {/each}
      {#if query && pending}<div class="fw-pending">finding more by meaning…</div>{/if}
    </div>
    <div class="fw-dim fw-foot">{query ? foot : ""}</div>
  </div>
</div>
<div class="fw-home-page" bind:this={page}>
  <div class="fw-rows">{@render row(NEW, query ? -1 : 0, false)}</div>
  <div class={grid ? "fw-rows fw-grid" : "fw-rows"} bind:this={gardenEl}>
    {#each garden as g, i (g.key)}{@render row({ ...g, label: g.title, open: g.key }, query ? -1 : 1 + i, grid)}{/each}
  </div>
  <div class="fw-section fw-dim">library  ·  {library.length}</div>
  <div class="fw-rows fw-library">
    {#each library as l, i (l.key)}{@render row({ ...l, label: l.title }, query ? -1 : 1 + garden.length + i, false)}{/each}
  </div>
</div>
{/if}
