<!-- Kinds.svelte — the header's kinds line (the terminal's): a token per answer (a yes, white on blue; a no, muted,
     "not …"), then a model's guesses that count (applied, "poem·"), then a +. ←/→ between them; Backspace on an applied
     guess says no, on an answer takes it back; Enter on one (or a double click) opens the kind; on the +, or typing
     anywhere on the line, the kinds picker: Enter yes, Shift+Enter no, "+ new kind" makes one. Each answer is the
     store's (set_kind). The picker's rows are $derived from what's typed. -->
<script>
  import { tick } from "svelte";
  import { api } from "../lib/api.js";
  import { opened } from "../state/state.svelte.js";

  // id: the block; tokens: the core's kindTokens; done(said): an answer changed; open(kind); down(): ↓ out (the title);
  // up(): ↑ out (the backlinks, when there are some)
  let { id, tokens = [], done, open, down, up = null } = $props();
  let chips = [];   // (each token's element, then the +'s)
  let picking = $state(null);   // the picker open: {left, top, typed, kinds, sel}
  let pickInput = $state();
  let pickerOpen = $derived(!!picking);
  $effect(() => { if (pickerOpen) return opened(); });   // (a menu open over the page: state.svelte.js)

  const label = (t) => (t.mark === "no" ? `not ${t.name}` : t.mark === "applied" ? `${t.name}·` : t.mark === "guess" ? `${t.name}?` : t.name);
  const hint = (t) => (t.mark === "guess" ? `a model's guess (${t.p}): ↵ yes, ⌫ no` : t.mark === "applied" ? "a model's, applied: ⌫ no" : "↵ open it · ⌫ take it back");
  let rows = $derived.by(() => {
    if (!picking) return [];
    const q = picking.typed.trim().toLowerCase();
    const found = picking.kinds.filter((k) => k.name.toLowerCase().includes(q));
    const exact = picking.kinds.some((k) => k.name.toLowerCase() === q);
    return [...found, ...(q && !exact ? [{ id: null, name: picking.typed.trim(), made: true }] : [])];
  });

  async function answer(kind, yes, name = "") {
    const r = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "kind", block: id, kind, answer: yes, name }) });
    done(r.ok ? "" : r.body.error || "couldn't");
  }
  /** The kinds picker, under `at`, `typed` already in it. */
  async function picker(at, typed) {
    const r = await api("/api/kinds");
    const rect = at.getBoundingClientRect();
    picking = { left: rect.left, top: rect.bottom + 4, typed, kinds: r.ok ? r.body.kinds : [], sel: 0 };
    await tick();
    pickInput?.focus();
  }
  function pick(no) {
    const k = rows[Math.max(0, Math.min(picking.sel, rows.length - 1))];
    if (!k) return;
    picking = null;
    answer(k.id, !no, k.made ? k.name : "");
  }
  function closePicker() { picking = null; chips[tokens.length]?.focus(); }
  function pickKey(e) {
    if (e.key === "ArrowDown") picking.sel = Math.min(rows.length - 1, picking.sel + 1);
    else if (e.key === "ArrowUp") picking.sel = Math.max(0, picking.sel - 1);
    else if (e.key === "Enter") { e.preventDefault(); pick(e.shiftKey); return; }
    else if (e.key === "Escape") { e.preventDefault(); closePicker(); return; }
    else return;
    e.preventDefault();
  }
  function chipKey(e, n) {
    const t = tokens[n], all = chips.slice(0, tokens.length + 1);
    if (e.key === "ArrowLeft") all[Math.max(0, n - 1)]?.focus();
    else if (e.key === "ArrowRight") all[Math.min(all.length - 1, n + 1)]?.focus();
    else if (e.key === "ArrowDown") down();
    else if (e.key === "ArrowUp" && up) up();
    else if (e.key === "Enter" && !t) picker(chips[tokens.length], "");
    else if (e.key === "Enter" && t.mark === "guess") answer(t.kind, true);
    else if (e.key === "Enter" || (e.key === "o" && e.ctrlKey)) open(t.kind);
    else if ((e.key === "Backspace" || e.key === "Delete") && t) answer(t.kind, t.mark === "guess" || t.mark === "applied" ? false : null);
    else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) picker(chips[tokens.length], e.key);
    else return;
    e.preventDefault();
  }

  /** The focus on the line (its last token, else the +). */
  export function focus() { (chips[tokens.length - 1] || chips[tokens.length])?.focus(); }
</script>

<div class="fw-kinds">
  {#each tokens as t, n (t.kind + t.mark)}
    <button class="fw-chip fw-chip-{t.mark}" title={hint(t)} bind:this={chips[n]} onkeydown={(e) => chipKey(e, n)} ondblclick={() => open(t.kind)}>{label(t)}</button>
  {/each}
  {#if !tokens.length}<span class="fw-none">none</span>{/if}   <!-- (an empty field says so) -->
  <button class="fw-chip fw-chip-plus" title="a tag: ↵, or type its name" bind:this={chips[tokens.length]}
    onkeydown={(e) => chipKey(e, tokens.length)} onclick={() => picker(chips[tokens.length], "")}>+</button>
</div>

{#if picking}
  <div class="fw-menu" style:position="fixed" style:left="{picking.left}px" style:top="{picking.top}px">
    <div class="fw-prompt"><span class="fw-dim">tag › </span>
      <input class="fw-input" bind:this={pickInput} bind:value={picking.typed} oninput={() => (picking.sel = 0)} onkeydown={pickKey}
        onblur={() => setTimeout(() => { if (document.activeElement !== pickInput) picking = null; }, 150)} />
    </div>
    <div class="fw-rows">
      {#each rows as k, n}
        <div class="fw-row{n === Math.min(picking.sel, rows.length - 1) ? ' fw-sel' : ''}" role="button" tabindex="-1"
          onmousedown={(e) => { e.preventDefault(); picking.sel = n; pick(false); }}>{k.made ? `+ new tag “${k.name}”` : k.name}</div>
      {/each}
    </div>
    <div class="fw-dim fw-foot">↵ it is one · ⇧↵ it isn't · esc</div>
  </div>
{/if}
