<!-- Tab.svelte — one block's tab in the gutter and its line to its box (tabs.js measures; Tabs.svelte lays them out).
     Every block has its own: it
     sits where its block's content puts it, and comes in or goes out where it stands as the block joins or leaves your
     path. Nothing glides from one block to another; it moves only as its block does (the room easing out, the writing).
     A click selects its block whole (`pick`). -->
<script>
  import { fade } from "svelte/transition";

  let { t, pick } = $props();
  // (comes and goes in place; at once when nothing moves: the tests, reduced motion)
  const show = (node) => fade(node, { duration: 0 });   // (no fades for now, it's there or it isn't)
  const cls = (base) => base + (t.focus ? (base === "fw-tab" ? " fw-tab-focus" : " fw-line-focus") : "")
    + (t.filled ? (base === "fw-tab" ? " fw-tab-filled" : " fw-line-filled") : "") + (t.quote ? (base === "fw-tab" ? " fw-tab-quote" : " fw-line-quote") : "")
    + (t.expr ? (base === "fw-tab" ? " fw-tab-expr" : " fw-line-expr") : "");
</script>

<div class={cls("fw-tab-line")} style:left="{t.lineLeft}px" style:top="{t.top + t.height / 2}px" style:width="{t.lineWidth}px" transition:show></div>
<div class={cls("fw-tab")} style:left="{t.left}px" style:top="{t.top}px" style:width="{t.width}px" style:height="{t.height}px" transition:show
  onmousedown={(e) => { e.preventDefault(); pick(t.box); }} role="button" tabindex="-1">{t.label}</div>
