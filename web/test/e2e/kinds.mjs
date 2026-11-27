import { join } from "node:path";
import { writeFileSync } from "node:fs";
import { A, B, B1, K, M, N, T } from "./fixture.mjs";

export const scenarios = {};

scenarios.review = async (t) => {   // (a model's guesses beside the store, as a model would leave them: alpha and beta might be poems)
  await t.open(`#/p/${K}`);
  t.check("a kind's header: its maybes, to review", await t.until(`[...document.querySelectorAll(".fw-field")].some(f => f.innerText.includes("2 · ↵ review them"))`, 2000),
    await t.js(`document.querySelector(".fw-fields")?.innerText`));
  await t.js(`[...document.querySelectorAll(".fw-chip")].find(c => c.innerText.includes("review them")).click(); 1`);
  await t.settle();
  t.check("  reviewing: the first maybe, where it lives; the bar asks", await t.until(`window.fw.editor()?.id === "${A}" && document.querySelector("#bar-left").innerText.includes("is “alpha” one?")`, 3000),
    await t.js(`document.querySelector("#bar-left").innerText`));
  await t.key("Enter");   // yes
  await t.settle();
  t.check("  Enter: yes; the next", await t.until(`window.fw.editor()?.id === "${B}"`, 3000));
  await t.key("Backspace");   // no
  await t.settle();
  const answers = async (id) => (await t.get(`/api/pericope/${id}`)).kindTokens.map((x) => x.mark).join(",");
  t.check("  Backspace: no; done, back on the kind, saying how it went", await t.until(`window.fw.editor()?.id === "${K}" && document.querySelector("#bar-left").innerText.includes("reviewed: 1 yes, 1 no")`, 3000)
    && (await answers(A)) === "yes" && (await answers(B)) === "no", `${await answers(A)} / ${await answers(B)}`);
};

