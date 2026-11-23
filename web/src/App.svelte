<!-- App.svelte — the page, one page (the user, 2026-11-19: "we need to switch to a one page, we should soft routing"):
     at the top, what the page says; below, the one pericope (Pericope.svelte: one header, one body, for every pericope),
     centred while it's home's; under it, the search and the suggestions (Suggested.svelte), one for the page, following
     whatever pericope is open (the user, 2026-11-21: "suggested should stay where it is": sending a pericope away
     moves only the pericope, main.js); the keys page, or the kinds view, in its place while that's open. Moving around changes `here`
     (main.js, from the address); nothing on the page is made again to move but what each pericope writes in. -->
<script>
  import Ask from "./Ask.svelte";
  import Suggested from "./Suggested.svelte";
  import Pericope from "./Pericope.svelte";
  import Keys from "./Keys.svelte";
  import KindsView from "./KindsView.svelte";
  import { status, ui, here } from "./state.svelte.js";

  let { go } = $props();   // (open a place: its address)
  let peri = $state(), foot = $state();
  let open = $state(null);   // (the pericope open, Pericope.svelte's: {id, base, reviewing}; null while home's waits)
  let homing = $derived(here.view === "home" && !here.written);   // (home's own parts showing)
  // (home's pericope, typed in or not, stays centred: it grows from the middle, the user, 2026-11-19)
  let centred = $derived(here.view === "home" || here.written);
  // what the page says: the pericope's, derived from what it says, or the page's own (state.svelte.js status.from)
  let line = $derived(status.from === "pericope" ? (peri?.says() ?? "") : status.text);

  /** Home's waiting pericope, its first key: the rest of home gone at once (an edit, not navigation). */
  function begun() { here.written = true; window.scrollTo(0, 0); }

  /** The one pericope on the page (main.js: its editor, leaving it). */
  export function pericope() { return peri; }
</script>

<header class="fw-topbar">
  <span id="bar-left" class="fw-status" class:fw-said={!!line}>{line}</span>
</header>
<main id="main" class="mx-auto max-w-7xl px-4 pt-4 pb-16" class:fw-room-below={here.view === "pericope"}>
  <div class="fw-page" class:fw-on-pericope={here.view === "pericope"} hidden={here.view === "keys" || here.view === "kinds"}>
    <div class={"fw-peri " + (centred ? (homing ? "fw-centre fw-waiting" : "fw-centre") : "fw-frame")}>
      <Pericope bind:this={peri} bind:now={open} opening={here.opening} {go} {begun} bottom={() => foot?.toSearch()} />
    </div>
    {#if here.view !== "keys" && here.view !== "kinds" && !open?.reviewing}
      <Suggested bind:this={foot} {go} up={() => peri?.focusEnd()} from={open?.id ?? null} version={open?.base ?? null} />
    {/if}
  </div>
  {#if here.view === "keys"}<Keys home={() => go("#/")} />{/if}
  {#if here.view === "kinds"}<KindsView {go} home={() => go("#/")} />{/if}
</main>
{#if ui.asking}<Ask />{/if}
