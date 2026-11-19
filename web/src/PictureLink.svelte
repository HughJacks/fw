<!-- PictureLink.svelte — Add a picture from a link: the address, then `add(url)` downloads it (its answer, an error,
     said in the footer; null when it's done). Esc cancels. -->
<script>
  import { onMount } from "svelte";
  let { left, top, add, dismiss } = $props();
  let url = $state(""), said = $state("↵ downloaded into fw (its own copy, never the link) · esc cancel"), input = $state();
  async function key(e) {
    if (e.key === "Escape") { e.preventDefault(); dismiss(true); return; }
    if (e.key !== "Enter") return;
    e.preventDefault();
    said = "downloading…";
    const error = await add(url);
    if (error) said = error;
  }
  onMount(() => input.focus());
</script>

<div class="fw-menu" style:left="{left}px" style:top="{top}px">
  <div class="fw-prompt"><span class="fw-dim">picture › </span><input class="fw-input" bind:this={input} bind:value={url} onkeydown={key} /></div>
  <div class="fw-dim fw-foot">{said}</div>
</div>
