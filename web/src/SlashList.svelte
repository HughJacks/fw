<!-- SlashList.svelte — the / menu's commands at the cursor (menu.js's plugin keeps `cmds` and `sel` as what's typed
     after the / changes; the keys stay in the editor). A click runs one. -->
<script>
  let { left, top, cmds = [], sel = 0, run } = $props();
</script>

<div class="fw-menu" style:left="{left}px" style:top="{top}px">
  {#each cmds as c, n}
    <div class="fw-row{n === sel ? ' fw-sel' : ''}" onmousedown={(e) => { e.preventDefault(); run(c); }} role="button" tabindex="-1"><span>{c.label}</span></div>
  {/each}
  {#if cmds[sel]}<div class="fw-dim fw-foot">{cmds[sel].note}</div>{/if}
</div>
