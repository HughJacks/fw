<!-- App.svelte — the page's shell: at the top, what the page says (no breadcrumb: the user, 2026-11-19); below,
     the view open (page.view: home, a pericope, the keys page; main.js decides which, after the one
     before has saved). (The bottom bar and its key hints are gone, 2026-11-18.) -->
<script>
  import Ask from "./Ask.svelte";
  import Home from "./Home.svelte";
  import Pericope from "./Pericope.svelte";
  import Keys from "./Keys.svelte";
  import { status, ui, page } from "./state.svelte.js";
</script>

<header class="fw-topbar">
  <span id="bar-left" class="fw-status">{status.text}</span>
</header>
<main id="main" class="mx-auto max-w-7xl px-4 pt-4 pb-16">
  {#key page.view}
    {#if page.view?.kind === "home"}<Home bind:this={page.instance} {...page.view.props} />
    {:else if page.view?.kind === "pericope"}<Pericope bind:this={page.instance} {...page.view.props} />
    {:else if page.view?.kind === "keys"}<Keys bind:this={page.instance} {...page.view.props} />{/if}
  {/key}
</main>
{#if ui.asking}<Ask />{/if}
