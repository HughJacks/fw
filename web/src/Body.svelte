<!-- Body.svelte — every pericope's body: where its blocks are written (the editor, ProseMirror, editor.js, drawn into
     `host`) with the gutter's tabs beside it. One body for every pericope (the user, 2026-11-19): it stays on the page;
     what's written in it is made again for each pericope opened (Pericope.svelte). -->
<script>
  import Tabs from "./Tabs.svelte";
  // host: the element the editor's drawn into (bound out); drawn: what moves the boxes (the editors' states, the width:
  // the tabs measured again); focus: where you are (editor.svelte.js focusOf); hidden: no tabs (reviewing);
  // pick(box): a tab clicked, its block selected whole
  let { host = $bindable(), drawn, focus, hidden = false, pick } = $props();
</script>

<div class="fw-doc" bind:this={host}><Tabs doc={host} {drawn} {focus} {hidden} {pick} /></div>
