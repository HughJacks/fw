<!-- Members.svelte — a kind's members on its own page, below what it says (the user, 2026-11-22: "i agree with your
     thoughts of showing a kinds members"): a line each (fw_web.members_json: your answers, newest first, then the
     model's sure guesses, dim, then its maybes, dimmer), each opening as itself; a guess answered with Y or N, one of yours taken out with N. Worked out, never stored as quotes. ↓ past the kind's
     last block comes here (enter), ↑ from its first row goes back up (up), ↓ past its last on to the search (down). -->
<script>
  import { tick } from "svelte";
  import { api } from "./api.js";
  import { keyOf, pressed, pretty } from "./keys.svelte.js";
  import { say } from "./state.svelte.js";
  import { reveal } from "./scrolling.js";

  let { rows, kind, go, up = null, down = null } = $props();   // (kind: whose they are)
  let sel = $state(-1), box = $state();
  let sure = $derived(rows.filter((m) => m.dim && !m.maybe).length), maybe = $derived(rows.filter((m) => m.maybe).length);
  /** A guess answered (Y yes, N no): said, the row after it selected; the page follows the store (Pericope.svelte). */
  async function answer(m, yes) {
    const got = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "kind", block: m.key, kind, answer: yes }) });
    say(got.ok ? `${m.title}: ${yes ? "yes" : "no"}` : got.body.error || "couldn't");
  }

  /** Into the rows, the first selected. */
  export async function enter() { sel = 0; await tick(); box?.focus(); }
  const open = (m) => go(`#/p/${m.open}` + (m.key !== m.open ? `@${m.key}` : ""));
  function onkey(e) {
    if (e.key === "ArrowDown") { if (sel >= rows.length - 1) { sel = -1; down?.(); } else sel++; }
    else if (e.key === "ArrowUp") { if (sel <= 0) { sel = -1; up?.(); } else sel--; }
    else if (e.key === "Enter" && rows[sel]) open(rows[sel]);
    else if (rows[sel]?.dim && pressed(e, "kindYes")) answer(rows[sel], true);
    else if (rows[sel] && pressed(e, "kindNo")) answer(rows[sel], false);   // (a guess denied, or one of yours taken out)
    else return;
    e.preventDefault();
  }
  $effect(() => { sel; tick().then(() => reveal(box?.querySelector(".fw-sel"))); });   // (smoothly, with room: scrolling.js)
</script>

<div class="fw-rows fw-library fw-members" tabindex="-1" bind:this={box} onkeydown={onkey} onblur={() => (sel = -1)} role="listbox">
  <div class="fw-hint">{rows.length - sure - maybe} tagged{sure ? `, ${sure} the model's sure of` : ""}{maybe ? `, ${maybe} maybe` : ""}</div>
  {#each rows as m, n (m.key)}
    <div class={"fw-row" + (n === sel ? " fw-sel" : "") + (m.dim ? " fw-dim" : "") + (m.maybe ? " fw-maybe" : "")} data-pericope={m.open} role="option" aria-selected={n === sel}
      tabindex="-1" onmousedown={(e) => { e.preventDefault(); open(m); }}>
      <span class="fw-row-label">{m.title}{m.maybe ? "?" : ""}</span><span class="fw-dim">{n !== sel ? "" : m.dim ? `${pretty(keyOf("kindYes"))} yes · ${pretty(keyOf("kindNo"))} no  ` : `${pretty(keyOf("kindNo"))} take out  `}{m.right}</span>
    </div>
  {/each}
</div>
