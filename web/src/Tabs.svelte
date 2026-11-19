<!-- Tabs.svelte — where you are, as an address in the gutter (tabs.js measures; this draws). Measured again whenever
     `tick` changes (the editor changed, or the window's width): the page's layout is the source, so it's read in an
     effect, after the page is laid out. A click on a tab selects its block whole (`pick`). -->
<script>
  import { tabsIn } from "./tabs.js";
  let { doc, tick, pick, hidden = false } = $props();
  let tabs = $state([]);
  $effect(() => { tick; hidden; tabs = hidden || !doc ? [] : tabsIn(doc); });
  const cls = (t, base) => base + (t.focus ? (base === "fw-tab" ? " fw-tab-focus" : " fw-line-focus") : "")
    + (t.filled ? (base === "fw-tab" ? " fw-tab-filled" : " fw-line-filled") : "") + (t.quote ? (base === "fw-tab" ? " fw-tab-quote" : " fw-line-quote") : "");
</script>

{#if tabs.length}
  <div class="fw-tabs">
    {#each tabs as t}
      <div class={cls(t, "fw-tab-line")} style:left="{t.lineLeft}px" style:top="{t.top + t.height / 2}px" style:width="{t.lineWidth}px"></div>
      <div class={cls(t, "fw-tab")} style:left="{t.left}px" style:top="{t.top}px" style:width="{t.width}px" style:height="{t.height}px"
        onmousedown={(e) => { e.preventDefault(); pick(t.box); }} role="button" tabindex="-1">{t.label}</div>
    {/each}
  </div>
{/if}
