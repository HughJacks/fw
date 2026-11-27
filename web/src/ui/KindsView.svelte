<!-- KindsView.svelte — the kinds view (#/kinds; "for now we should call this the kinds view, not
     necessarily home, this is where we can create new kinds and organize these things"): every kind, folded to its
     name and how many are of it; → opens one, showing its members under it (as on the kind's own page, Members.svelte:
     your answers, newest first, then the model's sure guesses, dim, then its maybes, dimmer, each a guess answered with Y
     or N), ← folds it; Enter opens the kind, or a member; N takes one
     of yours out; ⌘⌫ deletes a kind (asked first); + new kind, last, names one. Only a pericope has kinds; a kind is one, so a kind can be of kinds: it's shown nested in each kind
     it's of (a loop drawn ↻), at the top only when it's of none (or a loop would hide it); nothing carried up. Last, "no kind": the pericopes of none (no yes, no sure guess),
     a group opened like a kind (Enter too: it has no page). Followed as the store changes. Later, maybe: kinds and'ed together, a query
     over every field (not yet: the user's). Runes: the kinds, what's open, what's selected are $state; the rows
     $derived. -->
<script module>
  import { SvelteSet } from "svelte/reactivity";
  const opened = new SvelteSet();   // (the kinds opened: kept while the tab is, coming back here)
</script>
<script>
  import { tick } from "svelte";
  import { api } from "../lib/api.js";
  import { onStore } from "../lib/live.js";
  import { say } from "../state/state.svelte.js";
  import { ask } from "../lib/ask.js";
  import { reveal } from "../lib/scrolling.js";
  import { keyOf as keyFor, pressed, pretty } from "../lib/keys.js";

  let { go, home } = $props();   // (go: open a place; home: Esc)
  const keyName = (id) => pretty(keyFor(id));
  const NONE = "none";   // (the group of no kind: no kind's id, a pericope's being a date)
  let kinds = $state(null), unkinded = $state([]), at = $state("new"), naming = $state(false), name = $state("");
  let list = $state(), input = $state();
  // A row: a kind {t: "kind", k, path, depth, of?, m?} (nested: `of` the kind it's a member of, `m` its member line
  // there), a member {t: "member", k: whose, m, path: whose path, depth}, a loop {t: "loop", k, of, m, path, depth}
  // (a kind met again inside itself: ↻), or + new kind. A kind's place is its path (ids from its root, "/"): the same
  // kind can be in several places, each opened on its own.
  const keyOf = (r) => (r.t === "kind" ? `k:${r.path}` : r.t === "member" ? `m:${r.path}:${r.m.key}` : r.t === "loop" ? `l:${r.path}` : "new");
  // (kinds of kinds, the user: "a kind that has a kind would show up nested in the kinds page", in each place
  // it's of: a kind of another is a member of it, nothing carried up (a sonnet that's a poem says so itself). The top
  // level: the kinds of no kind (yours or a sure guess), and any a loop would leave out, oldest first.)
  let byId = $derived(new Map((kinds || []).map((k) => [k.id, k])));
  const kindsIn = (k) => k.members.filter((m) => !m.maybe && byId.has(m.key) && m.key !== k.id).map((m) => m.key);
  let roots = $derived.by(() => {
    const all = kinds || [], under = new Set(all.flatMap(kindsIn));
    const out = all.filter((k) => !under.has(k.id)), seen = new Set();
    const reach = (k) => { if (seen.has(k.id)) return; seen.add(k.id); kindsIn(k).forEach((c) => reach(byId.get(c))); };
    out.forEach(reach);
    for (const k of all) if (!seen.has(k.id)) { out.push(k); reach(k); }
    return out.sort((a, b) => (a.id < b.id ? -1 : 1));
  });
  // (after the kinds, the pericopes of no kind, a group like one)
  function tree(k, path, depth, inside, of = null, m = null) {
    const out = [{ t: "kind", k, path, depth, of, m }];
    if (!opened.has(path)) return out;
    for (const mm of k.members) {
      const c = !mm.maybe && mm.key !== k.id ? byId.get(mm.key) : null;
      if (!c) out.push({ t: "member", k, m: mm, path, depth: depth + 1 });
      else if (inside.has(c.id) || c.id === k.id) out.push({ t: "loop", k: c, of: k, m: mm, path: `${path}/${c.id}`, depth: depth + 1 });
      else out.push(...tree(c, `${path}/${c.id}`, depth + 1, new Set([...inside, k.id]), k, mm));
    }
    return out;
  }
  let rows = $derived([...roots.flatMap((k) => tree(k, k.id, 0, new Set())),
    ...(kinds ? tree({ id: NONE, name: "no tag", members: unkinded }, NONE, 0, new Set()) : []), { t: "new", depth: 0 }]);
  const up = (r) => (r.t === "kind" ? (r.path.includes("/") ? r.path.slice(0, r.path.lastIndexOf("/")) : null) : r.t === "new" ? null
    : r.t === "loop" ? r.path.slice(0, r.path.lastIndexOf("/")) : r.path);   // (the path of the kind it's shown in)
  let sel = $derived(Math.max(0, rows.findIndex((r) => keyOf(r) === at)));   // (gone: the first)

  async function load() {
    const r = await api("/api/kinds?members=1");
    if (!r.ok) return;
    const first = kinds === null;
    kinds = r.body.kinds;
    unkinded = r.body.unkinded || [];
    if (first) at = keyOf(rows[0]);
  }
  const counted = (k) => {
    const sure = k.members.filter((m) => m.dim && !m.maybe).length, maybe = k.members.filter((m) => m.maybe).length;
    return `${k.members.length - sure - maybe}${sure ? ` + ${sure} sure` : ""}${maybe ? ` + ${maybe} maybe` : ""}`;
  };
  /** A member answered (Y yes, N no; "a way to accept or deny from the kinds page", "remove
   * pericopes from kinds"): a guess accepted or denied, one of yours taken out (a no, so a guess can't put it back);
   * the next row selected, as a review goes on, and the kinds asked again. */
  async function answer(r, yes) {
    const next = rows[sel + 1], kind = r.t === "member" ? r.k : r.of;   // (a kind nested, a loop: a member of `of`)
    const got = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "kind", block: r.m.key, kind: kind.id, answer: yes }) });
    if (!got.ok) { say(got.body.error || "couldn't"); return; }
    say(`${r.m.title}: ${yes ? "" : "not "}${kind.name}`);
    if (next) at = keyOf(next);
    await load();
  }
  /** A kind deleted (asked first; "let me delete kinds in the kinds page"): the kind, what it
   * says, and every answer about it go; what was of it stays. The next row selected. */
  async function remove(r) {
    let i = sel + 1;
    while (rows[i] && rows[i].depth > r.depth) i++;   // (past what's open under it)
    const next = rows[i];
    if (!(await ask(`delete the tag “${r.k.name}”? what's tagged stays, only the tag goes. this can't be undone.`))) return;
    const got = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "delete", pericope: r.k.id }) });
    if (!got.ok) { say(got.body.error || "couldn't"); return; }
    say(`deleted the tag ${r.k.name}`);
    if (next) at = keyOf(next);
    await load();
    list?.focus();
  }
  const indent = (r) => `calc(.4rem + ${2 * r.depth}ch)`;   // (two columns a level, as the members were)
  const open = (r) => go(r.t === "kind" || r.t === "loop" ? `#/p/${r.k.id}` : `#/p/${r.m.open}` + (r.m.key !== r.m.open ? `@${r.m.key}` : ""));
  async function name1() { naming = true; name = ""; await tick(); input?.focus(); }
  async function make() {
    const r = await api("/api/act", { method: "POST", body: JSON.stringify({ do: "newkind", name }) });
    if (!r.ok) { say(r.body.error || "couldn't"); return; }
    naming = false;
    await load();
    at = `k:${r.body.kind}`;
    say(`a tag: ${name.trim()}`);
    list?.focus();
  }
  function onkey(e) {
    const r = rows[sel];
    if (e.key === "ArrowDown") at = keyOf(rows[Math.min(rows.length - 1, sel + 1)]);
    else if (e.key === "ArrowUp") at = keyOf(rows[Math.max(0, sel - 1)]);
    else if (e.key === "ArrowRight" && r.t === "kind") opened.add(r.path);
    else if (e.key === "ArrowLeft" && r.t !== "new") {   // (fold it, open; else the kind it's shown in, that selected)
      const fold = r.t === "kind" && opened.has(r.path) ? r.path : up(r);
      if (fold) { opened.delete(fold); at = `k:${fold}`; }
    }
    else if (e.key === "Enter") { if (r.t === "new") name1(); else if (r.t === "kind" && r.k.id === NONE) opened.has(NONE) ? opened.delete(NONE) : opened.add(NONE); else open(r); }
    else if (r.m && r.k.id !== NONE && r.m.dim && pressed(e, "kindYes")) answer(r, true);
    else if (r.m && r.k.id !== NONE && pressed(e, "kindNo")) answer(r, false);
    else if (r.t === "kind" && r.k.id !== NONE && pressed(e, "kindDelete")) remove(r);
    else if (e.key === "Escape") home();
    else return;
    e.preventDefault();
  }
  function onname(e) {
    if (e.key === "Enter") { e.preventDefault(); if (name.trim()) make(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); naming = false; list?.focus(); }
  }
  const click = (e, r) => { e.preventDefault(); at = keyOf(r); list?.focus(); if (r.t === "kind") (opened.has(r.path) ? opened.delete(r.path) : opened.add(r.path)); else if (r.t === "new") name1(); else open(r); };

  $effect(() => {   // (opened: its kinds, then followed as the store changes)
    const stop = onStore(load);   // (the first word too: a change made before the first look isn't missed)
    load().then(() => list?.focus());
    return stop;
  });
  $effect(() => { sel; tick().then(() => reveal(list?.querySelector(".fw-sel"))); });   // (smoothly, with room: scrolling.js)
