<!-- ActionsMenu.svelte — the ⌘/ menu (the terminal's Ctrl+/ menu): what can be done where the cursor is. Typing
     filters it (nested commands still found); ↑↓ move, Enter runs, → opens a submenu, ← or Esc goes back. A command
     closes the menu (one-shot) or stays open (toggles: its label drawn again, saying what's on now). The commands
     shown are $derived from what's typed, the submenu, and `rev` (the place's state after a toggle). -->
<script>
  import { onMount, untrack } from "svelte";
  // editor: where it opened; commands(editor, ctx); run(editor, name, ctx); root(): the page's editor (after a toggle)
  // moved(editor): a toggle redrew the page, the cursor now in `editor` (the focus goes back there)
  let { left, top, editor, commands, run, root, dismiss, moved = () => {} } = $props();
  let query = $state(""), sel = $state(0), group = $state(null), rev = $state(0), input = $state();
  let ed = untrack(() => editor), ctx = ed.context();   // (where it is: the page's again after a toggle)
  let shown = $derived.by(() => {
    rev;
    const all = commands(ed, ctx), q = query.toLowerCase();
    if (q) return all.filter((c) => !c.name.startsWith("group:") && c.label.toLowerCase().includes(q));   // (nested ones found too)
    return all.filter((c) => (group ? c.group === group : !c.group));
  });
  let at = $derived(Math.max(0, Math.min(sel, shown.length - 1)));

  async function pick() {
    const c = shown[at];
    if (!c) return;
    if (c.name.startsWith("group:")) { group = c.name.slice(6); sel = 0; query = ""; return; }
    if (!c.stays) dismiss(true);
    const got = await run(ed, c.name, ctx);
    if (c.stays) {   // (its labels say what's on now, where the cursor is now: a toggle may have drawn the page again)
      ed = got?.view && !got.gone ? got : ed.gone ? root() : ed;
      moved(ed); ctx = ed.context(); rev++; input?.focus();
    }
  }
  function key(e) {
    if (e.key === "ArrowDown") sel = Math.min(shown.length - 1, at + 1);
    else if (e.key === "ArrowUp") sel = Math.max(0, at - 1);
    else if (e.key === "Enter") { e.preventDefault(); pick(); return; }
    else if (e.key === "ArrowRight" && shown[at]?.name.startsWith("group:")) { e.preventDefault(); pick(); return; }
    else if ((e.key === "ArrowLeft" || e.key === "Escape") && group && !query) { group = null; sel = 0; }
    else if (e.key === "Escape") { e.preventDefault(); dismiss(true); return; }
    else return;
    e.preventDefault();
  }
  onMount(() => input.focus());
</script>

<div class="fw-menu" style:left="{left}px" style:top="{top}px">
  <div class="fw-prompt"><span class="fw-dim">do › </span>
    <input class="fw-input" bind:this={input} bind:value={query} oninput={() => (sel = 0)} onkeydown={key}
      onblur={() => setTimeout(() => { if (!input?.closest(".fw-menu")?.contains(document.activeElement)) dismiss(false); }, 150)} />
  </div>
  <div class="fw-rows">
    {#if !shown.length}<div class="fw-dim">nothing to do here</div>{/if}
    {#each shown as c, n}
      <div class="fw-row{n === at ? ' fw-sel' : ''}" onmousedown={(e) => { e.preventDefault(); sel = n; pick(); }} role="button" tabindex="-1">
        <span>{c.label}</span><span class="fw-dim">{c.key || (c.name.startsWith("group:") ? "→" : "")}</span>
      </div>
    {/each}
  </div>
  <div class="fw-dim fw-foot">{shown[at] ? shown[at].note : ""}</div>
</div>
