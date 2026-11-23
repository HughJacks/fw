<!-- Header.svelte — every pericope's header (the terminal's H box): what the block is, its facts, backlinks, a kind's
     maybes, its kinds, its title. Folded to one line, its title with what it is and how many backlinks, until you're in
     it (↑ from the first line, or a click), when it unfolds to every field (the user, 2026-11-22: the header weighed as
     much as a small pericope or a picture); always in its box, with a tab, H, as a block has its number. Unfolded it's
     always the same four lines (the user, 2026-11-19: every header a fixed height, so going from one to another changes
     nothing there). One header for every pericope (the user, 2026-11-19: "header and body can be shared
     between all pericopes because every pericope has one"): it stays on the page and shows whichever is open (p). What it
     shows is worked out by Pericope.svelte ($derived there) and handed in; the title field is bound both ways. -->
<script>
  import Kinds from "./Kinds.svelte";
  import { pressed } from "./keys.svelte.js";
  import { startReview } from "./review.svelte.js";

  // p: the pericope as the core said it; id: its id (null while home's waiting one isn't made); facts: created,
  // updated, words, last visited;
  // auto: the title's placeholder; title: what's in the title field; go: open a place; typed(), left(): the title typed
  // in, left; kindsDone(said): a kind answered; body(): ↓ or ↵ from the title, into the writing
  // backs(): into the backlinks above it (Backlinks.svelte)
  let { p, type = null, id, facts, auto, title = $bindable(), go, typed, left, kindsDone, body, backs = null } = $props();
  let titleInput, kinds = $state(), backsChip = $state();
  let hasBacks = $derived(!!p.backlinkRows?.length);

  function titleKey(e) {
    if (pressed(e, "done")) return;   // (send it away: main.js's, not ↵ here)
    if (e.key === "Enter" || e.key === "ArrowDown") { e.preventDefault(); body(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); kinds?.focus(); }
  }
  const review = () => startReview(id, p.shown, p.maybes, go);
  // (folded: what it is, and how many point here)
  let shownType = $derived(type ?? p.type);   // (what it is: Pericope.svelte's, as you write; else the core's)
  let folded = $derived(shownType + (p.backlinks ? ` · ← ${p.backlinks.split(" · ")[0]}` : ""));
  // (a click on the folded line, anywhere on it: into the title, which unfolds it)
  function into(e) { if (!e.currentTarget.contains(document.activeElement)) titleInput.focus(); }

  /** The cursor in the title field (↑ from the writing's first line). */
  export function focusTitle() { titleInput.focus(); }
  /** The kinds line (after a kind's answered). */
  export function focusKinds() { kinds?.focus(); }
  /** The backlinks line (↓ out of the list above). */
  export function focusBacklinks() { backsChip?.focus({ preventScroll: true }); }   // (the list scrolls the page back itself)
  /** Whether the title field has the focus (the store's title isn't put over one being written). */
  export function editingTitle() { return document.activeElement === titleInput; }
</script>

<div class="fw-header">
  <span class="fw-gutter">H</span>
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions (keys reach it through the title) -->
  <div class="fw-box fw-hbox" onclick={into}>
    <div class="fw-more"><div class="fw-more-in">
    <div class="fw-typerow"><span class="fw-label">{shownType}</span><span class="fw-dim">{facts}</span></div>
    <div class="fw-fields">
      <!-- (every field shown, an empty one saying "none": the user, 2026-11-21, "dont hide metadata in headers"; a kind's maybes
           too. Paraphrases of it count among its backlinks: a pericope is never a paraphrase itself) -->
      <div class="fw-row-fields">
        <div class="fw-field"><span class="fw-key">backlinks</span>
          {#if hasBacks}
            <!-- (↵ or ↑: up into the list of them above the header, the user, 2026-11-23: "a reverse of the go to") -->
            <button class="fw-chip fw-chip-backs" bind:this={backsChip} onclick={() => backs?.()}
              onkeydown={(e) => { if (e.key === "Enter" || e.key === "ArrowUp") { e.preventDefault(); backs?.(); } else if (e.key === "ArrowDown") { e.preventDefault(); kinds?.focus(); } }}>
              {p.backlinks} · ↑</button>
          {:else}<span class:fw-none={!p.backlinks}>{p.backlinks || "none"}</span>{/if}
        </div>
        {#if p.kind}
          <div class="fw-field"><span class="fw-key">maybes</span>
            {#if p.maybes?.length}
              <button class="fw-chip fw-chip-guess" onclick={review}
                onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); review(); } else if (e.key === "ArrowDown") { e.preventDefault(); kinds?.focus(); } }}>
                {p.maybes.length} · ↵ review them</button>
            {:else}<span class="fw-none">none</span>{/if}
          </div>
        {/if}
      </div>
      <div class="fw-field"><span class="fw-key">kinds</span>
        <Kinds bind:this={kinds} {id} tokens={p.kindTokens || []} done={kindsDone} open={(k) => go(`#/p/${k}`)} down={focusTitle}
          up={hasBacks ? () => backsChip?.focus() : null} /></div>
    </div>
    </div></div>
    <div class="fw-field fw-titlerow"><span class="fw-key">title</span>
      <input class="fw-input fw-title" bind:this={titleInput} bind:value={title} placeholder={auto || "none"} oninput={typed} onblur={left} onkeydown={titleKey} />
      <span class="fw-folded">{folded}</span>
    </div>
  </div>
</div>