</script>

<div class="fw-kindsview fw-home-page">
  <div class="fw-rows fw-library" tabindex="-1" bind:this={list} onkeydown={onkey} role="listbox">
    {#each rows as r, n (keyOf(r))}
      {#if r.t === "kind"}
        <div class={"fw-row fw-kind" + (n === sel ? " fw-sel" : "") + (r.k.id === NONE ? " fw-nokind" : "") + (r.m?.dim ? " fw-dim" : "") + (r.depth ? " fw-nested" : "")}
          style:padding-left={indent(r)} data-kind={r.k.id} role="option" aria-selected={n === sel} tabindex="-1" onmousedown={(e) => click(e, r)}>
          <span class="fw-row-label">{opened.has(r.path) ? "▾" : "▸"} {r.k.name}</span><span class="fw-dim">{n === sel && r.m?.dim ? `${keyName("kindYes")} yes · ${keyName("kindNo")} no  ` : ""}{counted(r.k)}</span>
        </div>
      {:else if r.t === "loop"}
        <div class={"fw-row fw-loop fw-dim" + (n === sel ? " fw-sel" : "")} style:padding-left={indent(r)} data-kind={r.k.id} role="option"
          aria-selected={n === sel} tabindex="-1" onmousedown={(e) => click(e, r)}>
          <span class="fw-row-label">↻ {r.k.name}</span>
        </div>
      {:else if r.t === "member"}
        <div class={"fw-row fw-member" + (n === sel ? " fw-sel" : "") + (r.m.dim ? " fw-dim" : "") + (r.m.maybe ? " fw-maybe" : "")} style:padding-left={indent(r)} data-pericope={r.m.open} role="option"
          aria-selected={n === sel} tabindex="-1" onmousedown={(e) => click(e, r)}>
          <span class="fw-row-label">{r.m.title}{r.m.maybe ? "?" : ""}</span><span class="fw-dim">{n !== sel || r.k.id === NONE ? "" : r.m.dim ? `${keyName("kindYes")} yes · ${keyName("kindNo")} no  ` : `${keyName("kindNo")} take out  `}{r.m.right}</span>
        </div>
      {:else}
        <div class={"fw-row fw-newkind" + (n === sel ? " fw-sel" : "")} role="option" aria-selected={n === sel} tabindex="-1"
          onmousedown={(e) => click(e, r)}>
          {#if naming}<span class="fw-row-label">+ new tag: <input class="fw-input" bind:this={input} bind:value={name} onkeydown={onname}
            onblur={() => (naming = false)} placeholder="its name" /></span>
          {:else}<span class="fw-row-label">+ new tag</span>{/if}
        </div>
      {/if}
    {/each}
  </div>
</div>
