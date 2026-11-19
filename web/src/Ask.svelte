<!-- Ask.svelte — the question in the page (ask.js puts it in ui.asking): Enter or y, yes; anything else, no; leaving
     it, no. -->
<script>
  import { ui } from "./state.svelte.js";
  let box = $state();
  $effect(() => { box?.focus(); });
  function key(e) {
    e.preventDefault();
    e.stopPropagation();
    if (["Shift", "Meta", "Control", "Alt"].includes(e.key)) return;
    ui.asking?.answer(e.key === "Enter" || e.key === "y");
  }
  const left = () => {   // (left: no, but only to this question; another may be open by the time this looks)
    const asked = ui.asking;
    setTimeout(() => { if (asked && ui.asking === asked && document.activeElement !== box) asked.answer(false); }, 100);
  };
</script>

<div class="fw-ask" tabindex="-1" bind:this={box} onkeydown={key} onblur={left} role="dialog">
  <div>{ui.asking.question}</div>
  <div class="fw-dim">{ui.asking.yes}</div>
</div>
