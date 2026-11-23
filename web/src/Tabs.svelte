<!-- Tabs.svelte — where you are, as an address in the gutter: a tab per block on your path (tabs.js measures; each is a
     Tab.svelte). Which blocks are on your path is derived from the editors' states (`focus`, editor.svelte.js focusOf);
     only where they are is measured, again whenever what's drawn changes (`drawn`: the editors' states, the window's
     width), in an effect, after the page is laid out; and, while a block's room is easing out or back
     (a padding transition in the body, app.css), every frame, so the tabs follow the boxes as they move. Keyed by block
     (the user, 2026-11-19): each block's tab is its own, placed by its block, shown while the block's on your path; going
     elsewhere, one fades out where it is and another fades in where it is, nothing travels between blocks. -->
<script>
  import { tabsIn, linksIn, focusBoxes } from "./tabs.js";
  import Tab from "./Tab.svelte";

  let { doc, drawn, focus, pick, hidden = false } = $props();
  let tabs = $state([]), links = $state([]);   // (links: the lines between the block you're in and its neighbours)
  const measure = () => {
    const at = hidden || !doc ? null : focusBoxes(focus);
    tabs = at ? tabsIn(doc, at) : [];
    links = at ? linksIn(doc, at) : [];
  };
  $effect(() => { drawn; focus; hidden; measure(); });

  // a block's room easing (padding transitions running in the body): measured each frame until none is (asked of the
  // page each frame, not counted from events: a block taken away mid-way never says it's done)
  $effect(() => {
    if (!doc) return;
    let frame = 0;
    const easing = () => doc.getAnimations({ subtree: true }).some((a) => a.transitionProperty?.startsWith("padding"));
    const loop = () => { measure(); frame = easing() ? requestAnimationFrame(loop) : 0; };
    const start = (e) => { if (e.propertyName.startsWith("padding") && !frame) frame = requestAnimationFrame(loop); };
    doc.addEventListener("transitionrun", start);
    return () => { cancelAnimationFrame(frame); doc.removeEventListener("transitionrun", start); };
  });
</script>

<div class="fw-tabs">
  {#each links as l}
    <div class="fw-link-line" style:left="{l.left}px" style:top="{l.top}px" style:height="{l.height}px"
      style:background="linear-gradient(to bottom, {l.from}, {l.to})"></div>
  {/each}
  {#each tabs as t (t.box)}<Tab {t} {pick} />{/each}
</div>
