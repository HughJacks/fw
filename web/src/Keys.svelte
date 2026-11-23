<!-- Keys.svelte — the keys page (#/keys): every command and its key. Enter (or a click), then the new keys, rebinds
     it; Backspace puts the default back; a key another command has, or a browser keeps, is refused and said so. Each
     row's key is derived from the bindings (a rune, keys.svelte.js): a change shows at once. -->
<script>
  import { tick } from "svelte";
  import { COMMANDS, KEPT, keyOf, nameOf, pretty, saveKeys, userKeys } from "./keys.svelte.js";
  import { ui } from "./state.svelte.js";

  let { home } = $props();   // (Esc: home)
  const where = { editor: "writing", home: "home", everywhere: "anywhere", kinds: "a kind's list" };
  let note = $state("");
  let rows = [];   // (each row's element, to move the focus)
  let rowsShown = $derived(COMMANDS.map((c) => ({ ...c, key: pretty(keyOf(c.id)), mine: !!userKeys()[c.id] })));

  const focus = async (n) => { await tick(); rows[Math.max(0, Math.min(COMMANDS.length - 1, n))]?.focus(); };
  $effect(() => { focus(0); });

  function capture(n) {   // the next keys pressed, its key
    const c = COMMANDS[n];
    ui.capturing = c.id;
    const take = (e) => {
      const name = nameOf(e);
      if (!name) return;   // (a modifier alone: wait for the key)
      e.preventDefault();
      e.stopPropagation();
      window.removeEventListener("keydown", take, true);
      ui.capturing = null;
      if (name === "Escape") { note = ""; focus(n); return; }
      const taken = COMMANDS.find((x) => x.id !== c.id && keyOf(x.id) === name && (x.where === c.where || x.where === "everywhere" || c.where === "everywhere"));
      if (KEPT.has(name)) { note = `${pretty(name)}: your browser keeps that one; ${c.id} keeps ${pretty(keyOf(c.id))}`; focus(n); return; }
      if (taken) { note = `${pretty(name)} is ${taken.id}'s; ${c.id} keeps ${pretty(keyOf(c.id))} (change ${taken.id}'s first)`; focus(n); return; }
      saveKeys({ ...userKeys(), [c.id]: name }).then(() => { note = `${c.id}: ${pretty(name)}`; focus(n); });
    };
    window.addEventListener("keydown", take, true);
  }

  function onkey(e, n) {
    if (ui.capturing) return;
    if (e.key === "ArrowDown") focus(n + 1);
    else if (e.key === "ArrowUp") focus(n - 1);
    else if (e.key === "Enter") capture(n);
    else if (e.key === "Backspace" || e.key === "Delete") {
      const k = userKeys(); delete k[COMMANDS[n].id];
      saveKeys(k).then(() => { note = `${COMMANDS[n].id}: the default again`; focus(n); });
    } else if (e.key === "Escape") home();
    else return;
    e.preventDefault();
  }
</script>

<div class="fw-dim mb-2">fw  ·  keys: Enter (or a click) then the new keys; Backspace: the default; esc: home</div>
<div class="fw-box">
  {#each rowsShown as c, n (c.id)}
    <div class="fw-keyrow" tabindex="0" data-id={c.id} bind:this={rows[n]} onclick={() => capture(n)} onkeydown={(e) => onkey(e, n)} role="button">
      <span class={c.mine ? "fw-key-new" : ""}>{ui.capturing === c.id ? "press the keys…" : c.key}</span><span>{c.label}</span><span class="fw-dim">{where[c.where]}</span>
    </div>
  {/each}
  <div class="fw-dim fw-foot">{note || "⌘Z, ⌘C, ⌘V and the like aren't here: they're the browser's and the text's"}</div>
</div>