scenarios.kinds = async (t) => {
  await t.open(`#/p/${B}@${B1}`);
  await t.key("ArrowUp");
  t.check("↑ from the first line: the title", await t.until(`document.activeElement?.classList.contains("fw-title")`, 1000));
  await t.key("ArrowUp");
  t.check("  ↑ again: the kinds line", await t.until(`document.activeElement?.classList.contains("fw-chip")`, 1000));
  await t.key("h");   // (typing on the line: the picker, with it typed)
  await t.until(`document.querySelector(".fw-menu")?.innerText.includes("tag ›")`, 2000);
  await t.type("aiku");
  t.check("  the picker: + new kind, with what's typed", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("+ new tag “haiku”")`, 2000));
  await t.key("Enter");
  await t.settle();
  const tok = (await t.get(`/api/pericope/${B}`)).kindTokens;
  t.check("  a new kind, said yes to: in the store, a token", tok.length === 1 && tok[0].name === "haiku" && tok[0].mark === "yes"
    && await t.until(`document.activeElement?.classList.contains("fw-chip-yes") && document.activeElement.innerText === "haiku"`, 2000), JSON.stringify(tok));
  await t.key("Backspace");
  await t.settle();
  t.check("  ⌫ on it: the answer taken back", (await t.get(`/api/pericope/${B}`)).kindTokens.length === 0);
  const haiku = (await t.get("/api/kinds")).kinds.find((k) => k.name === "haiku").id;
  await t.open(`#/p/${haiku}`);
  await t.js(`(() => { const x = document.querySelector(".fw-title"); x.focus(); x.select(); return true; })()`);
  await t.type("verse");
  await t.key("Enter");
  await t.settle();
  t.check("a kind's title: its name, renamed as you leave it", (await t.get("/api/kinds")).kinds.some((k) => k.name === "verse"));
};

// the kinds view (#/kinds): every kind folded, → its members, Enter opens; + new kind; a kind's page lists them
scenarios.kindsview = async (t) => {
  const say = (block, answer) => t.js(`fetch("/api/act", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ do: "kind", block: "${block}", kind: "${K}", answer: ${answer} }) }).then((r) => r.ok)`);
  await t.open("#/");
  await say(A, true); await say(B, true);
  t.check("only a pericope has kinds: a block inside one refused", !(await say(B1, true)));
  await t.key("u", 4 | 8);
  const rows = `[...document.querySelectorAll(".fw-kindsview .fw-row")].map((r) => r.innerText.replace(/\\s+/g, " ").trim()).join(" | ")`;
  t.check("⌘⇧U: the kinds view, each kind folded with its count", await t.until(`location.hash === "#/tags" && ${rows} === "▸ poem 2 + 1 sure + 1 maybe | ▸ no tag 4 | + new tag"`, 3000), await t.js(rows));
  await t.key("ArrowRight");
  t.check("  →: its members, yours newest first, then the model's sure ones, dim, then its maybes",
    await t.until(`${rows}.startsWith("▾ poem 2 + 1 sure + 1 maybe | beta") && ${rows}.includes("| alpha") && ${rows}.includes("| fox")
      && ${rows}.includes("| masker?") && document.querySelectorAll(".fw-member.fw-dim").length === 2 && document.querySelectorAll(".fw-member.fw-maybe").length === 1`, 2000), await t.js(rows));
  await t.key("ArrowDown");
  await t.key("Enter");
  t.check("  Enter on a member: opened", await t.until(`window.fw?.editor()?.id === "${B}"`, 4000));
  await t.key("u", 4 | 8);
  await t.until(`location.hash === "#/tags" && document.querySelector(".fw-kindsview .fw-sel")`, 3000);
  t.check("  back again: still open", await t.until(`document.querySelectorAll(".fw-member").length === 4`, 3000));
  for (let i = 0; i < 3; i++) await t.key("ArrowDown");   // (from the kind: beta, alpha, fox, the sure guess)
  await t.key("y");
  t.check("  Y on a guess: yes, it joins yours, the next selected", await t.until(`${rows}.startsWith("▾ poem 3 + 1 maybe") && document.querySelector(".fw-sel")?.innerText.includes("masker")`, 3000)
    && (await t.get(`/api/pericope/${T}`)).kindTokens.some((x) => x.mark === "yes"), await t.js(rows));
  await t.key("n");
  t.check("  N on a maybe: no, it goes", await t.until(`${rows}.startsWith("▾ poem 3 | ") && !${rows}.includes("masker")`, 3000)
    && (await t.get(`/api/pericope/${M}`)).kindTokens.some((x) => x.mark === "no"), await t.js(rows));
  await say(T, null); await say(M, null);   // (as it was: fox sure, masker maybe)
  t.check("  answered elsewhere: followed", await t.until(`${rows}.startsWith("▾ poem 2 + 1 sure + 1 maybe")`, 3000), await t.js(rows));
  for (let i = 0; i < 4; i++) await t.key("ArrowUp");   // (from + new kind, where N left it: up to beta)
  await t.key("n");
  t.check("  N on one of yours: taken out (a no)", await t.until(`${rows}.startsWith("▾ poem 1 + 1 sure + 1 maybe | alpha")`, 3000)
    && (await t.get(`/api/pericope/${B}`)).kindTokens.some((x) => x.mark === "no"), await t.js(rows));
  await say(B, true);
  await t.until(`${rows}.startsWith("▾ poem 2 + 1 sure + 1 maybe")`, 3000);
  for (let i = 0; i < 5; i++) await t.key("ArrowUp");   // (up to poem)
  await t.key("ArrowLeft"); await t.key("ArrowDown");
  await t.key("ArrowRight");
  t.check("  no kind, last: the pericopes of none (a maybe isn't one), newest first", await t.until(`${rows}.includes("▾ no tag 4 | nested") && ${rows}.includes("| masker")
    && !${rows}.includes("| fox") && !${rows}.includes("| poem ")`, 2000), await t.js(rows));
  await t.key("ArrowLeft"); await t.key("ArrowDown");
  t.check("  ←: folded; ↓ to + new kind", await t.until(`${rows} === "▸ poem 2 + 1 sure + 1 maybe | ▸ no tag 4 | + new tag" && document.querySelector(".fw-sel")?.classList.contains("fw-newkind")`, 2000), await t.js(rows));
  await t.key("Enter");
  await t.until(`document.activeElement?.matches(".fw-newkind .fw-input")`, 2000);
  await t.type("song");
  await t.key("Enter");
  t.check("  + new kind: named, made, selected", await t.until(`${rows}.includes("▸ song 0") && document.querySelector(".fw-sel")?.innerText.includes("song")`, 3000)
    && (await t.get("/api/kinds")).kinds.some((k) => k.name === "song"), await t.js(rows));
  await t.key("Backspace", 4);
  await t.until(`!!document.querySelector(".fw-ask")`, 2000);
  await t.key("y");
  t.check("  ⌘⌫ on a kind, asked, y: deleted", await t.until(`${rows} === "▸ poem 2 + 1 sure + 1 maybe | ▸ no tag 4 | + new tag"`, 3000)
    && !(await t.get("/api/kinds")).kinds.some((k) => k.name === "song"), await t.js(rows));
  await t.key("ArrowUp");
  await t.key("Enter");
  t.check("  Enter on a kind: its page, its members below what it says", await t.until(`window.fw?.editor()?.id === "${K}" && document.querySelectorAll(".fw-members .fw-row").length === 4`, 4000));
  await t.end();
  await t.key("ArrowDown");
  t.check("  ↓ past its last block: into them", await t.until(`document.querySelector(".fw-members .fw-sel")?.innerText.includes("beta")`, 2000));
  await t.key("ArrowUp");
  t.check("  ↑ from the first: back in the kind", await t.until(`!document.querySelector(".fw-members .fw-sel") && window.fw.editor()?.view.hasFocus()`, 2000));
  await t.key("Escape");
};

scenarios.kindtree = async (t) => {   // kinds of kinds: nested in each kind they're of, roots at the top, ↻ for a loop
  const act = (body) => t.js(`fetch("/api/act", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(${JSON.stringify(body)}) }).then((r) => r.json())`);
  await t.open("#/");
  const F = (await act({ do: "newkind", name: "form" })).kind, S = (await act({ do: "newkind", name: "sonnet" })).kind;
  await act({ do: "kind", block: S, kind: K, answer: true });
  await act({ do: "kind", block: S, kind: F, answer: true });
  await act({ do: "kind", block: K, kind: F, answer: true });
  await act({ do: "kind", block: A, kind: S, answer: true });
  await t.key("u", 4 | 8);
  const rows = `[...document.querySelectorAll(".fw-kindsview .fw-row")].map((r) => r.innerText.replace(/\\s+/g, " ").trim()).join(" | ")`;
  t.check("only the kinds of no kind at the top: form", await t.until(`${rows}.startsWith("▸ form 2 | ▸ no tag")`, 3000), await t.js(rows));
  await t.key("ArrowRight");
  t.check("  → form: poem and sonnet nested in it, as kinds", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▸ poem 1 | ▸ no tag")`, 2000), await t.js(rows));
  await t.key("ArrowDown"); await t.key("ArrowDown"); await t.key("ArrowRight");
  t.check("  → poem: sonnet again inside it, a level further in (in every place it's of)", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▾ poem 1 | ▸ sonnet 1 | ▸ no tag")
    && document.querySelectorAll('.fw-kindsview [data-kind="${S}"]').length === 2`, 2000), await t.js(rows));
  await t.key("ArrowDown"); await t.key("ArrowRight");
  t.check("  → sonnet there: its own member", await t.until(`${rows}.includes("▾ sonnet 1 | alpha")`, 2000), await t.js(rows));
  await t.key("ArrowLeft"); await t.key("ArrowLeft");
  t.check("  ← ←: sonnet folded, then out to poem, folded", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▸ poem 1 | ▸ no tag")
    && document.querySelector(".fw-sel")?.dataset.kind === "${K}"`, 2000), await t.js(rows));
  await t.key("ArrowRight"); await t.key("ArrowDown"); await t.key("n");
  t.check("  N on sonnet in poem: taken out of poem (form keeps it)", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▾ poem 0 | ▸ no tag")`, 3000), await t.js(rows));
  await act({ do: "kind", block: F, kind: S, answer: true });   // (a loop: form is a sonnet, a sonnet is a form)
  const tops = `[...document.querySelectorAll(".fw-kindsview .fw-kind:not(.fw-nested):not(.fw-nokind)")].map((r) => r.dataset.kind).join(",")`;
  t.check("  a loop: every kind of some kind; the oldest (poem) at the top, then the first the loop would hide (made the same second: either)",
    await t.until(`["${K},${F}", "${K},${S}"].includes(${tops})`, 3000), await t.js(rows));
  const second = (await t.js(tops)).split(",")[1];
  for (let i = 0; i < 9; i++) await t.key("ArrowUp");
  await t.key("ArrowDown");
  if (!(await t.js(`document.querySelector(".fw-sel")?.dataset.kind === "${second}" && document.querySelector(".fw-sel").innerText.startsWith("▾")`))) await t.key("ArrowRight");
  await t.key("ArrowDown"); await t.key("ArrowRight");
  t.check("  the other opened inside it: it met again inside itself, ↻", await t.until(`[...document.querySelectorAll(".fw-loop")].some((r) => r.dataset.kind === "${second}")`, 3000), await t.js(rows));
};

scenarios.kindsview.setup = (dir, data) => {   // guesses (current): fox is a poem (sure), masker maybe
  const at = Object.fromEntries(data.blocks.map((b) => [b.id, b.updated]));
  writeFileSync(join(dir, "kind-guesses.json"), JSON.stringify({ model: "test", guesses: { [K]: { [T]: [0.95, at[K], at[T]], [M]: [0.7, at[K], at[M]] } } }));
};

scenarios.review.setup = (dir, data) => {   // the guesses, current: each pair's kind and block as stored now
  const at = Object.fromEntries(data.blocks.map((b) => [b.id, b.updated]));
  writeFileSync(join(dir, "kind-guesses.json"), JSON.stringify({ model: "test",
    guesses: { [K]: { [A]: [0.8, at[K], at[A]], [B]: [0.7, at[K], at[B]] } } }));
};
