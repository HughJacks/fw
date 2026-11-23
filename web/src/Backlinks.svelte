<!-- Backlinks.svelte — what points at the pericope open, above its header: the "go to" list below turned over (the
     user, 2026-11-23: "the exact same structure as go to below but just reverse order"): its rows, oldest at the top,
     the newest nearest, then a rule, then "links to this", then the pericope. Each row as the go-to's: the pericope it's
     in, and at the right how it points (quote, link, paraphrase) and when (fw_web.backlink_rows). At rest the rows hang
     just off the top of the window (out of the page's flow, right above the rule, which sits near the window's top), a
     sliver of the nearest showing ("cut off"), so where they hang is just where they are once they're in; scrolling up at
     the page's top, ↵ or ↑ on the header's backlinks line, or a click on the sliver brings them in (they join the page,
     the page scrolled by as much, so nothing moves) and they scroll like the page; once you're not looking at them
     (scrolled back past them, or ↓ past the nearest, or Esc) they hang off the top again, the page where it was. Enter
     opens one where it points, on the ⌘[ trail. -->
<script>
  import { tick } from "svelte";
  import { reveal, showList, scrollPage } from "./scrolling.js";
  import { TEST } from "./api.js";

  let { rows, go, out } = $props();   // (out(): back to the header)
  let open = $state(false), sel = $state(-1), box = $state();
  let quiet = 0;   // (until when the page's own scrolling, ours, isn't read as you scrolling)
  let leaving = null;   // (on its way out: one leaving at a time)
  // (the user, 2026-11-23: "after a certain amount of inactivity or mouse leaving the area we should scroll back to the
  // normal position with the pericope at the top of the screen")
  const IDLE = TEST ? 800 : 6000, AWAY = TEST ? 300 : 1200;   // ms with nothing done in them; ms after the mouse leaves them
  let idle = null;
  function wait(ms) { clearTimeout(idle); idle = open ? setTimeout(() => leave(box?.contains(document.activeElement)), ms) : null; }
  const busy = () => { if (open && !leaving) wait(IDLE); };

  const room = (h) => document.documentElement.style.setProperty("--backs-room", `${h}px`);
  const height = () => box?.offsetHeight || 0;
  /** In: it joins the page, scrolled by as much so nothing moves; `focus`: from the keys, the nearest selected. */
  export async function enter(focus = true) {
    if (!rows.length) return;
    if (!open) {
      open = true;
      await tick();
      room(height());   // (the page that much taller, so a short one can scroll by it too)
      await tick();
      quiet = Date.now() + 150;
      scrollBy(0, height());
    }
    busy();
    if (focus) {   // (from the keys: the nearest selected, and the whole list shown with room above it, if it fits)
      sel = rows.length - 1;
      box?.focus({ preventScroll: true });
      await tick();
      showList(box?.querySelector(".fw-row"), box?.querySelector(".fw-sel"), 160);
    }
  }
  /** Out: the page scrolled back, smoothly, to where the pericope is at the top (as far down as the rows are tall),
   * then the rows hung above again, nothing moving (`back`: the header's backlinks line in focus). */
  function leave(back = true) {
    if (!open) return Promise.resolve();
    clearTimeout(idle);
    return (leaving ||= (async () => {
      const h = height();
      if (back) out?.();
      if (scrollY < h - 1) {
        quiet = Infinity;
        scrollPage(h - scrollY);
        for (const end = Date.now() + 900; Math.abs(scrollY - h) > 1 && Date.now() < end;) await new Promise(requestAnimationFrame);
      }
      open = false; sel = -1;
      await tick();
      quiet = Date.now() + 150;
      scrollBy(0, -h);   // (they're just above the window's top by now: hung there, nothing seen moving)
      room(0);
      leaving = null;
    })());
  }
  function onkey(e) {
    if (e.key === "ArrowUp") move(Math.max(0, sel - 1));
    else if (e.key === "ArrowDown") { if (sel >= rows.length - 1) leave(); else move(sel + 1); }
    else if (e.key === "Enter" && rows[sel]) go(`#/p/${rows[sel].open}@${rows[sel].at}`);
    else if (e.key === "Escape") leave();
    else return;
    e.preventDefault();
  }
  /** Scrolling up at the page's top: in (the wheel's own scroll then carries on up into them). */
  function onwheel(e) { if (!open && rows.length && scrollY <= 0 && e.deltaY < 0) enter(false); else busy(); }
  /** Scrolled back down to where they hang, not in them: out, nothing moving (hung, they're just where they were). */
  let lastY = 0;
  function onscroll() {
    const down = scrollY > lastY;
    lastY = scrollY;
    if (!open || leaving || !down || Date.now() < quiet || box?.contains(document.activeElement)) return;
    if (scrollY >= height() - 1) leave(false);
  }
  $effect(() => { rows; return () => { if (open) { open = false; room(0); } }; });   // (another pericope: hung up again)
  function move(to) { sel = to; busy(); tick().then(() => reveal(box?.querySelector(".fw-sel"))); }
  $effect(() => () => clearTimeout(idle));
</script>

<svelte:window {onwheel} {onscroll} />
{#if rows.length}
  <div class="fw-backlinks" onmouseenter={busy} onmousemove={busy} onmouseleave={() => { if (open && !leaving) wait(AWAY); }} role="presentation">
    <div class="fw-backs-at">
      <div class="fw-rows fw-library fw-backs" class:fw-backs-open={open} tabindex="-1"
        bind:this={box} onkeydown={onkey} onfocusout={(e) => { if (!box.contains(e.relatedTarget)) sel = -1; }} role="listbox">
        {#each rows as r, n (r.key)}
          <div class={"fw-row fw-back" + (n === sel ? " fw-sel" : "")} data-pericope={r.open} role="option" aria-selected={n === sel} tabindex="-1"
            onmousedown={(e) => { e.preventDefault(); if (!open) enter(); else go(`#/p/${r.open}@${r.at}`); }}>
            <span class="fw-row-label">{r.title}</span><span class="fw-dim">{r.kind}  {r.right}</span>
          </div>
        {/each}
      </div>
    </div>
    <div class="fw-prompt fw-go fw-go-up"><span class="fw-dim">links to this</span></div>
  </div>
{/if}
