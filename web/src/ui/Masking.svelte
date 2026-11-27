<!-- Masking.svelte — masking mode (the terminal's): a quote's whole text, what shows bright and what's hidden dim,
     each shown span between red ‹ › brackets; no typing. [ on a selection shows exactly it, ] hides it; [ or ] at a
     point opens or closes there (its partner inferred at the edge of the stretch, as Hazel's holes); Backspace or
     Delete on a bracket takes it out (the spans either side join); Tab and Shift+Tab jump between brackets; the arrows
     and a click move the caret as in any text; Esc or Enter finishes (touching spans merge), saved as one action (^Z
     takes it back). The rules are the core's (fw_lens, through POST /api/maskop): the page only says which key, where.
     A quote or a picture inside it is one unit, shown or hidden whole. The mask is $state; every bracket and piece is
     $derived from it and the quote's lines. -->
<script>
  import { onMount, tick, untrack } from "svelte";
  import { api } from "../lib/api.js";
  import { quoteEl } from "../expr/views.js";

  // box: the quote's own box (what it shows hidden meanwhile); draft, lines, mask: the core's; finish(draft, mask)
  // saves it; cancel() leaves it as it was; close() takes masking down
  let { box, draft, lines, mask: first, finish, cancel, close } = $props();
  let mask = $state(untrack(() => first)), panel = $state();

  const spans = (m) => m.reduce((out, x, n) => (n % 2 ? (out[out.length - 1].push(x), out) : [...out, [x]]), []);
  const shown = (m, a, b) => spans(m).some(([o, c]) => o <= a && b <= c && o < c);
  // what's drawn: units (a quote, a picture) and groups (a block's lines), each line its brackets and pieces
  let parts = $derived.by(() => {
    const out = [];
    let group = null, gid;
    for (const line of lines) {
      if (line.t !== "text") { group = null; out.push({ unit: line, on: shown(mask, line.start, line.end) }); continue; }
      if (!group || line.block !== gid) { group = { rows: [] }; gid = line.block; out.push(group); }
      const row = [], end = line.start + line.text.length;
      const cuts = new Set([line.start, end]);
      mask.forEach((x) => { if (x >= line.start && x <= end) cuts.add(x); });
      const points = [...cuts].sort((a, b) => a - b);
      const bracket = (p) => mask.forEach((x, k) => { if (x === p) row.push({ br: k % 2 ? "close" : "open", off: p, k }); });
      if (!line.text) { bracket(line.start); row.push({ zw: true, off: line.start, on: shown(mask, line.start, line.start + 1) }); }
      for (let k = 0; k + 1 < points.length; k++) {
        const [a, b] = [points[k], points[k + 1]];
        bracket(a);
        row.push({ text: line.text.slice(a - line.start, b - line.start), off: a, on: shown(mask, a, b) });
      }
      if (line.text) bracket(end);
      group.rows.push(row);
    }
    return out;
  });

  /** A quote inside, drawn as any quote (views.js), with what it shows. */
  function quoteUnit(node, part) {
    const q = quoteEl(part.unit.data, null);
    q.classList.add("fw-unit", part.on ? "fw-unit-shown" : "fw-unit-hid");
    q.dataset.off = part.unit.start;
    q.dataset.zw = "";
    q.contentEditable = "false";
    node.append(q);
    return { update(p) { q.classList.toggle("fw-unit-shown", p.on); q.classList.toggle("fw-unit-hid", !p.on); } };
  }

  /** The draft offset a DOM point (node, offset) is at. */
  function offsetOf(node, offset) {
    if (!node) return null;
    const host = node.nodeType === 3 ? node.parentElement : node.childNodes[offset] || node;
    const at = host.closest?.("[data-off]") || host.querySelector?.("[data-off]");
    if (!at) return null;
    if (node.nodeType === 3 && at.dataset.zw === undefined) return +at.dataset.off + offset;
    return +at.dataset.off;
  }
  /** The caret put back at draft offset `p`. */
  function caretAt(p) {
    if (!panel) return;   // (finished meanwhile)
    let best = null;
    for (const s of panel.querySelectorAll("[data-off]")) {
      const o = +s.dataset.off, len = s.dataset.zw !== undefined || s.classList.contains("fw-br") ? 0 : s.textContent.length;
      if (o <= p && p <= o + len && !s.classList.contains("fw-br")) { best = [s, p - o]; break; }
    }
    if (!best) return;
    const [s, k] = best, sel = window.getSelection();
    const text = s.firstChild && s.firstChild.nodeType === 3 ? s.firstChild : s;
    sel.collapse(text, s.dataset.zw !== undefined ? 0 : Math.min(k, text.length ?? 0));
  }

  async function op(body, caret) {
    const r = await api("/api/maskop", { method: "POST", body: JSON.stringify({ draft, mask: $state.snapshot(mask), ...body }) });
    if (!r.ok) return;
    mask = r.body.mask;
    await tick();
    caretAt(caret);
  }
  async function key(e) {
    if (!(e.metaKey && !["z", "y"].includes(e.key))) e.stopPropagation();   // (its keys are masking's: the page's, but ⌘ ones, not)
    const sel = window.getSelection();
    const a = offsetOf(sel.anchorNode, sel.anchorOffset), b = offsetOf(sel.focusNode, sel.focusOffset);
    if (e.key === "[" || e.key === "]") {
      e.preventDefault();
      if (a === null) return;
      const [lo, hi] = a <= b ? [a, b] : [b, a];
      if (lo !== hi) await op({ op: e.key === "[" ? "wrap" : "minus", a: lo, b: hi }, lo);
      else await op({ op: e.key === "[" ? "open" : "close", a: lo }, lo);
    } else if (e.key === "Backspace" || e.key === "Delete") {
      e.preventDefault();
      if (a === null) return;
      const at = mask.map((x, k) => [x, k]).filter(([x]) => x === a);   // (the bracket the caret's at: Backspace the one before, Delete after)
      const k = at.length ? at[e.key === "Backspace" ? 0 : at.length - 1][1] : -1;
      if (k >= 0) await op({ op: "drop", i: k }, a);
    } else if (e.key === "Tab") {
      e.preventDefault();
      if (a === null || !mask.length) return;
      const next = e.shiftKey ? [...mask].reverse().find((x) => x < a) ?? mask[mask.length - 1] : mask.find((x) => x > a) ?? mask[0];
      caretAt(next);
    } else if (e.key === "Escape" || e.key === "Enter") {
      e.preventDefault();
      const m = $state.snapshot(mask);
      close();
      await finish(draft, m);
    } else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) {
      e.preventDefault();   // (no typing)
    }
  }
  const left = () => setTimeout(() => {   // (clicked away: leave it, nothing saved)
    if (panel?.isConnected && !panel.contains(document.activeElement)) { close(); cancel(); }
  }, 200);

  onMount(() => {
    box.classList.add("fw-masking-on");
    panel.focus();
    caretAt(mask.length ? mask[0] : 0);
    return () => box.classList.remove("fw-masking-on");
  });
</script>

<div class="fw-masking" contenteditable="true" spellcheck="false" bind:this={panel} role="textbox" tabindex="-1"
  onbeforeinput={(e) => e.preventDefault()} onpaste={(e) => e.preventDefault()} onkeydown={key} onblur={left}>
  {#each parts as part}
    {#if part.unit}
      {#if part.unit.data?.t === "quote"}
        <div style="display: contents" use:quoteUnit={part}></div>
      {:else if part.unit.data?.t === "image" && part.unit.data.file}
        <div class="fw-image fw-unit {part.on ? 'fw-unit-shown' : 'fw-unit-hid'}" data-off={part.unit.start} data-zw="" contenteditable="false"><img src="/images/{part.unit.data.file}" alt="" /></div>
      {:else}
        <div class="fw-munit fw-unit {part.on ? 'fw-unit-shown' : 'fw-unit-hid'}" data-off={part.unit.start} data-zw="" contenteditable="false">{part.unit.t === "quote" ? part.unit.title : "picture"}</div>
      {/if}
    {:else}
      <div class="fw-mblock">
        {#each part.rows as row}
          <div class="fw-mline">{#each row as x}{#if x.br}<span class="fw-br fw-br-{x.br}" data-off={x.off} data-anchor={x.k} contenteditable="false">{x.br === "close" ? "›" : "‹"}</span>{:else if x.zw}<span class={x.on ? "fw-shown" : "fw-hid"} data-off={x.off} data-zw="">​</span>{:else}<span class={x.on ? "fw-shown" : "fw-hid"} data-off={x.off}>{x.text}</span>{/if}{/each}</div>
        {/each}
      </div>
    {/if}
  {/each}
</div>
