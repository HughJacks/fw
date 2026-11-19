<!-- SearchBox.svelte — a search at the cursor (the / menu's Quote a block, ⌘/'s Link and Paraphrases…): home's rows,
     the search service's answers mixed in after a pause (a placeholder while they come; rows move, new ones ease in). `keep(row)`
     which rows to offer; `foot(row)` what Enter will do; `onPick(row, shift, query)` once one's picked (the box gone).
     Esc closes it. What's typed, the rows, the selection are $state; the footer is $derived. -->
<script>
  import { onMount } from "svelte";
  import { flip } from "svelte/animate";
  import { fade } from "svelte/transition";
  import { api } from "./api.js";
  import { keep as keepSel, MOVE } from "./results.js";

  let { left, top, prompt, keep = () => true, foot: say, onPick, dismiss } = $props();
  let query = $state(""), rows = $state([]), sel = $state(0), pending = $state(false), input = $state();
  let seq = 0, timer = null;
  let footText = $derived(rows[sel] ? say(rows[sel]) : "");

  async function search(meaning) {
    const n = ++seq, q = query;
    const r = await api(`/api/search?q=${encodeURIComponent(q)}${meaning ? "&meaning=1" : ""}`);
    if (!r.ok || n !== seq) return;
    const was = meaning ? rows[sel]?.key : null;   // (the search service's answer: what's selected stays selected, wherever it moves)
    rows = r.body.rows.filter(keep).map((x) => (x.key === "new" ? { ...x, label: q ? `+ new pericope “${q}”` : "+ new pericope" } : x));
    if (meaning) pending = false;
    sel = keepSel(rows, was, rows.length > 1 ? 1 : 0);
  }
  function typed() { pending = !!query; search(false); clearTimeout(timer); timer = setTimeout(() => search(true), 400); }
  function pick(shift) {
    const it = rows[sel];
    if (!it) return;
    dismiss(false);
    onPick(it, shift, query);
  }
  function key(e) {
    if (e.key === "ArrowDown") sel = Math.min(rows.length - 1, sel + 1);
    else if (e.key === "ArrowUp") sel = Math.max(0, sel - 1);
    else if (e.key === "Enter") { e.preventDefault(); pick(e.shiftKey); return; }
    else if (e.key === "Escape") { e.preventDefault(); dismiss(true); return; }
    else return;
    e.preventDefault();
  }
  onMount(() => { search(false); input.focus(); return () => clearTimeout(timer); });
</script>

<div class="fw-menu" style:left="{left}px" style:top="{top}px">
  <div class="fw-prompt"><span class="fw-dim">{prompt}</span>
    <input class="fw-input" bind:this={input} bind:value={query} oninput={typed} onkeydown={key}
      onblur={() => setTimeout(() => { if (document.activeElement !== input) dismiss(false); }, 150)} />
  </div>
  <div class="fw-rows">
    {#each rows.slice(0, 12) as row, n (row.key + (row.at || ""))}
      <div class="fw-row{n === sel ? ' fw-sel' : ''}{row.dim ? ' fw-dim' : ''}" animate:flip={{ duration: MOVE }} in:fade={{ duration: MOVE }}
        onmousedown={(e) => { e.preventDefault(); sel = n; pick(false); }} role="button" tabindex="-1">
        <span class="fw-row-label">{row.label}</span><span class="fw-dim">{row.right}</span>
      </div>
    {/each}
    {#if pending}<div class="fw-pending">finding more by meaning…</div>{/if}
  </div>
  <div class="fw-dim fw-foot">{footText}</div>
</div>
